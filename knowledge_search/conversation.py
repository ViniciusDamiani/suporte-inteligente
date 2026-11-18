"""Sessões locais do piloto; isolamento por usuário e repetição idempotente."""
import json
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path

from api.text_utils import anonymize
from .config import SearchError
from .text import clean_text
from .dialogue_context import retrieval_query, topic_terms

MAX_TURNS = 6
RETRYABLE = {"rejected", "unavailable", "rate_limited", "busy"}


def compact(turns):
    """Preserva o relato inicial e os últimos pares pergunta/resposta, sem fatos inferidos."""
    if len(turns) == 1:
        return turns[0]["message"][:1800]
    parts = ["Relato inicial: " + turns[0]["message"][:350]]
    allowance = 1400 // (len(turns) - 1)
    for turn in turns[1:]:
        if turn.get("asked"):
            parts.append("Pergunta anterior: " + turn["asked"][:allowance // 3])
        parts.append("Resposta do usuário: " + turn["message"][:allowance * 2 // 3])
    return "\n".join(parts)[:2000]


class ConversationStore:
    def __init__(self, path):
        self.path = Path(path)

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("""CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, turns TEXT NOT NULL,
            request_id TEXT, request_message TEXT, response TEXT,
            lease_until REAL NOT NULL DEFAULT 0, updated REAL NOT NULL)""")
        return db

    def begin(self, owner, session_id, request_id, message):
        if session_id is not None and not isinstance(session_id, str):
            raise SearchError("Referência de conversa inválida.", 400)
        for value in (request_id, session_id if session_id is not None else request_id):
            if not isinstance(value, str) or len(value) != 36:
                raise SearchError("Referência de conversa inválida.", 400)
            try:
                uuid.UUID(value)
            except ValueError as exc:
                raise SearchError("Referência de conversa inválida.", 400) from exc
        if not isinstance(message, str) or not 2 <= len(message.strip()) <= 1800:
            raise SearchError("Escreva entre 2 e 1.800 caracteres.", 400)
        message = clean_text(anonymize(message.strip()))
        identifier = session_id or request_id
        now = time.time()
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM conversations WHERE updated < ? AND lease_until < ?", (now - 86400, now))
            row = db.execute("SELECT * FROM conversations WHERE id=? AND owner=?", (identifier, owner)).fetchone()
            retry = False
            if row is None:
                if session_id:
                    raise SearchError("Conversa não encontrada ou expirada. Inicie uma nova investigação.", 404)
                if db.execute("SELECT 1 FROM conversations WHERE id=?", (identifier,)).fetchone():
                    raise SearchError("Conversa não encontrada.", 404)
                db.execute("INSERT INTO conversations(id,owner,turns,updated) VALUES (?,?,?,?)", (identifier, owner, "[]", now))
                turns = []
            else:
                if row["request_id"] == request_id and row["request_message"] != message:
                    raise SearchError("Use uma nova referência para uma nova mensagem.", 409)
                if row["request_id"] == request_id and row["response"]:
                    return identifier, None, json.loads(row["response"])
                if row["response"] and json.loads(row["response"]).get("decision") == "answer":
                    raise SearchError("Esta investigação foi concluída. Inicie uma nova investigação.", 409)
                if row["lease_until"] > now:
                    raise SearchError("Aguarde a resposta em andamento.", 409)
                turns = json.loads(row["turns"])
                previous = json.loads(row["response"]) if row["response"] else {}
                retry = (previous.get("generation_status") in RETRYABLE and turns
                         and turns[-1]["message"] == message)
                if len(turns) >= MAX_TURNS and not retry:
                    raise SearchError("Esta investigação atingiu seis mensagens. Inicie uma nova investigação.", 400)
            asked = json.loads(row["response"]).get("follow_up", "") if row and row["response"] else ""
            if not retry:
                turns.append({"message": message, "asked": asked})
            db.execute("UPDATE conversations SET lease_until=?,updated=? WHERE id=?", (now + 180, now, identifier))
        return identifier, turns, None

    def finish(self, owner, identifier, request_id, turns, response):
        with closing(self.connect()) as db, db:
            db.execute("""UPDATE conversations SET turns=?,request_id=?,request_message=?,response=?,
                lease_until=0,updated=? WHERE id=? AND owner=?""",
                       (json.dumps(turns, ensure_ascii=False), request_id, turns[-1]["message"],
                        json.dumps(response, ensure_ascii=False), time.time(), identifier, owner))

    def release(self, owner, identifier):
        with closing(self.connect()) as db, db:
            db.execute("UPDATE conversations SET lease_until=0 WHERE id=? AND owner=?", (identifier, owner))


def reply(store, search, generator, owner, data):
    if not isinstance(data, dict) or data.keys() - {"message", "session_id", "request_id"}:
        raise SearchError("Envie message, request_id e, opcionalmente, session_id.", 400)
    identifier, turns, cached = store.begin(owner, data.get("session_id"), data.get("request_id"), data.get("message"))
    if cached is not None:
        return cached
    try:
        context = compact(turns)
        query = retrieval_query(turns)
        if query:
            result = search.search(query, 20)
        else:
            # Sem assunto pesquisável, pedir contexto sem buscar palavras de instrução.
            result = {"query": "", "mode": "textual", "results": [], "warnings": [],
                      "generated_answer": None, "generation_status": "pending", "source_count": 0}
        result["topic_terms"] = topic_terms(turns)
        evidence = search.evidence(result)
        questions = [t["asked"] for t in turns if t["asked"]]
        decision = generator.converse(evidence, context, questions, len(turns) < 4)
        result.update(decision, session_id=identifier, turn=len(turns),
                      messages=[{"message": t["message"], "asked": t["asked"]} for t in turns],
                      generation_available=generator.settings.status() == "ready")
        store.finish(owner, identifier, data["request_id"], turns, result)
        return result
    except BaseException:
        store.release(owner, identifier)
        raise
