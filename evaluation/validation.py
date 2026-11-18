"""Contrato fechado para impedir expectativas ignoradas ou casos vazios."""
import json
import math

from evaluation.legacy_triage.attachments import PATTERNS
from evaluation.legacy_triage.engine import answer, new_state
from evaluation.legacy_triage.model import load_models


class EvaluationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise EvaluationError(message)


def fields(value, required, optional=()):
    require(isinstance(value, dict), "Esperado objeto JSON.")
    require(set(required) <= value.keys(), f"Campos obrigatórios: {sorted(set(required) - value.keys())}")
    require(value.keys() <= set(required) | set(optional), f"Campos desconhecidos: {sorted(value.keys() - set(required) - set(optional))}")


def strings(value):
    require(isinstance(value, list) and all(isinstance(v, str) and v for v in value), "Esperada lista de textos não vazios.")
    require(len(value) == len(set(value)), "Lista contém valores repetidos.")


def nonempty(value):
    require(isinstance(value, str) and value.strip(), "Texto obrigatório.")


def integer(value, minimum=0, maximum=None):
    require(type(value) is int and value >= minimum and (maximum is None or value <= maximum), "Inteiro fora do intervalo permitido.")


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"Chave JSON repetida: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise EvaluationError(f"Número JSON inválido: {value}")

    try:
        return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=pairs, parse_constant=invalid)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"Não foi possível ler {path.name}: {exc}") from exc


SEARCH_EXPECTED = {"relevant_ids", "top_k", "forbidden_ids", "http_status", "error_contains"}
TRIAGE_EXPECTED = {"status", "diagnosis_confirmed", "closed", "next_question", "request_statuses",
                   "hypothesis_statuses", "requests_absent", "minimum_conflicts", "conflicts",
                   "minimum_missing_context", "attachment_count", "events", "response_contains", "response_excludes"}
THRESHOLDS = {"recall@5", "reciprocal_rank", "empty_correct", "triage_pass_rate", "response_pass_rate"}
REQUEST_STATUSES = {"evidencia_localizada", "indisponivel", "complemento_necessario", "aguardando_anexo"}
CORRELATIONS = {"correlacionado", "origem_nao_confirmada", "periodo_nao_verificado", "fuso_nao_verificado",
                "fora_do_periodo", "unit_divergente", "identificador_nao_verificado"}


def triage_expectation(expected, model):
    fields(expected, (), TRIAGE_EXPECTED)
    require(bool(expected), "Expectativa de triagem vazia.")
    questions = {q["id"] for q in model["questions"]}
    requests = {r["id"] for r in model["evidence_requests"]}
    hypotheses = {h["id"] for h in model["hypotheses"]}
    for key in ("closed", "diagnosis_confirmed"):
        if key in expected:
            require(type(expected[key]) is bool, f"{key} deve ser booleano.")
    if "status" in expected:
        require(expected["status"] in {"em_triagem", "revisar_divergencias", "aguardando_evidencias", "analise_tecnica", "encaminhado"}, "Estado de triagem desconhecido.")
    if "next_question" in expected:
        require(expected["next_question"] is None or expected["next_question"] in questions, "Próxima pergunta desconhecida.")
    for key, identifiers, statuses in (("request_statuses", requests, REQUEST_STATUSES),
                                      ("hypothesis_statuses", hypotheses, {"candidata", "indicio_a_verificar"})):
        if key in expected:
            value = expected[key]
            require(isinstance(value, dict) and bool(value), f"{key} deve ter expectativas.")
            require(value.keys() <= identifiers and all(v in statuses for v in value.values()), f"ID ou estado desconhecido em {key}.")
    if "requests_absent" in expected:
        strings(expected["requests_absent"])
        require(set(expected["requests_absent"]) <= requests, "Pedido ausente desconhecido.")
        require(not set(expected["requests_absent"]) & expected.get("request_statuses", {}).keys(), "Expectativas contraditórias para pedido.")
    for key in ("minimum_conflicts", "conflicts", "minimum_missing_context", "attachment_count"):
        if key in expected:
            integer(expected[key])
    for key in ("response_contains", "response_excludes"):
        if key in expected:
            strings(expected[key])
    if "events" in expected:
        require(isinstance(expected["events"], list) and expected["events"], "Eventos esperados vazios.")
        for event in expected["events"]:
            fields(event, {"type"}, {"correlation", "location", "unit"})
            require(event["type"] in {p[0] for p in PATTERNS}, "Tipo de evento desconhecido.")
            if "correlation" in event:
                require(event["correlation"] in CORRELATIONS, "Correlação desconhecida.")
            if "location" in event:
                nonempty(event["location"])
            if event.get("unit") is not None:
                require(isinstance(event["unit"], str) and event["unit"].isdigit(), "Unit esperada deve ser texto numérico ou nulo.")


