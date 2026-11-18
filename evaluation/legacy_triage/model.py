import json
from pathlib import Path


class TriageError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def check(condition, message, status=400):
    if not condition:
        raise TriageError(message, status)


def validate_model(model):
    check(isinstance(model, dict) and model.get("schema_version") == 1, "Contrato de triagem inválido.")
    for key in ("id", "version", "title"):
        check(isinstance(model.get(key), str) and bool(model[key]), f"Modelo sem {key}.")
    questions = model.get("questions")
    requests = model.get("evidence_requests")
    check(isinstance(questions, list) and questions and isinstance(requests, list), "Perguntas e pedidos obrigatórios.")
    question_ids, request_ids = set(), set()
    for question in questions:
        check(isinstance(question, dict) and isinstance(question.get("id"), str), "Pergunta inválida.")
        check(question["id"] not in question_ids, "ID de pergunta repetido.")
        check(question.get("type") in ("text", "date", "time", "identifiers", "choice"), "Tipo de pergunta inválido.")
        check(isinstance(question.get("text"), str) and question["text"], "Pergunta sem texto.")
        if question["type"] == "choice":
            options = question.get("options", [])
            check(options and all(isinstance(o, dict) and isinstance(o.get("value"), str) and isinstance(o.get("label"), str) for o in options), "Opções inválidas.")
            check(len({o["value"] for o in options}) == len(options), "Opção repetida.")
        condition = question.get("when")
        if condition:
            check(set(condition) == {"question", "equals"} and condition["question"] in question_ids,
                  "Condição deve referenciar pergunta anterior; ciclos não são permitidos.")
        question_ids.add(question["id"])
    for request in requests:
        check(isinstance(request, dict) and isinstance(request.get("id"), str), "Pedido inválido.")
        check(request["id"] not in request_ids, "Pedido de evidência repetido.")
        request_ids.add(request["id"])
    for request in requests:
        check(all(isinstance(request.get(k), str) and request[k] for k in ("title", "message", "alternative")), "Pedido incompleto.")
        check(isinstance(request.get("event_types"), list), "Tipos de eventos obrigatórios.")
        condition = request.get("when")
        if condition:
            check(isinstance(condition, dict), "Condição inválida.")
            check((set(condition) == {"question", "equals"} and condition["question"] in question_ids)
                  or (set(condition) == {"unavailable"} and condition["unavailable"] in request_ids)
                  or (set(condition) == {"event"} and isinstance(condition["event"], str)), "Condição desconhecida.")
    for hypothesis in model.get("hypotheses", []):
        check(set(hypothesis.get("requires", [])) <= request_ids, "Hipótese aponta para evidência inexistente.")
    return model


def load_models(directory=None):
    folder = Path(directory) if directory else Path(__file__).parent / "models"
    models = {}
    for path in sorted(folder.glob("*.json")):
        model = validate_model(json.loads(path.read_text(encoding="utf-8")))
        check(model["id"] not in models, "ID de modelo duplicado.")
        models[model["id"]] = model
    return models
