import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from evaluation import adapters
from evaluation.__main__ import main
from evaluation.metrics import assess_search, assess_triage, retrieval_metrics
from evaluation.reports import render, write
from evaluation.runner import DEFAULT_CORPUS, DEFAULT_SUITE, compare, execute, run, summarize
from evaluation.validation import EvaluationError, read_json, validate


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = read_json(DEFAULT_SUITE)
        cls.corpus = read_json(DEFAULT_CORPUS)
        # A avaliação completa deve funcionar mesmo com rede e Firebase bloqueados.
        with patch("socket.socket.connect", side_effect=AssertionError("Rede proibida")), \
             patch("api.extensions.init_firebase", side_effect=AssertionError("Firebase proibido")):
            cls.report = run()

    def test_metrics_against_hand_calculation_and_duplicates(self):
        m = retrieval_metrics(["x", "b", "a", "b", "z"], ["a", "b", "c"])
        self.assertEqual(0, m["precision@1"])
        self.assertAlmostEqual(2 / 3, m["precision@3"])
        self.assertAlmostEqual(2 / 3, m["recall@5"])
        self.assertEqual(0.4, m["precision@5"])
        self.assertEqual(0.5, m["reciprocal_rank"])
        self.assertIsNone(m["empty_correct"])

    def test_negative_queries_are_not_perfect_recall(self):
        m = retrieval_metrics([], [])
        self.assertIsNone(m["recall@5"])
        self.assertIsNone(m["reciprocal_rank"])
        self.assertEqual(1, m["empty_correct"])
        self.assertEqual(0, retrieval_metrics(["wrong"], [])["empty_correct"])
        self.assertEqual(0.2, retrieval_metrics(["a"], ["a"])["precision@5"])

    def test_runs_real_services_offline_and_exposes_lexical_misses(self):
        self.assertEqual(0, self.report["summary"]["execution_errors"])
        cases = {c["id"]: c for c in self.report["cases"]}
        self.assertTrue(cases["B01"]["passed"])
        self.assertEqual("SYN-001", cases["B01"]["actual"]["results"][0]["ticket_id"])
        self.assertTrue(cases["T16"]["passed"])
        self.assertTrue(any(c.get("frame") == "1" and c["name"] == "pedido_E02" for c in cases["T16"]["checks"]))
        # Essas paráfrases são lacunas conhecidas da busca lexical, não erros do avaliador.
        for identifier in ("B13", "B14"):
            self.assertFalse(cases[identifier]["passed"])
            self.assertEqual([], cases[identifier]["actual"]["results"])
        self.assertFalse(self.report["summary"]["quality_passed"])

    def test_source_fidelity_detects_changed_resolution_and_unknown_reference(self):
        case = self.suite["cases"][0]
        result = adapters.search(case, self.corpus)
        result["results"][0]["resolution"] = "Solução inventada"
        checks, _ = assess_search(case, result, self.corpus)
        self.assertFalse(next(c for c in checks if c["name"] == "resposta_fiel_ao_ticket")["passed"])
        result["results"][0]["ticket_id"] = "inexistente"
        checks, _ = assess_search(case, result, self.corpus)
        self.assertFalse(next(c for c in checks if c["name"] == "referencias_existentes")["passed"])

    def test_response_invariants_detect_corrupt_citation_and_diagnosis(self):
        result = copy.deepcopy(next(c["actual"] for c in self.report["cases"] if c["id"] == "T06"))
        result["requests"][0]["evidence_ids"] = ["fonte-inexistente"]
        result["diagnosis_confirmed"] = True
        result["attachments"][0]["findings"][0]["location"] = ""
        failures = {c["name"] for c in assess_triage({}, result) if not c["passed"]}
        self.assertTrue({"citacoes_existentes", "fundamentacao_correlacionada", "diagnostico_nao_inventado", "trechos_rastreaveis"} <= failures)

    def test_silent_orphan_indication_fails(self):
        result = copy.deepcopy(next(c["actual"] for c in self.report["cases"] if c["id"] == "T10"))
        hypothesis = next(h for h in result["hypotheses"] if h["id"] == "H04")
        hypothesis["support_evidence_ids"] = []
        failures = {c["name"] for c in assess_triage({}, result) if not c["passed"]}
        self.assertIn("indicio_tem_fonte", failures)

    def test_validation_rejects_unknown_expectation_duplicate_ids_and_references(self):
        changes = [
            lambda s: s["cases"][0]["expected"].update(relevent_ids=[]),
            lambda s: s["cases"].append(copy.deepcopy(s["cases"][0])),
            lambda s: s["cases"][0]["expected"].update(relevant_ids=["absent"]),
            lambda s: s["cases"][0]["expected"].update(forbidden_ids=["SYN-001"]),
            lambda s: s["cases"][-1]["expected"].update(request_statuses={"E99": "aguardando_anexo"}),
            lambda s: s["cases"][-1].update(checkpoints=[{"after": 9, "expected": {"closed": False}}]),
            lambda s: s["cases"][-1]["steps"][0].update(operation="typo"),
            lambda s: s["thresholds"].update({"recall@5": float("nan")}),
            lambda s: s["cases"][-1]["expected"].update({"events": [{"type": "write_skipped", "correllation": "correlacionado"}]}),
        ]
        for change in changes:
            with self.subTest(change=change):
                suite = copy.deepcopy(self.suite)
                change(suite)
                with self.assertRaises(EvaluationError):
                    validate(suite, self.corpus)
        with self.assertRaises(EvaluationError):
            validate(self.suite, self.corpus + [self.corpus[0]])

    def test_json_duplicate_keys_and_nan_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "suite.json"
            for text in ('{"id":1,"id":2}', '{"value":NaN}'):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(EvaluationError):
                    read_json(path)

    def test_execution_errors_are_not_skipped_or_counted_as_abstention(self):
        suite = copy.deepcopy(self.suite)
        suite["cases"] = [c for c in suite["cases"] if c["id"] in ("B01", "B10", "T01")]
        with patch.object(adapters, "search", side_effect=RuntimeError("falha simulada")):
            results = execute(suite, self.corpus)
        summary = summarize(results, suite["thresholds"])
        self.assertEqual(2, summary["execution_errors"])
        self.assertEqual(3, summary["total"])
        self.assertEqual(0, summary["metrics"]["empty_correct"]["value"])
        self.assertAlmostEqual(1 / 3, summary["metrics"]["response_pass_rate"]["value"])

    def test_comparison_rejects_changed_inputs_and_detects_regressions(self):
        current = copy.deepcopy(self.report)
        current["cases"][0]["passed"] = False
        current["summary"]["metrics"]["recall@5"]["value"] -= 0.1
        result = compare(current, self.report)
        self.assertTrue(result["compatible"])
        self.assertEqual(["B01"], result["regressions"])
        self.assertAlmostEqual(-0.1, result["metric_deltas"]["recall@5"])
        current["inputs"]["suite_sha256"] = "different"
        self.assertFalse(compare(current, self.report)["compatible"])

    def test_reports_escape_content_and_preserve_existing_output(self):
        report = copy.deepcopy(self.report)
        report["cases"][0]["title"] = '<script>alert("x")</script>'
        page = render(report)
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "new"
            write(report, output)
            self.assertEqual(35, json.loads((output / "relatorio.json").read_text(encoding="utf-8"))["summary"]["total"])
            original = (output / "relatorio.json").read_bytes()
            with self.assertRaises(FileExistsError):
                write(report, output)
            self.assertEqual(original, (output / "relatorio.json").read_bytes())
            self.assertTrue((output / "revisao-humana.csv").is_file())

    def test_cli_exit_codes_and_invalid_configuration(self):
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            root = Path(folder)
            with patch("evaluation.__main__.run", return_value=self.report):
                self.assertEqual(1, main(["--saida", str(root / "failure")]))
            self.assertEqual(2, main(["--saida", str(root / "failure")]))
            success = copy.deepcopy(self.report)
            success["summary"]["quality_passed"] = True
            with patch("evaluation.__main__.run", return_value=success):
                self.assertEqual(0, main(["--saida", str(root / "success")]))
            self.assertEqual(2, main(["--suite", str(root / "missing.json"), "--saida", str(root / "invalid")]))
            self.assertFalse((root / "invalid").exists())


if __name__ == "__main__":
    unittest.main()
