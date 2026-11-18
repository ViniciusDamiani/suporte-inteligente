"""Persistência administrativa local; cada sessão pertence a um usuário autenticado."""
import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

from .attachments import clean_text, interpret
from .engine import answer, new_state, now, view
from .model import check, load_models


class SessionStore:
    def __init__(self, path, models=None):
        self.path = Path(path)
        self.models = models if models is not None else load_models()

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS triage_sessions (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, version INTEGER NOT NULL,
                updated_at TEXT NOT NULL, state TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS triage_owner ON triage_sessions(owner,updated_at)")
            db.commit()
            return db
        except BaseException:
            db.close()
            raise

    def _get(self, db, session_id, user_id):
        check(isinstance(user_id, str) and user_id, "Usuário obrigatório.", 401)
        check(isinstance(session_id, str) and len(session_id) <= 100, "Sessão inválida.")
        row = db.execute("SELECT version,updated_at,state FROM triage_sessions WHERE id=? AND owner=?", (session_id, user_id)).fetchone()
        check(row is not None, "Triagem não encontrada.", 404)
        return row

    def _response(self, session_id, version, updated, state):
        return {"id": session_id, "version": version, "updated_at": updated, **view(state)}

    def create(self, user_id, model_id, problem):
        check(isinstance(user_id, str) and user_id, "Usuário obrigatório.", 401)
        check(isinstance(model_id, str) and model_id in self.models, "Modelo de triagem não encontrado.")
        state = new_state(self.models[model_id], problem)
        session_id, updated = str(uuid.uuid4()), now()
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO triage_sessions VALUES (?,?,?,?,?)", (session_id, user_id, 0, updated, json.dumps(state, ensure_ascii=False)))
        return self._response(session_id, 0, updated, state)

    def list(self, user_id):
        check(isinstance(user_id, str) and user_id, "Usuário obrigatório.", 401)
        with closing(self._connect()) as db:
            rows = db.execute("SELECT id,version,updated_at,state FROM triage_sessions WHERE owner=? ORDER BY updated_at DESC LIMIT 50", (user_id,)).fetchall()
        sessions = []
        for sid, version, updated, raw in rows:
            state = json.loads(raw)
            sessions.append({"id": sid, "version": version, "updated_at": updated, "title": state["model"]["title"],
                             "problem": state["problem"][:160], "closed": state["closed"]})
        return sessions

    def get(self, session_id, user_id):
        with closing(self._connect()) as db:
            version, updated, raw = self._get(db, session_id, user_id)
        return self._response(session_id, version, updated, json.loads(raw))

    def change(self, session_id, user_id, expected_version, operation, data=None, raw=None, filename=None):
        check(type(expected_version) is int and expected_version >= 0, "Versão da sessão obrigatória.")
        check(isinstance(data, dict), "Dados da operação devem ser objeto JSON.")
        with closing(self._connect()) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                version, _, stored = self._get(db, session_id, user_id)
                check(version == expected_version, "A triagem foi atualizada em outra aba. Recarregue antes de continuar.", 409)
                state = json.loads(stored)
                check(not state["closed"], "Triagem já encaminhada; inicie uma nova sessão.", 409)
                check(len(state["history"]) < 1000, "Limite de histórico atingido; encaminhe a análise e inicie outra sessão.", 409)
                if operation == "answer":
                    check("value" in data, "Resposta obrigatória; use nulo para não informado.")
                    answer(state, data.get("question_id"), data["value"])
                elif operation == "unavailable":
                    request_id = data.get("request_id")
                    check(any(r["id"] == request_id for r in state["model"]["evidence_requests"]), "Pedido desconhecido.")
                    reason = data.get("reason")
                    check(isinstance(reason, str) and 3 <= len(reason.strip()) <= 1000, "Descreva por que o anexo está indisponível.")
                    reason = clean_text(reason.strip())
                    state["unavailable"][request_id] = reason
                    state["history"].append({"kind": "anexo_indisponivel", "request_id": request_id, "reason": reason, "at": now()})
                elif operation == "attachment":
                    request_id = data.get("request_id")
                    check(any(r["id"] == request_id for r in state["model"]["evidence_requests"]), "Pedido desconhecido.")
                    check(isinstance(raw, bytes), "Arquivo obrigatório.")
                    check(type(data.get("occurrence_confirmed")) is bool, "Confirme se o arquivo pertence à instalação e ocorrência em análise.")
                    content_hash = hashlib.sha256(raw).hexdigest()
                    duplicate = next((a for a in state["attachments"] if a["sha256"] == content_hash and a["request_id"] == request_id), None)
                    if duplicate:
                        duplicate["occurrence_confirmed"] = data["occurrence_confirmed"]
                        state["history"].append({"kind": "anexo_reutilizado", "attachment_id": duplicate["id"], "at": now()})
                    else:
                        check(len(state["attachments"]) < 20, "Limite de 20 anexos por triagem.", 409)
                        attachment = interpret(filename, raw, request_id, data["occurrence_confirmed"])
                        state["attachments"].append(attachment)
                        state["history"].append({"kind": "anexo_recebido", "attachment_id": attachment["id"], "name": attachment["name"], "at": now()})
                    state["unavailable"].pop(request_id, None)
                elif operation == "remove_attachment":
                    attachment_id = data.get("attachment_id")
                    check(any(a["id"] == attachment_id for a in state["attachments"]), "Anexo não encontrado.", 404)
                    state["attachments"] = [a for a in state["attachments"] if a["id"] != attachment_id]
                    state["history"].append({"kind": "anexo_desconsiderado", "attachment_id": attachment_id, "at": now()})
                elif operation == "handoff":
                    state["closed"] = True
                    state["history"].append({"kind": "encaminhado_analise_tecnica", "at": now()})
                else:
                    check(False, "Operação desconhecida.")
                updated = now()
                # A derivação é validada antes de persistir; falhas não deixam sessão parcial.
                result = self._response(session_id, version + 1, updated, state)
                db.execute("UPDATE triage_sessions SET version=?,updated_at=?,state=? WHERE id=? AND owner=?",
                           (version + 1, updated, json.dumps(state, ensure_ascii=False), session_id, user_id))
                db.commit()
                return result
            except BaseException:
                db.rollback()
                raise
