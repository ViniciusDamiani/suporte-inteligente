"""Avaliação offline dos serviços atuais, com trilha das expectativas e resultados."""
import hashlib
import platform
from datetime import datetime, timezone
from pathlib import Path

from api.config import Config
from api.services.suggestion_service import MAX_CANDIDATES, MAX_QUERY_TERMS

from . import adapters
from .metrics import assess_search, assess_triage, average, check, retrieval_metrics
from .validation import EvaluationError, read_json, require, validate

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SUITE = ROOT / "evaluation/data/scenarios.v1.json"
DEFAULT_CORPUS = ROOT / "evaluation/data/corpus.v1.json"
RESPONSE_CHECKS = {"resposta_fiel_ao_ticket", "referencias_existentes", "orientacao_entrada_invalida",
                   "citacoes_existentes", "fundamentacao_correlacionada", "trechos_rastreaveis",
                   "diagnostico_nao_inventado", "mensagem_necessaria", "afirmacao_proibida_ausente",
                   "eventos_sem_ids_repetidos", "anexos_referenciados_existentes",
                   "evidencia_localizada_tem_fonte", "indicio_tem_fonte"}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_fingerprints():
    paths = sorted({p for folder in ("api", "evaluation", "knowledge_search") for p in (ROOT / folder).rglob("*.py")}
                   | set((ROOT / "evaluation/legacy_triage/models").glob("*.json")) | {ROOT / "requirements.txt"})
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in paths}


def response_trace(state):
    return {key: state[key] for key in ("status", "message", "next_question", "answers", "requests", "hypotheses", "attachments", "missing_context", "conflicts", "diagnosis_confirmed", "closed")}


def execute(suite, corpus):
    results = []
    for case in suite["cases"]:
        result = {"id": case["id"], "kind": case["kind"], "title": case["title"], "expected": case["expected"]}
        try:
            if case["kind"] == "search":
                actual = adapters.search(case, corpus, suite["search_limit"])
                checks, metrics = assess_search(case, actual, corpus)
                result.update(actual=actual, metrics=metrics)
            else:
                state, frames = adapters.triage(case, suite["setups"].get(case.get("setup"), {}))
                expectations = {str(cp["after"]): cp["expected"] for cp in case.get("checkpoints", [])}
                final_frame = str(len(case["steps"])) if case["steps"] else "inicio"
                checks = []
                for frame_id, frame in frames.items():
                    expected = expectations.get(frame_id, {})
                    if frame_id == final_frame:
                        # Checkpoint e resultado final são avaliados separadamente se coexistirem.
                        if expected:
                            checks.extend({**c, "frame": frame_id} for c in assess_triage(expected, frame))
                        expected = case["expected"]
                    checks.extend({**c, "frame": frame_id} for c in assess_triage(expected, frame))
                result.update(actual=response_trace(state), messages=[{"frame": k, "message": v["message"]} for k, v in frames.items()])
            result["checks"] = checks
            result["passed"] = all(c["passed"] for c in checks)
            response_checks = [c for c in checks if c["name"] in RESPONSE_CHECKS]
            result["response_passed"] = bool(response_checks) and all(c["passed"] for c in response_checks)
        except Exception as exc:
            # A falha fica visível e não impede os outros cenários de produzirem diagnóstico.
            result.update(passed=False, response_passed=False, error=f"{type(exc).__name__}: {exc}", checks=[])
            if case["kind"] == "search":
                metrics = retrieval_metrics([], case["expected"]["relevant_ids"])
                # Uma exceção nunca vale como abstenção correta.
                if metrics["empty_correct"] is not None:
                    metrics["empty_correct"] = 0.0
                result["metrics"] = metrics
        results.append(result)
    return results


def summarize(results, thresholds):
    searches = [r for r in results if r["kind"] == "search"]
    triages = [r for r in results if r["kind"] == "triage"]
    metrics = {}
    for name in retrieval_metrics([], ["example"]):
        values = [r["metrics"][name] for r in searches if r["metrics"][name] is not None]
        metrics[name] = {"value": average(values), "n": len(values)}
    for name, values in (("search_pass_rate", [int(r["passed"]) for r in searches]),
                         ("triage_pass_rate", [int(r["passed"]) for r in triages]),
                         ("response_pass_rate", [int(r["response_passed"]) for r in results])):
        metrics[name] = {"value": average(values), "n": len(values)}
    gates = [check(name, threshold, metrics[name]["value"], metrics[name]["value"] is not None and metrics[name]["value"] >= threshold)
             for name, threshold in thresholds.items()]
    passed = sum(r["passed"] for r in results)
    return {"total": len(results), "passed": passed, "failed": len(results) - passed,
            "execution_errors": sum("error" in r for r in results), "metrics": metrics, "gates": gates,
            "quality_passed": passed == len(results) and all(g["passed"] for g in gates)}


def compare(current, previous):
    require(isinstance(previous, dict) and previous.get("schema_version") == 1, "Relatório anterior incompatível.")
    compatible = (current["inputs"] == previous.get("inputs") and current["configuration"] == previous.get("configuration"))
    if not compatible:
        return {"compatible": False, "reason": "Corpus, cenários ou configuração mudaram. Gere uma nova referência; deltas não são comparáveis."}
    old_cases = {c["id"]: c for c in previous["cases"]}
    require(old_cases.keys() == {c["id"] for c in current["cases"]}, "Relatório anterior sem os mesmos cenários.")
    deltas = {}
    for name, metric in current["summary"]["metrics"].items():
        old = previous["summary"]["metrics"][name]["value"]
        deltas[name] = metric["value"] - old if old is not None and metric["value"] is not None else None
    return {"compatible": True, "metric_deltas": deltas,
            "regressions": [c["id"] for c in current["cases"] if old_cases[c["id"]]["passed"] and not c["passed"]],
            "improvements": [c["id"] for c in current["cases"] if not old_cases[c["id"]]["passed"] and c["passed"]]}


def run(suite_path=DEFAULT_SUITE, corpus_path=DEFAULT_CORPUS, previous_path=None):
    suite_path, corpus_path = Path(suite_path), Path(corpus_path)
    try:
        suite, corpus = validate(read_json(suite_path), read_json(corpus_path))
        report = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                  "suite": {k: suite[k] for k in ("id", "version", "review_status", "purpose")},
                  "inputs": {"suite_sha256": sha256(suite_path), "corpus_sha256": sha256(corpus_path)},
                  "code_sha256": code_fingerprints(), "python_version": platform.python_version(),
                  "configuration": {"search_limit": suite["search_limit"], "ticket_success_min_csat": Config.TICKET_SUCCESS_MIN_CSAT,
                                    "max_candidates": MAX_CANDIDATES, "max_query_terms": MAX_QUERY_TERMS},
                  "execution_mode": "offline_synthetic", "pending_coverage": suite["pending_coverage"]}
        report["cases"] = execute(suite, corpus)
        report["summary"] = summarize(report["cases"], suite["thresholds"])
        report["comparison"] = compare(report, read_json(Path(previous_path))) if previous_path else None
        return report
    except (TypeError, KeyError, OSError) as exc:
        raise EvaluationError(f"Contrato ou arquivo inválido: {exc}") from exc
