"""Conversa declarativa; observações e evidências permanecem separadas."""
import copy
import re
from datetime import date, datetime, time, timedelta, timezone

from .attachments import clean_text
from .model import check


def now():
    return datetime.now(timezone.utc).isoformat()


def matches(condition, answers, events=(), unavailable=None):
    if not condition:
        return True
    if "question" in condition:
        return answers.get(condition["question"]) == condition["equals"]
    if "event" in condition:
        return condition["event"] in events
    if "unavailable" in condition:
        return condition["unavailable"] in (unavailable or {})
    return False


def active_answers(state):
    active = {}
    for question in state["model"]["questions"]:
        if question["id"] in state["answers"] and matches(question.get("when"), active):
            active[question["id"]] = state["answers"][question["id"]]
    return active


def validate_answer(question, value):
    if value is None:
        return None
    check(isinstance(value, str) and 0 < len(value.strip()) <= 2000, "Resposta deve ter entre 1 e 2.000 caracteres.")
    value = value.strip()
    kind = question["type"]
    if kind == "choice":
        check(value in {option["value"] for option in question["options"]}, "Escolha uma das respostas disponíveis.")
    if kind == "date":
        check(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)), "Informe a data no formato AAAA-MM-DD.")
        try:
            date.fromisoformat(value)
        except ValueError:
            check(False, "Data inválida.")
    if kind == "time":
        check(bool(re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", value)), "Informe o horário como HH:MM ou HH:MM:SS.")
        try:
            time.fromisoformat(value)
        except ValueError:
            check(False, "Horário inválido.")
    if kind == "identifiers":
        check(bool(re.fullmatch(r"\d{1,12}(?:\s*[,;]\s*\d{1,12})*", value)), "Informe os códigos numéricos das Units separados por vírgula.")
        value = ",".join(dict.fromkeys(str(int(part.strip())) for part in re.split(r"[,;]", value)))
    return clean_text(value)


def new_state(model, problem):
    check(isinstance(problem, str) and 3 <= len(problem.strip()) <= 4000, "Descreva a ocorrência em 3 a 4.000 caracteres.")
    return {"model": copy.deepcopy(model), "problem": clean_text(problem.strip()), "answers": {},
            "attachments": [], "unavailable": {}, "history": [], "closed": False, "created_at": now()}


def answer(state, question_id, value):
    check(not state["closed"], "Atendimento encaminhado; inicie uma nova sessão.", 409)
    question = next((q for q in state["model"]["questions"] if q["id"] == question_id), None)
    check(question is not None, "Pergunta não encontrada.")
    answers = active_answers(state)
    check(matches(question.get("when"), answers), "Esta pergunta não se aplica às respostas atuais.")
    value = validate_answer(question, value)
    previous = state["answers"].get(question_id)
    was_answered = question_id in state["answers"]
    state["answers"][question_id] = value
    if question_id in ("cliente", "versao") and previous != value:
        for attachment in state["attachments"]:
            attachment["occurrence_confirmed"] = False
    # Quando a condição deixa de valer, a resposta dependente deve ser coletada
    # novamente se o ramo for reaberto. A resposta antiga permanece na auditoria.
    active = active_answers(state)
    for key in list(state["answers"]):
        if key not in active:
            del state["answers"][key]
    state["history"].append({"at": now(), "kind": "correcao" if was_answered else "resposta",
                             "question_id": question_id, "value": value, "previous": previous})


def _window(answers):
    if not all(answers.get(key) for key in ("data", "inicio", "fim")):
        return None
    start = datetime.fromisoformat(answers["data"] + "T" + answers["inicio"])
    end = datetime.fromisoformat(answers["data"] + "T" + answers["fim"])
    if end < start:
        end += timedelta(days=1)
    return start, end


def attachment_view(attachment, answers):
    result = copy.deepcopy(attachment)
    window = _window(answers)
    units = set(answers.get("units", "").split(",")) if answers.get("units") else set()
    for event in result["findings"]:
        stamp = datetime.fromisoformat(event["timestamp"]) if event["timestamp"] else None
        if not attachment["occurrence_confirmed"] or not answers.get("cliente") or not answers.get("versao"):
            correlation = "origem_nao_confirmada"
        elif not window or not stamp:
            correlation = "periodo_nao_verificado"
        elif stamp.tzinfo is not None:
            correlation = "fuso_nao_verificado"
        elif not window[0] <= stamp <= window[1]:
            correlation = "fora_do_periodo"
        elif event["unit"] is not None and units and str(int(event["unit"])) not in units:
            correlation = "unit_divergente"
        elif not units or event["unit"] is None:
            correlation = "identificador_nao_verificado"
        else:
            correlation = "correlacionado"
        event["correlation"] = correlation
        event["attachment_id"] = attachment["id"]
        event["attachment_name"] = attachment["name"]
    return result


def view(state):
    model, answers = state["model"], active_answers(state)
    applicable = [q for q in model["questions"] if matches(q.get("when"), answers)]
    next_question = next((q for q in applicable if q["id"] not in answers), None)
    attachments = [attachment_view(a, answers) for a in state["attachments"]]
    events = [e for a in attachments for e in a["findings"]]
    trusted_events = [e for e in events if e["correlation"] == "correlacionado"]
    event_types = {e["type"] for e in trusted_events}
    requests = []
    for definition in model["evidence_requests"]:
        relevant = definition.get("always") or matches(definition.get("when"), answers, event_types, state["unavailable"])
        if not relevant:
            continue
        # Um arquivo pode atender a mais de um pedido. Reutilize os trechos já
        # encontrados antes de solicitar um novo upload da mesma informação.
        received = [a for a in attachments if a["request_id"] == definition["id"]
                    or any(e["type"] in definition["event_types"] for e in a["findings"])]
        matching = [e for a in received for e in a["findings"] if e["type"] in definition["event_types"] and e["correlation"] == "correlacionado"]
        if matching and not any(a["truncated"] for a in received):
            status = "evidencia_localizada"
        elif definition["id"] in state["unavailable"]:
            status = "indisponivel"
        elif received:
            status = "complemento_necessario"
        else:
            status = "aguardando_anexo"
        requests.append({**definition, "status": status, "attachment_ids": [a["id"] for a in received],
                         "evidence_ids": [e["id"] for e in matching], "unavailable_reason": state["unavailable"].get(definition["id"])})
    missing = [q["text"] for q in applicable if q.get("context") and not answers.get(q["id"])]
    conflicts = []
    if answers.get("alarme") == "nao":
        for event in trusted_events:
            if event["type"] == "alarm":
                conflicts.append({"question_id": "alarme", "evidence_id": event["id"],
                                  "message": "O relato informa ausência de alarme; um registro menciona alarme/intertravamento. Confira o estado e o significado antes de concluir."})
    for event in events:
        if event["correlation"] in ("fora_do_periodo", "unit_divergente"):
            conflicts.append({"evidence_id": event["id"], "message": "Registro com período ou Unit diferente do contexto informado."})
    conflicts = conflicts[:50]
    ready_requests = {r["id"] for r in requests if r["status"] == "evidencia_localizada"}
    hypotheses = []
    for hypothesis in model["hypotheses"]:
        support = [e["id"] for e in trusted_events if e["type"] in hypothesis.get("support_events", [])]
        hypotheses.append({**hypothesis, "status": "indicio_a_verificar" if support else "candidata",
                           "support_evidence_ids": support,
                           "missing_requests": [r for r in hypothesis["requires"] if r not in ready_requests]})
    if state["closed"]:
        status, message = "encaminhado", "Triagem encaminhada para análise técnica com o relato, as evidências e as lacunas registradas."
    elif next_question:
        status, message = "em_triagem", next_question["text"]
    elif conflicts:
        status, message = "revisar_divergencias", "Há divergências entre o contexto, o relato e os anexos. Confira as referências e corrija ou complemente as informações."
    elif any(r["status"] in ("aguardando_anexo", "complemento_necessario") for r in requests):
        status, message = "aguardando_evidencias", "Envie os anexos indicados ou registre quais estão indisponíveis. Arquivos recebidos com lacunas precisam apenas de complemento."
    else:
        status, message = "analise_tecnica", "A coleta foi registrada. A causa e a aplicabilidade de qualquer correção precisam de análise técnica."
    return {"model_id": model["id"], "model_version": model["version"], "title": model["title"],
            "source": model.get("source"), "problem": state["problem"], "status": status, "message": message,
            "next_question": None if state["closed"] else next_question,
            "answers": [{**q, "value": answers[q["id"]]} for q in applicable if q["id"] in answers],
            "requests": requests, "attachments": attachments, "hypotheses": hypotheses,
            "missing_context": missing, "conflicts": conflicts, "limits": model["limits"],
            "history": state["history"], "closed": state["closed"], "diagnosis_confirmed": False}
