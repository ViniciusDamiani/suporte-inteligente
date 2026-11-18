"""Métricas de recuperação e verificações independentes das saídas esperadas."""


def retrieval_metrics(predicted, relevant, cutoffs=(1, 3, 5)):
    # Duplicatas nunca contam como novos acertos nem melhoram a posição relevante.
    metrics = {}
    relevant = set(relevant)
    for cutoff in cutoffs:
        hits = len(set(predicted[:cutoff]) & relevant)
        metrics[f"precision@{cutoff}"] = hits / cutoff
        metrics[f"recall@{cutoff}"] = hits / len(relevant) if relevant else None
        metrics[f"hit@{cutoff}"] = float(hits > 0) if relevant else None
    rank = next((index for index, identifier in enumerate(predicted, 1) if identifier in relevant), None)
    metrics["reciprocal_rank"] = (1 / rank if rank else 0.0) if relevant else None
    metrics["empty_correct"] = float(not predicted) if not relevant else None
    return metrics


def check(name, expected, actual, passed=None):
    return {"name": name, "expected": expected, "actual": actual,
            "passed": actual == expected if passed is None else bool(passed)}


def assess_search(case, result, corpus):
    expected = case["expected"]
    documents = {record["id"]: record for record in corpus}
    ids = [item["ticket_id"] for item in result["results"]]
    relevant = expected["relevant_ids"]
    top_k = expected.get("top_k", 5)
    checks = [check("status_http", expected.get("http_status", 200), result["http_status"]),
              check("sem_duplicatas", True, len(set(ids)) == len(ids)),
              check("referencias_existentes", True, set(ids) <= documents.keys()),
              check("itens_proibidos_ausentes", [], sorted(set(ids) & set(expected.get("forbidden_ids", []))))]
    if relevant:
        missed = sorted(set(relevant) - set(ids[:top_k]))
        checks.append(check(f"relevantes_entre_{top_k}", [], missed))
    else:
        checks.append(check("abstencao_sem_resultado_pertinente", [], ids))
    # A resposta atual é extrativa: a solução exibida deve ser a da fonte retornada.
    grounded = all(item["ticket_id"] in documents and item.get("resolution") == documents[item["ticket_id"]].get("resolution") for item in result["results"])
    checks.append(check("resposta_fiel_ao_ticket", True, grounded))
    if "error_contains" in expected:
        checks.append(check("orientacao_entrada_invalida", expected["error_contains"], result.get("error"),
                            expected["error_contains"].casefold() in (result.get("error") or "").casefold()))
    return checks, retrieval_metrics(ids, relevant)


def assess_triage(expected, result):
    checks = []
    for field in ("status", "diagnosis_confirmed", "closed"):
        if field in expected:
            checks.append(check(field, expected[field], result.get(field)))
    if "next_question" in expected:
        checks.append(check("proxima_pergunta", expected["next_question"], (result.get("next_question") or {}).get("id")))
    requests = {r["id"]: r for r in result["requests"]}
    hypotheses = {h["id"]: h for h in result["hypotheses"]}
    for identifier, status in expected.get("request_statuses", {}).items():
        checks.append(check("pedido_" + identifier, status, requests.get(identifier, {}).get("status")))
    for identifier, status in expected.get("hypothesis_statuses", {}).items():
        checks.append(check("hipotese_" + identifier, status, hypotheses.get(identifier, {}).get("status")))
    if "requests_absent" in expected:
        checks.append(check("pedidos_desnecessarios_ausentes", [], sorted(set(expected["requests_absent"]) & requests.keys())))
    if "minimum_conflicts" in expected:
        checks.append(check("divergencias_identificadas", expected["minimum_conflicts"], len(result["conflicts"]), len(result["conflicts"]) >= expected["minimum_conflicts"]))
    if "conflicts" in expected:
        checks.append(check("numero_divergencias", expected["conflicts"], len(result["conflicts"])))
    if "minimum_missing_context" in expected:
        checks.append(check("lacunas_preservadas", expected["minimum_missing_context"], len(result["missing_context"]), len(result["missing_context"]) >= expected["minimum_missing_context"]))
    if "attachment_count" in expected:
        checks.append(check("quantidade_anexos", expected["attachment_count"], len(result["attachments"])))
    events = {event["id"]: event for attachment in result["attachments"] for event in attachment["findings"]}
    for wanted in expected.get("events", []):
        match = any(all(event.get(key) == value for key, value in wanted.items()) for event in events.values())
        checks.append(check("evento_esperado", wanted, match, match))
    # Verificações de resposta aplicadas a todos os cenários, inclusive negativos.
    request_citations = [cid for request in result["requests"] for cid in request["evidence_ids"]]
    hypothesis_citations = [cid for h in result["hypotheses"] for cid in h.get("support_evidence_ids", [])]
    conflict_citations = [c["evidence_id"] for c in result["conflicts"] if "evidence_id" in c]
    citations = request_citations + hypothesis_citations + conflict_citations
    checks.append(check("citacoes_existentes", True, all(cid in events for cid in citations)))
    event_list = [e for a in result["attachments"] for e in a["findings"]]
    checks.append(check("eventos_sem_ids_repetidos", True, len(events) == len(event_list)))
    checks.append(check("fundamentacao_correlacionada", True, all(events.get(cid, {}).get("correlation") == "correlacionado" for cid in request_citations + hypothesis_citations)))
    attachment_ids = {a["id"] for a in result["attachments"]}
    checks.append(check("trechos_rastreaveis", True, all(e.get("attachment_id") == a["id"] and bool(e.get("location")) and bool(e.get("snippet")) for a in result["attachments"] for e in a["findings"])))
    checks.append(check("anexos_referenciados_existentes", True, all(set(r["attachment_ids"]) <= attachment_ids for r in result["requests"])))
    checks.append(check("evidencia_localizada_tem_fonte", True, all(r["evidence_ids"] for r in result["requests"] if r["status"] == "evidencia_localizada")))
    checks.append(check("indicio_tem_fonte", True, all(h["support_evidence_ids"] for h in result["hypotheses"] if h["status"] == "indicio_a_verificar")))
    checks.append(check("diagnostico_nao_inventado", False, result.get("diagnosis_confirmed")))
    # Trechos de arquivos são citações; não são instruções produzidas pelo sistema.
    generated = "\n".join([result.get("message", "")] + [e["interpretation"] for e in events.values()]).casefold()
    for text in expected.get("response_contains", []):
        checks.append(check("mensagem_necessaria", text, text.casefold() in generated, text.casefold() in generated))
    for text in expected.get("response_excludes", []):
        checks.append(check("afirmacao_proibida_ausente", text, text.casefold() not in generated, text.casefold() not in generated))
    return checks


def average(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None
