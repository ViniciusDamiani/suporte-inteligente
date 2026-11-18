"""Compara FTS e busca híbrida usando o modelo local real e corpus sintético."""
import argparse
import json
import sqlite3
import sys
import tempfile
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from api.services.ticket_service import is_successful
from knowledge_import.storage import connect
from knowledge_search.config import SearchError, Settings
from knowledge_search.documents import digest
from knowledge_search.embeddings import get_embedder
from knowledge_search.service import SearchService
from knowledge_search.storage import build

from .metrics import average, check, retrieval_metrics
from .reports import write
from .runner import DEFAULT_CORPUS, DEFAULT_SUITE, ROOT, code_fingerprints, sha256, summarize
from .validation import read_json, validate


def fixture(path, corpus):
    """Snapshot descartável com o mesmo envelope lido pela busca; sem Firebase."""
    with closing(connect(path)) as db, db:
        db.execute("INSERT INTO snapshots VALUES ('eval','evaluation','v1','synthetic','now','{}')")
        for record in corpus:
            eligible = is_successful(record)
            value = {"tipo": "caso_ticket", "dados": {"assunto": record["title"], "problema_relatado": record["description"], "solucao_documentada": record["resolution"]},
                     "metadados": {"disponivel_pesquisa": eligible, "apto_recomendacao_automatica": False, "uso_na_recomendacao": "hipotese_para_investigacao"},
                     "origem": {"arquivo_relativo": "evaluation/data/corpus.v1.json", "registro_id": record["id"]}}
            raw = json.dumps(value, ensure_ascii=False)
            fingerprint = digest(raw)
            db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?)", ("evaluation", record["id"], fingerprint, "conhecimento", raw, int(eligible)))
            db.execute("INSERT INTO membership VALUES (?,?,?,?)", ("eval", "evaluation", record["id"], fingerprint))
        db.execute("INSERT INTO active_packages VALUES ('evaluation','eval')")


def evaluate(settings=None):
    suite, corpus = validate(read_json(DEFAULT_SUITE), read_json(DEFAULT_CORPUS))
    settings = settings or Settings.from_env()
    embedder = get_embedder(settings)
    started = datetime.now(timezone.utc).isoformat()
    results, baseline = [], []
    with tempfile.TemporaryDirectory(prefix="hybrid-eval-") as folder:
        folder = Path(folder)
        settings = replace(settings, source=folder / "source.sqlite3", index=folder / "hybrid.sqlite3")
        fixture(settings.source, corpus)
        textual_settings = replace(settings, index=folder / "text.sqlite3")
        build(textual_settings)
        build(settings, embedder)
        service = SearchService(settings, lambda _: embedder)
        lexical = SearchService(textual_settings)
        for case in suite["cases"]:
            if case["kind"] != "search":
                continue
            expected = case["expected"]
            result = {"id": case["id"], "kind": "search", "title": case["title"], "expected": expected}
            try:
                try:
                    actual, status = service.search(case["query"], 5), 200
                except SearchError as exc:
                    if exc.status != 400:
                        raise
                    actual, status = {"results": [], "error": str(exc), "generated_answer": None}, exc.status
                try:
                    lexical_result = lexical.search(case["query"], 5)
                except SearchError as exc:
                    if exc.status != 400:
                        raise
                    lexical_result = {"results": []}
                ids = [r["source_id"] for r in actual["results"]]
                text_ids = [r["source_id"] for r in lexical_result["results"]]
                baseline.append({"id": case["id"], "ids": text_ids, "metrics": retrieval_metrics(text_ids, expected["relevant_ids"])})
                checks = [check("status_http", expected.get("http_status", 200), status),
                          check("sem_duplicatas", True, len(ids) == len(set(ids))),
                          check("itens_proibidos_ausentes", [], sorted(set(ids) & set(expected.get("forbidden_ids", [])))),
                          check("sem_resposta_llm_simulada", None, actual["generated_answer"])]
                if status == 200:
                    checks.append(check("busca_hibrida_ativa", "hybrid", actual["mode"]))
                if expected["relevant_ids"]:
                    checks.append(check("fontes_pertinentes", [], sorted(set(expected["relevant_ids"]) - set(ids[:expected.get("top_k", 5)]))))
                else:
                    checks.append(check("abstencao", [], ids))
                if expected.get("error_contains"):
                    checks.append(check("orientacao_entrada", True, expected["error_contains"].casefold() in actual.get("error", "").casefold()))
                faithful = all(service.document(r["document_key"])["body"][r["start"]:r["end"]] == r["excerpt"] for r in actual["results"])
                checks.append(check("trecho_fiel_fonte", True, faithful))
                result.update(actual={**actual, "textual_ids": text_ids}, metrics=retrieval_metrics(ids, expected["relevant_ids"]), checks=checks,
                              passed=all(c["passed"] for c in checks), response_passed=faithful and actual["generated_answer"] is None)
            except Exception as exc:
                result.update(error=f"{type(exc).__name__}: {exc}", checks=[], passed=False, response_passed=False,
                              metrics=retrieval_metrics([], expected["relevant_ids"]))
                if result["metrics"]["empty_correct"] is not None:
                    result["metrics"]["empty_correct"] = 0.0
            results.append(result)
    summary = summarize(results, {"recall@5": .90, "empty_correct": 1.0, "response_pass_rate": 1.0})
    baseline_metrics = {name: average([r["metrics"][name] for r in baseline]) for name in retrieval_metrics([], ["x"])}
    return {"schema_version": 1, "created_at": started,
            "suite": {"id": "local_hybrid_v1", "version": "1.0.0", "review_status": "rascunho_sintetico",
                      "purpose": "Modelo de embeddings real, textos sintéticos. Não representa homologação do acervo do cliente."},
            "inputs": {"suite_sha256": sha256(DEFAULT_SUITE), "corpus_sha256": sha256(DEFAULT_CORPUS)},
            "code_sha256": code_fingerprints(), "python_version": sys.version.split()[0],
            "configuration": {"model": embedder.key, "min_similarity": settings.min_similarity, "fusion": "RRF k=60", "search_limit": 5},
            "execution_mode": "offline_real_embeddings_synthetic_corpus", "cases": results, "summary": summary,
            "pending_coverage": [{"id": "real_gold_set", "reason": "Selecionar e rotular casos reais com especialista; medir desempenho no computador do cliente."},
                                 {"id": "gemini", "reason": "Integração com API da LLM adiada pelo usuário; não houve geração de respostas."}],
            "comparison": {"textual_metrics": baseline_metrics,
                           "hybrid_metrics": {k: v["value"] for k, v in summary["metrics"].items()}, "textual_cases": baseline}}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Avaliação de busca híbrida com embeddings locais reais.")
    parser.add_argument("--saida", type=Path)
    args = parser.parse_args(argv)
    output = args.saida or ROOT / "instance/evaluation" / ("hybrid-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    try:
        if output.exists():
            raise ValueError("Informe uma pasta nova para preservar o relatório anterior.")
        report = evaluate()
        write(report, output)
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        print(f"Relatório: {(output / 'relatorio.html').resolve()}")
        return 0 if report["summary"]["quality_passed"] else 1
    except (SearchError, OSError, ValueError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
