"""Executa os serviços reais com banco sintético; nenhuma chamada ao Firebase."""
import copy
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from api.services import suggestion_service, ticket_service
from evaluation.legacy_triage.model import load_models
from evaluation.legacy_triage.storage import SessionStore


class Document:
    def __init__(self, data):
        self.id = data["id"]
        self.data = {**data, **ticket_service._derived_fields(data)}

    def to_dict(self):
        return copy.deepcopy(self.data)


class MemoryQuery:
    def __init__(self, documents):
        self.documents = documents

    def where(self, *, filter):
        if filter.field_path != "keywords" or filter.op_string != "array_contains_any":
            raise ValueError("A consulta da aplicação mudou; atualize o adaptador da avaliação.")
        terms = set(filter.value)
        return MemoryQuery([d for d in self.documents if terms.intersection(d.data["keywords"])])

    def limit(self, count):
        return MemoryQuery(self.documents[:count])

    def stream(self):
        return iter(self.documents)


class MemoryDB:
    def __init__(self, documents):
        self.documents = documents
        self.audit = []

    def collection(self, name):
        if name == "tickets":
            return MemoryQuery(self.documents)
        if name == "suggestion_queries":
            return self
        raise ValueError("Coleção inesperada na avaliação offline.")

    def add(self, data):
        self.audit.append(data)
        return None, SimpleNamespace(id="avaliacao-local")


def search(case, corpus, limit=5):
    db = MemoryDB([Document(record) for record in corpus])
    user = SimpleNamespace(id="avaliacao", team_id="equipe-sintetica", role="agent")
    with patch.object(suggestion_service, "get_db", return_value=db), patch.object(suggestion_service.Config, "SUGGESTIONS_LIMIT", limit):
        data, error, status = suggestion_service.suggest(text=case["query"], user=user)
    return {"http_status": status, "error": error, "results": (data or {}).get("results", [])}


def triage(case, setup=None):
    # Cada cenário é uma sessão real em banco temporário independente.
    with tempfile.TemporaryDirectory(prefix="triage-eval-") as folder:
        store = SessionStore(Path(folder) / "sessions.sqlite3", models=load_models())
        state = store.create("avaliacao", case["model_id"], case["problem"])
        for question_id, value in (setup or {}).items():
            state = store.change(state["id"], "avaliacao", state["version"], "answer",
                                 {"question_id": question_id, "value": value})
        frames = {"inicio": state}
        for index, step in enumerate(case.get("steps", []), 1):
            operation = step["operation"]
            if operation == "attachment":
                state = store.change(state["id"], "avaliacao", state["version"], operation,
                                     {"request_id": step["request_id"], "occurrence_confirmed": step["occurrence_confirmed"]},
                                     step["content"].encode("utf-8"), step["filename"])
            else:
                state = store.change(state["id"], "avaliacao", state["version"], operation, step)
            frames[str(index)] = state
        return state, frames
