import copy
import json
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

import requests

from knowledge_search.generation import GenerationSettings, GeminiGenerator, outgoing_context
import test_knowledge_search as search_tests


EXCERPT = "Problema relatado: falha de comunicação com PLC. Contato: tecnico@example.com"


def result():
    return {"query": "Falha no PLC. senha=SEGREDO_FIXTURE_123", "warnings": [], "generated_answer": None,
            "results": [{"document_key": "a" * 64, "source_id": "private-ticket-id",
                         "title": "CLIENTE PRIVADO", "excerpt": EXCERPT,
                         "origin": {"arquivo_relativo": "arquivo_privado.json"},
                         "metadata": {"uso_na_recomendacao": "hipotese_para_investigacao", "cliente": "CLIENTE PRIVADO"}}]}


def answer():
    return {"abstain": False, "paragraphs": [{"text": "O registro descreve falha de comunicação; confirme a relação com o atendimento atual.",
                                             "citations": [{"source": "F1", "quote": "falha de comunicação com PLC"}]}]}


class Reply:
    def __init__(self, value=None, status=200, finish="STOP", raw=None):
        self.status_code = status
        self.raw = raw if raw is not None else json.dumps({"candidates": [{"finishReason": finish,
            "content": {"parts": [{"text": json.dumps(value if value is not None else answer())}]}}]}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, size):
        yield self.raw


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.settings = GenerationSettings(True, "fake-key-for-tests", "gemini-test")

    def test_disabled_missing_key_and_invalid_model_never_send(self):
        for settings, expected in ((replace(self.settings, enabled=False), "disabled"),
                                   (replace(self.settings, api_key=""), "not_configured"),
                                   (replace(self.settings, model="../invalid?key=x"), "not_configured")):
            with self.subTest(expected=expected):
                post = Mock()
                response = GeminiGenerator(settings, post).generate(result())
                self.assertEqual(expected, response["generation_status"])
                post.assert_not_called()
        self.assertNotIn(self.settings.api_key, repr(self.settings))

    def test_no_sources_never_send(self):
        data = result(); data["results"] = []
        post = Mock()
        self.assertEqual("no_sources", GeminiGenerator(self.settings, post).generate(data)["generation_status"])
        post.assert_not_called()

    def test_payload_minimization_header_key_and_real_source_mapping(self):
        post = Mock(return_value=Reply())
        data = result(); original = copy.deepcopy(data)
        generated = GeminiGenerator(self.settings, post).generate(data)
        self.assertEqual("generated", generated["generation_status"])
        self.assertEqual(data, original)
        args, kwargs = post.call_args
        self.assertNotIn(self.settings.api_key, args[0])
        self.assertEqual(self.settings.api_key, kwargs["headers"]["x-goog-api-key"])
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual((5, 45), kwargs["timeout"])
        payload = json.dumps(kwargs["json"])
        for forbidden in ("CLIENTE PRIVADO", "arquivo_privado", "private-ticket-id", "tecnico@example.com", "SEGREDO_FIXTURE_123", self.settings.api_key):
            self.assertNotIn(forbidden, payload)
        self.assertNotIn("tools", kwargs["json"])
        citation = generated["generated_answer"]["paragraphs"][0]["citations"][0]
        self.assertEqual("a" * 64, citation["document_key"])
        self.assertEqual("private-ticket-id", citation["source_id"])

    def test_payload_is_bounded(self):
        data = result(); data["results"] *= 10; data["results"][0]["excerpt"] = "x" * 5000
        context = outgoing_context(data)
        self.assertEqual(5, len(context["sources"]))
        self.assertTrue(all(len(s["excerpt"]) <= 1000 for s in context["sources"]))

    def test_provider_failures_keep_sources_without_secret_or_raw_error(self):
        for status, expected in ((429, "rate_limited"), (401, "unavailable"), (403, "unavailable"), (500, "unavailable"), (302, "unavailable")):
            with self.subTest(status=status):
                post = Mock(return_value=Reply(status=status, raw=b"sensitive upstream error"))
                value = GeminiGenerator(self.settings, post).generate(result())
                self.assertEqual(expected, value["generation_status"])
                self.assertEqual(result()["results"], value["results"])
                self.assertNotIn("sensitive", json.dumps(value))
                post.assert_called_once()

    def test_timeout_releases_slot_and_does_not_retry(self):
        post = Mock(side_effect=requests.Timeout("fake-key-for-tests"))
        generator = GeminiGenerator(self.settings, post)
        for _ in range(3):
            response = generator.generate(result())
            self.assertEqual("unavailable", response["generation_status"])
            self.assertNotIn(self.settings.api_key, json.dumps(response))
        self.assertEqual(3, post.call_count)

    def test_busy_limit_never_sends(self):
        post = Mock()
        generator = GeminiGenerator(self.settings, post)
        generator.slots.acquire(); generator.slots.acquire()
        self.assertEqual("busy", generator.generate(result())["generation_status"])
        post.assert_not_called()

    def test_rejects_unknown_sources_fabricated_quotes_and_unreferenced_claims(self):
        invalid = []
        value = answer(); value["paragraphs"][0]["citations"][0]["source"] = "F99"; invalid.append(value)
        value = answer(); value["paragraphs"][0]["citations"][0]["quote"] = "Procedimento que nunca esteve na fonte"; invalid.append(value)
        value = answer(); value["paragraphs"][0]["citations"] = []; invalid.append(value)
        value = answer(); value["paragraphs"][0]["text"] = "x" * 1501; invalid.append(value)
        invalid.extend([[], {}, {"abstain": "false", "paragraphs": []}, {"abstain": False, "paragraphs": []}])
        for value in invalid:
            with self.subTest(value=str(value)[:60]):
                response = GeminiGenerator(self.settings, Mock(return_value=Reply(value))).generate(result())
                self.assertEqual("rejected", response["generation_status"])
                self.assertIsNone(response["generated_answer"])

    def test_abstention_blocked_truncated_invalid_and_oversized_responses(self):
        response = GeminiGenerator(self.settings, Mock(return_value=Reply({"abstain": True, "paragraphs": []}))).generate(result())
        self.assertEqual("abstained", response["generation_status"])
        for reply in (Reply(finish="MAX_TOKENS"), Reply(finish="SAFETY"), Reply(raw=b"not json"),
                      Reply(raw=b"x" * (128 * 1024 + 1)), Reply(raw=b'{"promptFeedback":{"blockReason":"SAFETY"}}'),
                      Reply(raw=b'{"candidates":null}')):
            self.assertEqual("rejected", GeminiGenerator(self.settings, Mock(return_value=reply)).generate(result())["generation_status"])


