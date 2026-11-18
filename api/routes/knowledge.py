import sqlite3
import threading

from flask import Blueprint, current_app, g, jsonify, request

from api.decorators import require_token_request
from knowledge_search.config import SearchError
from knowledge_search.service import SearchService
from knowledge_search.generation import GeminiGenerator
from knowledge_search.conversation import ConversationStore, reply

knowledge_bp = Blueprint("knowledge", __name__, url_prefix="/knowledge")
_lock = threading.Lock()


def service():
    # Instância por aplicação: mantém uma única matriz vetorial e modelo por processo.
    with _lock:
        if "knowledge_search" not in current_app.extensions:
            current_app.extensions["knowledge_search"] = SearchService(current_app.config["KNOWLEDGE_SEARCH_SETTINGS"])
        return current_app.extensions["knowledge_search"]


def generator():
    with _lock:
        if "knowledge_generator" not in current_app.extensions:
            current_app.extensions["knowledge_generator"] = GeminiGenerator(current_app.config["GEMINI_SETTINGS"])
        return current_app.extensions["knowledge_generator"]


@knowledge_bp.errorhandler(SearchError)
def invalid(error):
    return jsonify(error=str(error)), error.status


@knowledge_bp.errorhandler(sqlite3.Error)
@knowledge_bp.errorhandler(OSError)
def storage_error(error):
    current_app.logger.error("Falha no acervo local: %s", type(error).__name__)
    return jsonify(error="Não foi possível acessar o acervo. Confira a preparação da busca no servidor."), 503


@knowledge_bp.get("/status")
@require_token_request
def status():
    return jsonify({**service().status(), "generation_status": current_app.config["GEMINI_SETTINGS"].status()})


@knowledge_bp.post("/search")
@require_token_request
def search():
    return jsonify(retrieve())


def retrieve():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.keys() - {"query", "limit"}:
        raise SearchError("Envie query e, opcionalmente, limit.", 400)
    query = data.get("query", "")
    if not isinstance(query, str) or len(query) > 2000:
        raise SearchError("Consulta inválida; use até 2.000 caracteres.", 400)
    result = service().search(query, data.get("limit", 8))
    result["generation_available"] = current_app.config["GEMINI_SETTINGS"].status() == "ready"
    return result


@knowledge_bp.post("/answer")
@require_token_request
def answer():
    # Reconsulta a base; não aceita fontes do navegador.
    return jsonify(generator().generate(retrieve()))


@knowledge_bp.post("/conversation")
@require_token_request
def conversation():
    settings = current_app.config["KNOWLEDGE_SEARCH_SETTINGS"]
    path = current_app.config.get("KNOWLEDGE_CONVERSATION_DATABASE", settings.index.parent / "conversations.sqlite3")
    return jsonify(reply(ConversationStore(path), service(), generator(), g.current_user.id,
                         request.get_json(silent=True)))


@knowledge_bp.get("/documents/<key>")
@require_token_request
def document(key):
    return jsonify(service().document(key))