def validate(suite, corpus):
    fields(suite, {"schema_version", "id", "version", "review_status", "purpose", "search_limit", "thresholds", "pending_coverage", "setups", "cases"})
    require(type(suite["schema_version"]) is int and suite["schema_version"] == 1, "Versão de contrato desconhecida.")
    for key in ("id", "version", "review_status", "purpose"):
        nonempty(suite[key])
    # Os cortes publicados são 1, 3 e 5. Alterações exigem novo contrato.
    require(type(suite["search_limit"]) is int and suite["search_limit"] == 5, "O contrato v1 avalia cinco resultados.")
    fields(suite["thresholds"], THRESHOLDS)
    for value in suite["thresholds"].values():
        require(type(value) in (float, int) and math.isfinite(value) and 0 <= value <= 1, "Meta deve ficar entre zero e um.")
    require(isinstance(suite["pending_coverage"], list), "Cobertura pendente deve ser lista.")
    pending_ids = set()
    for pending in suite["pending_coverage"]:
        fields(pending, {"id", "reason"})
        nonempty(pending["id"])
        nonempty(pending["reason"])
        require(pending["id"] not in pending_ids, "ID pendente repetido.")
        pending_ids.add(pending["id"])
    require(isinstance(corpus, list) and corpus, "Corpus vazio.")
    corpus_ids = set()
    for record in corpus:
        fields(record, {"id", "title", "description", "status", "resolution", "reopen_count"},
               {"satisfaction", "category", "product", "tags", "helpful_count", "not_helpful_count"})
        for key in ("id", "title", "description"):
            nonempty(record[key])
        require(record["id"] not in corpus_ids, "Ticket duplicado.")
        corpus_ids.add(record["id"])
        require(record["status"] in {"open", "in_progress", "resolved"}, "Status de ticket inválido.")
        require(isinstance(record["resolution"], str), "Solução deve ser texto.")
        integer(record["reopen_count"])
        if record.get("satisfaction") is not None:
            integer(record["satisfaction"], 1, 5)
        for key in ("helpful_count", "not_helpful_count"):
            if key in record:
                integer(record[key])
        for key in ("category", "product"):
            if key in record:
                nonempty(record[key])
        if "tags" in record:
            strings(record["tags"])
    require(isinstance(suite["setups"], dict), "Preparações devem ser objeto.")
    for name, setup in suite["setups"].items():
        nonempty(name)
        require(isinstance(setup, dict), "Preparação deve ser objeto.")
    require(isinstance(suite["cases"], list) and suite["cases"], "Sem cenários.")
    models, case_ids, kinds = load_models(), set(), set()
    for case in suite["cases"]:
        require(isinstance(case, dict), "Cenário deve ser objeto.")
        kind = case.get("kind")
        require(kind in {"search", "triage"}, "Tipo de cenário desconhecido.")
        kinds.add(kind)
        fields(case, {"id", "kind", "title", "expected"} | ({"query"} if kind == "search" else {"model_id", "problem", "steps"}),
               () if kind == "search" else {"setup", "checkpoints"})
        for key in ("id", "title"):
            nonempty(case[key])
        require(case["id"] not in case_ids, "ID de cenário repetido.")
        case_ids.add(case["id"])
        try:
            if kind == "search":
                require(isinstance(case["query"], str), "Consulta deve ser texto.")
                expected = case["expected"]
                fields(expected, {"relevant_ids"}, SEARCH_EXPECTED)
                for key in ("relevant_ids", "forbidden_ids"):
                    strings(expected.get(key, []))
                    require(set(expected.get(key, [])) <= corpus_ids, "Expectativa aponta para ticket inexistente.")
                require(not set(expected["relevant_ids"]) & set(expected.get("forbidden_ids", [])), "Ticket pertinente também proibido.")
                integer(expected.get("top_k", 5), 1, 5)
                integer(expected.get("http_status", 200), 100, 599)
                if "error_contains" in expected:
                    nonempty(expected["error_contains"])
            else:
                require(case["model_id"] in models, "Modelo desconhecido.")
                model = models[case["model_id"]]
                nonempty(case["problem"])
                state = new_state(model, case["problem"])
                if "setup" in case:
                    require(case["setup"] in suite["setups"], "Preparação desconhecida.")
                    for key, value in suite["setups"][case["setup"]].items():
                        answer(state, key, value)
                require(isinstance(case["steps"], list), "Passos devem ser lista.")
                closed = False
                for step in case["steps"]:
                    require(not closed, "Passo após encaminhamento.")
                    require(isinstance(step, dict), "Passo deve ser objeto.")
                    operation = step.get("operation")
                    keys = {"answer": {"question_id", "value"}, "unavailable": {"request_id", "reason"},
                            "attachment": {"request_id", "filename", "occurrence_confirmed", "content"}, "handoff": set()}
                    require(operation in keys, "Operação desconhecida.")
                    fields(step, {"operation"} | keys[operation])
                    if operation == "answer":
                        answer(state, step["question_id"], step["value"])
                    if operation in {"attachment", "unavailable"}:
                        require(step["request_id"] in {r["id"] for r in model["evidence_requests"]}, "Pedido desconhecido.")
                    if operation == "attachment":
                        nonempty(step["filename"])
                        nonempty(step["content"])
                        require(type(step["occurrence_confirmed"]) is bool, "Confirmação deve ser booleana.")
                    if operation == "unavailable":
                        nonempty(step["reason"])
                        require(3 <= len(step["reason"].strip()) <= 1000, "Motivo inválido.")
                    closed = operation == "handoff"
                triage_expectation(case["expected"], model)
                require(isinstance(case.get("checkpoints", []), list), "Checkpoints devem ser lista.")
                afters = set()
                for checkpoint in case.get("checkpoints", []):
                    fields(checkpoint, {"after", "expected"})
                    integer(checkpoint["after"], 1, len(case["steps"]))
                    require(checkpoint["after"] not in afters, "Checkpoint repetido.")
                    afters.add(checkpoint["after"])
                    triage_expectation(checkpoint["expected"], model)
        except (ValueError, TypeError, KeyError) as exc:
            raise EvaluationError(f"{case['id']}: {exc}") from exc
    require(kinds == {"search", "triage"}, "A suíte deve conter busca e triagem.")
    require(any(c["expected"]["relevant_ids"] for c in suite["cases"] if c["kind"] == "search"), "Sem consultas positivas.")
    require(any(not c["expected"]["relevant_ids"] for c in suite["cases"] if c["kind"] == "search"), "Sem consultas negativas.")
    return suite, corpus