class GenerationApiTests(unittest.TestCase):
    def setUp(self):
        search_tests.KnowledgeApiTests.setUp(self)
        self.app.config["GEMINI_SETTINGS"] = GenerationSettings(True, "fake-key", "gemini-test")
        self.post = Mock(return_value=Reply())
        self.app.extensions["knowledge_generator"] = GeminiGenerator(self.app.config["GEMINI_SETTINGS"], self.post)

    def test_local_search_never_calls_gemini_even_when_enabled(self):
        data = self.client.post("/knowledge/search", json={"query": "redler"}, headers=self.headers)
        self.assertEqual(200, data.status_code)
        self.assertTrue(data.json["generation_available"])
        self.assertIsNone(data.json["generated_answer"])
        self.post.assert_not_called()

    def test_generation_requires_auth_and_rejects_retired_triage(self):
        self.assertEqual(401, self.client.post("/knowledge/answer", json={"query": "redler"}).status_code)
        self.assertEqual(400, self.client.post("/knowledge/answer", json={"session_id": "old"}, headers=self.headers).status_code)
        self.post.assert_not_called()

    def test_rejects_client_supplied_sources_and_stale_index(self):
        self.assertEqual(400, self.client.post("/knowledge/answer", json={"query": "redler", "sources": []}, headers=self.headers).status_code)
        search_tests.source_fixture(self.settings.source, [], "s2")
        self.assertEqual(503, self.client.post("/knowledge/answer", json={"query": "redler"}, headers=self.headers).status_code)
        self.post.assert_not_called()

    def test_generate_and_fallback_preserve_retrieval_and_never_expose_key(self):
        value = answer(); value["paragraphs"][0]["citations"][0]["quote"] = "Ausência de velocidade durante o transporte."
        self.post.return_value = Reply(value)
        response = self.client.post("/knowledge/answer", json={"query": "redler"}, headers=self.headers)
        self.assertEqual(200, response.status_code)
        self.assertEqual("generated", response.json["generation_status"])
        self.assertNotIn("fake-key", response.get_data(as_text=True))
        self.post.return_value = Reply(status=429)
        response = self.client.post("/knowledge/answer", json={"query": "redler"}, headers=self.headers)
        self.assertEqual("rate_limited", response.json["generation_status"])
        self.assertTrue(response.json["results"])


if __name__ == "__main__":
    unittest.main()
