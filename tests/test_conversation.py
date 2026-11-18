import json
import tempfile
import unittest
import uuid
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import requests

import test_knowledge_search as fixtures
from test_generation import Reply, answer, result
from knowledge_search.config import SearchError
from knowledge_search.conversation import ConversationStore, compact, reply
from knowledge_search.dialogue_context import retrieval_query
from knowledge_search.generation import GenerationSettings, GeminiGenerator, catalogue_source
from knowledge_search.storage import build


def decision(kind="ask", question="A falha começou depois de uma alteração ou nunca funcionou?"):
    body = answer() if kind == "answer" else {"abstain": True, "paragraphs": []}
    for paragraph in body["paragraphs"]:
        paragraph["citations"] = [{"evidence": "F1:E1"}]
    return {"decision": kind, "question": question if kind == "ask" else "", "options": [], **body}


class JsonReply(Reply):
    def __init__(self, data):
        super().__init__(raw=json.dumps(data).encode())


class DialogueTests(unittest.TestCase):
    def setUp(self):
        self.settings = GenerationSettings(True, "fixture-key", "gemini-test")
        self.post = Mock(side_effect=[JsonReply({"totalTokens": 1200}), Reply(decision())])
        self.generator = GeminiGenerator(self.settings, self.post)

    def test_ask_counts_tokens_and_sends_only_three_sources(self):
        data = result(); data["results"] *= 5
        value = self.generator.converse(data, "PLC sem comunicação", [], True)
        self.assertEqual("ask", value["decision"])
        self.assertEqual(1200, value["usage"]["input_tokens"])
        self.assertTrue(self.post.call_args_list[0].args[0].endswith(":countTokens"))
        payload = self.post.call_args_list[1].kwargs["json"]
        context = json.loads(payload["contents"][0]["parts"][0]["text"])
        self.assertEqual(3, len(context["sources"]))
        for forbidden in ("CLIENTE PRIVADO", "private-ticket-id", "arquivo_privado"):
            self.assertNotIn(forbidden, json.dumps(payload))

    def test_budget_blocks_generation(self):
        self.post.side_effect = [JsonReply({"totalTokens": 4001})]
        value = self.generator.converse(result(), "PLC", [])
        self.assertEqual("budget_exceeded", value["generation_status"])
        self.assertEqual(1, self.post.call_count)

    def test_initial_abstention_asks_for_symptom_without_another_provider_call(self):
        self.post.side_effect = [JsonReply({"totalTokens": 1007}), Reply(decision("insufficient"))]
        value = self.generator.converse(result(), "problema com a unity", [])
        self.assertEqual("ask", value["decision"])
        self.assertEqual("clarifying_local", value["generation_status"])
        self.assertIn("O que acontece", value["follow_up"])
        self.assertEqual(2, self.post.call_count)
        self.assertIsNone(value["generated_answer"])

    def test_source_backed_choices_are_returned_and_fabricated_choices_rejected(self):
        data = result()
        data["results"].append({**data["results"][0], "document_key": "b" * 64,
                              "excerpt": "Valores congelados durante a operação."})
        value = decision()
        value["options"] = [{"label": "Falha de comunicação", "evidence": "F1:E1"},
                            {"label": "Valores congelados", "evidence": "F2:E1"}]
        self.post.side_effect = [JsonReply({"totalTokens": 200}), Reply(value)]
        output = self.generator.converse(data, "Problema no PLC", [])
        self.assertEqual(2, len(output["clarification_options"]))
        self.assertEqual("a" * 64, output["clarification_options"][0]["document_key"])
        for mutation in ("evidence", "source", "duplicate", "one"):
            invalid = json.loads(json.dumps(value))
            if mutation == "duplicate":
                invalid["options"][1]["label"] = invalid["options"][0]["label"]
            elif mutation == "one":
                invalid["options"] = invalid["options"][:1]
            else:
                invalid["options"][0][mutation] = "inventado sem apoio na fonte"
            post = Mock(side_effect=[JsonReply({"totalTokens": 200}), Reply(invalid)])
            self.assertEqual("rejected", GeminiGenerator(self.settings, post).converse(data, "PLC", [])["generation_status"])

    def test_abstention_after_generic_reply_offers_specific_local_choices(self):
        data = result()
        data["results"] = [{**data["results"][0], "excerpt": "Problema relatado: Alguém relata erro de problema com Unit"},
                           {**data["results"][0], "excerpt": "Problema relatado: A Unit fica travada ao iniciar."},
                           {**data["results"][0], "excerpt": "Problema relatado: Não consegue copiar uma Unit para outra."}]
        self.post.side_effect = [JsonReply({"totalTokens": 100}), Reply(decision("insufficient"))]
        value = self.generator.converse(data, "Relato inicial: problema na Unit. Resposta: erro genérico na Unit", ["Qual o sintoma?"], True)
        self.assertEqual("ask", value["decision"])
        self.assertEqual(2, len(value["clarification_options"]))
        self.assertTrue(all("erro de problema" not in o["label"] for o in value["clarification_options"]))

    def test_open_question_gets_specific_source_options_without_extra_call(self):
        data = result()
        data["results"] = [{**data["results"][0], "excerpt": "Problema relatado: A Unit fica travada ao iniciar."},
                           {**data["results"][0], "excerpt": "Problema relatado: Não consegue copiar uma Unit para outra."}]
        value = self.generator.converse(data, "Problema na Unity", [], True)
        self.assertEqual(2, len(value["clarification_options"]))
        self.assertEqual(2, self.post.call_count)

    def test_local_abstention_choices_are_extracted_from_ticket_symptoms(self):
        data = result()
        data["results"] = [{**data["results"][0], "excerpt": "Problema relatado: A tela fica preta ao iniciar."},
                           {**data["results"][0], "excerpt": "Problema relatado: O login apresenta erro após atualizar."}]
        self.post.side_effect = [JsonReply({"totalTokens": 200}), Reply(decision("insufficient"))]
        value = self.generator.converse(data, "problema com a unity", [])
        self.assertEqual("ask", value["decision"])
        self.assertEqual(2, len(value["clarification_options"]))
        self.assertEqual("A tela fica preta ao iniciar.", value["clarification_options"][0]["label"])

    def test_abstention_after_clarification_or_at_limit_stays_explicit(self):
        for previous, allowed in ((["Qual erro aparece?"], True), ([], False)):
            post = Mock(side_effect=[JsonReply({"totalTokens": 100}), Reply(decision("insufficient"))])
            value = GeminiGenerator(self.settings, post).converse(result(), "Ainda não sei", previous, allowed)
            self.assertEqual("insufficient", value["decision"])
            self.assertEqual("abstained", value["generation_status"])

    def test_answer_preserves_citation_and_usage(self):
        data = result()
        data["results"][0]["excerpt"] = "Solução candidata: Ajustar a configuração de rede após verificar a compatibilidade."
        response = json.loads(Reply(decision("answer")).raw)
        response["usageMetadata"] = {"promptTokenCount": 1200, "totalTokenCount": 1500}
        self.post.side_effect = [JsonReply({"totalTokens": 1200}), JsonReply(response)]
        value = self.generator.converse(data, "PLC", [])
        self.assertEqual("answer", value["decision"])
        self.assertEqual("a" * 64, value["generated_answer"]["paragraphs"][0]["citations"][0]["document_key"])
        self.assertEqual(1500, value["usage"]["totalTokenCount"])
        source = json.loads(self.post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"])["sources"][0]
        self.assertNotIn("excerpt", source, "a ficha não é enviada duas vezes")
        self.assertEqual(source["evidence"][0]["text"], value["generated_answer"]["paragraphs"][0]["citations"][0]["quote"])

    def test_request_description_alone_cannot_be_a_final_solution(self):
        data = result()
        data["results"][0]["excerpt"] = "Problema relatado: Solicitação de inclusão de um medidor no supervisório."
        self.post.side_effect = [JsonReply({"totalTokens": 300}), Reply(decision("answer"))]
        value = self.generator.converse(data, "Problema na Unit", [], True)
        self.assertNotEqual("answer", value["decision"])
        self.assertIsNone(value["generated_answer"])

    def test_solution_answer_must_cite_the_action_not_only_the_symptom(self):
        data = result()
        data["results"][0]["excerpt"] = "Problema relatado: Erro de script ao clicar nas Units.\n\nSolução candidata: Alterar o caminho padrão no SCADA, após conferir a configuração."
        for evidence, expected in (("F1:E1", False), ("F1:E2", True)):
            value = decision("answer");value["paragraphs"][0]["citations"] = [{"evidence":evidence}]
            generator = GeminiGenerator(self.settings,Mock(side_effect=[JsonReply({"totalTokens":300}),Reply(value)]))
            actual=generator.converse(data,"Erro de script ao clicar nas Units",[],True)
            self.assertEqual(expected,actual["decision"]=="answer")

    def test_catalogue_chunks_are_literal_bounded_and_keep_final_words(self):
        text = "Solução candidata: " + "palavra " * 50 + "não confirmado"
        catalogue = catalogue_source("F1", text)
        self.assertTrue(all(12 <= len(e["text"]) <= 260 and e["text"] in text for e in catalogue))
        self.assertIn("não confirmado", " ".join(e["text"] for e in catalogue))

    def test_generation_import_does_not_depend_on_flask_import_order(self):
        process = subprocess.run([sys.executable, "-c", "import knowledge_search.generation"], capture_output=True, text=True)
        self.assertEqual(0, process.returncode, process.stderr)

    def test_repeated_question_and_question_limit_are_rejected(self):
        for questions, allowed in (([decision()["question"]], True), ([], False)):
            with self.subTest(allowed=allowed):
                post = Mock(side_effect=[JsonReply({"totalTokens": 1}), Reply(decision())])
                value = GeminiGenerator(self.settings, post).converse(result(), "PLC", questions, allowed)
                self.assertEqual("rejected", value["generation_status"])

    def test_no_sources_and_disabled_never_call_provider(self):
        data = result(); data["results"] = []
        value = self.generator.converse(data, "Falha", [])
        self.assertEqual("ask", value["decision"])
        self.assertEqual("insufficient", self.generator.converse(data, "Falha", [value["follow_up"]])["decision"])
        disabled = GeminiGenerator(replace(self.settings, enabled=False), self.post)
        self.assertEqual("disabled", disabled.converse(result(), "PLC", [])["generation_status"])
        self.post.assert_not_called()

    def test_timeout_and_bad_count_fail_without_generation(self):
        for response in (requests.Timeout(), JsonReply({"totalTokens": True}), JsonReply({}), JsonReply(None)):
            with self.subTest(response=type(response).__name__):
                post = Mock(side_effect=[response])
                value = GeminiGenerator(self.settings, post).converse(result(), "PLC", [])
                self.assertIn(value["generation_status"], ("rejected", "unavailable"))
                self.assertEqual(1, post.call_count)

    def test_fabricated_evidence_and_inconsistent_decision_are_rejected(self):
        cases = [decision("answer"), decision("ask"), decision("insufficient")]
        cases[0]["paragraphs"][0]["citations"][0]["evidence"] = "F99:E999"
        cases[1]["paragraphs"] = answer()["paragraphs"]; cases[1]["abstain"] = False
        cases[2]["question"] = "Uma pergunta indevida?"
        for case in cases:
            post = Mock(side_effect=[JsonReply({"totalTokens": 100}), Reply(case)])
            self.assertEqual("rejected", GeminiGenerator(self.settings, post).converse(result(), "PLC", [])["generation_status"])


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = ConversationStore(Path(self.temp.name) / "sessions.sqlite3")

    def begin(self, owner="alice", session_id=None, request_id=None, message="Falha no PLC"):
        return self.store.begin(owner, session_id, request_id or str(uuid.uuid4()), message)

    def test_owner_isolation_pending_lease_and_idempotency(self):
        request_id = str(uuid.uuid4())
        identifier, turns, _ = self.begin(request_id=request_id)
        with self.assertRaises(SearchError) as caught:
            self.begin(owner="bob", session_id=identifier)
        self.assertEqual(404, caught.exception.status)
        with self.assertRaises(SearchError) as caught:
            self.begin(session_id=identifier)
        self.assertEqual(409, caught.exception.status)
        response = {"follow_up": "Quando começou?", "session_id": identifier}
        self.store.finish("alice", identifier, request_id, turns, response)
        self.assertEqual(response, self.begin(request_id=request_id)[2])
        with self.assertRaises(SearchError):
            self.begin(request_id=request_id, message="Outro problema")
        _, next_turns, _ = self.begin(session_id=identifier, message="Após atualizar")
        self.assertEqual("Quando começou?", next_turns[-1]["asked"])
        self.assertIn("Após atualizar", compact(next_turns))

    def test_invalid_input_masking_and_turn_limit(self):
        for session_id in ([], "", "bad", 123):
            with self.assertRaises(SearchError):
                self.begin(session_id=session_id)
        identifier, turns, _ = self.begin(message="Falha CPF 12345678901 senha=segredo")
        self.assertNotIn("12345678901", turns[0]["message"])
        self.assertNotIn("segredo", turns[0]["message"])
        self.store.finish("alice", identifier, str(uuid.uuid4()), turns * 6, {"follow_up": ""})
        with self.assertRaises(SearchError):
            self.begin(session_id=identifier)

    def test_compact_context_keeps_all_turns_within_budget(self):
        turns = [{"message": f"Fato{i} " + "a" * 1700, "asked": f"Pergunta{i} " + "b" * 200} for i in range(6)]
        value = compact(turns)
        self.assertLessEqual(len(value), 2000)
        for i in range(6):
            self.assertIn(f"Fato{i}", value)

    def test_retrieval_excludes_role_labels_and_normalizes_domain_alias(self):
        turns = [{"message": "problemas com a unity", "asked": ""},
                 {"message": "Erro genérico com Unit relatado", "asked": "Qual erro ocorre com a unidade?"},
                 {"message": "pronlema com a unity", "asked": ""}]
        query = retrieval_query(turns)
        for noise in ("usuário", "usuario", "pergunta", "relato", "unity"):
            self.assertNotIn(noise, query)
        self.assertIn("unit", query)
        confirmed = retrieval_query([turns[0], {"message": "Sim", "asked": "A Unit fica travada ao copiar?"}])
        self.assertIn("copiar", confirmed)

    def test_option_request_does_not_become_search_content(self):
        prompt = "Estou com problema em uma Unit. Quais situações parecidas existem nos tickets? Mostre opções para eu escolher a que mais se parece com o meu caso."
        self.assertEqual("unit",retrieval_query([{"message":prompt,"asked":""}]))
        general = "Estou com um problema no sistema, mas não sei identificar a causa. Pode me mostrar algumas situações para eu escolher a mais parecida?"
        query = retrieval_query([{"message":general,"asked":""}])
        self.assertEqual("",query)
        for word in ("situacao","opcao","escolher","parecida","identificar"):
            self.assertNotIn(word,query)

    def test_completed_session_can_replay_but_cannot_start_another_turn(self):
        request_id = str(uuid.uuid4())
        identifier, turns, _ = self.begin(request_id=request_id)
        response = {"decision": "answer", "follow_up": ""}
        self.store.finish("alice", identifier, request_id, turns, response)
        self.assertEqual(response, self.begin(request_id=request_id)[2])
        with self.assertRaises(SearchError) as caught:
            self.begin(session_id=identifier)
        self.assertEqual(409, caught.exception.status)

    def test_failure_releases_session_for_retry(self):
        search = Mock(); search.search.side_effect = RuntimeError("fixture failure")
        request_id = str(uuid.uuid4())
        with self.assertRaises(RuntimeError):
            reply(self.store, search, Mock(), "alice", {"message": "Falha no PLC", "request_id": request_id})
        self.assertEqual(1, len(self.begin(request_id=request_id, message="Falha no PLC")[1]))

    def test_retry_after_technical_failure_preserves_original_turn(self):
        request_id = str(uuid.uuid4())
        identifier, turns, _ = self.begin(request_id=request_id)
        self.store.finish("alice", identifier, request_id, turns, {"generation_status":"rejected"})
        _, retried, _ = self.begin(session_id=identifier, message="Falha no PLC")
        self.assertEqual(turns, retried)
        self.store.release("alice", identifier)
        _, next_turn, _ = self.begin(session_id=identifier, message="Outro detalhe do problema")
        self.assertEqual(2, len(next_turn))


class ConversationApiTests(unittest.TestCase):
    def setUp(self):
        fixtures.KnowledgeApiTests.setUp(self)
        self.app.config["KNOWLEDGE_CONVERSATION_DATABASE"] = self.root / "conversations.sqlite3"
        self.fake = Mock()
        self.fake.settings.status.return_value = "ready"
        self.fake.converse.return_value = {"decision": "ask", "follow_up": "Quando a falha começou?",
            "generated_answer": None, "warnings": [], "generation_status": "clarifying", "usage": {}}
        self.app.extensions["knowledge_generator"] = self.fake

    def test_conversation_refines_query_and_retry_does_not_generate_twice(self):
        request_id = str(uuid.uuid4())
        data = {"request_id": request_id, "message": "PLC sem comunicação"}
        value = self.client.post("/knowledge/conversation", json=data, headers=self.headers)
        self.assertEqual(200, value.status_code)
        self.assertEqual("ask", value.json["decision"])
        self.assertEqual(200, self.client.post("/knowledge/conversation", json=data, headers=self.headers).status_code)
        self.assertEqual(1, self.fake.converse.call_count)
        data.update(session_id=value.json["session_id"], request_id=str(uuid.uuid4()), message="Após atualização")
        value = self.client.post("/knowledge/conversation", json=data, headers=self.headers)
        self.assertEqual(2, value.json["turn"])
        context = self.fake.converse.call_args.args[1]
        self.assertIn("PLC", context)
        self.assertIn("Após atualização", context)
        self.assertEqual(404, self.client.post("/knowledge/conversation", json={**data,"request_id":str(uuid.uuid4())}, headers={"Authorization":"Bearer bob"}).status_code)

    def test_auth_validation_and_no_database_exposure(self):
        self.assertEqual(401, self.client.post("/knowledge/conversation", json={}).status_code)
        for data in ([], {}, {"message":"Falha","request_id":str(uuid.uuid4()),"sources":[]}):
            self.assertEqual(400, self.client.post("/knowledge/conversation", json=data, headers=self.headers).status_code)
        self.assertEqual(404, self.client.get("/instance/conversations.sqlite3").status_code)

    def test_solution_at_end_of_long_document_reaches_generation(self):
        records = [fixtures.record("long", "Falha PLC", "Sintoma sem ação. " * 300,
            solucao_documentada="Ajustar configuração de rede conforme procedimento validado.",
            resultado_documentado="Comunicação restabelecida no caso histórico.",
            aplicabilidade_ao_caso_atual="Conferir versão antes de aplicar.")]
        fixtures.source_fixture(self.settings.source, records, "s2")
        build(self.settings)
        response = self.client.post("/knowledge/conversation", json={"message":"Falha PLC","request_id":str(uuid.uuid4())}, headers=self.headers)
        self.assertEqual(200, response.status_code)
        evidence = self.fake.converse.call_args.args[0]["results"][0]["excerpt"]
        for text in ("Ajustar configuração", "Comunicação restabelecida", "Conferir versão"):
            self.assertIn(text, evidence)

    def test_concrete_symptoms_precede_generic_records_and_history_labels_are_not_searched(self):
        records = [fixtures.record("generic", "Problema com Unit", "Pessoa relata erro de problema com Unit"),
                   fixtures.record("locked", "Unit travada", "A Unit fica travada ao iniciar."),
                   fixtures.record("copy", "Copiar Unit", "Não consegue copiar uma Unit para outra.")]
        fixtures.source_fixture(self.settings.source, records, "s2")
        build(self.settings)
        found = self.service.search("unit", 20)
        evidence = self.service.evidence(found)
        ids = [item["source_id"] for item in evidence["results"]]
        self.assertEqual({"locked", "copy"}, set(ids[:2]))
        with patch.object(self.service, "search", wraps=self.service.search) as search:
            value = self.client.post("/knowledge/conversation", json={"message":"problemas com a unity","request_id":str(uuid.uuid4())}, headers=self.headers)
            self.assertEqual(200, value.status_code)
            self.assertEqual("unit", search.call_args.args[0])
            self.assertEqual(20, search.call_args.args[1])

    def test_unit_request_filters_unrelated_proposals_and_candidates_outside_topic(self):
        records=[fixtures.record("proposal","Proposta de automação - Unit","Solicitação de engenharia para inclusão de medidor de vazão.",solucao_candidata="Executar projeto de inclusão de medidor."),
                 fixtures.record("unrelated","Falha no sensor","Sensor apresenta leitura incorreta.",solucao_candidata="Trocar sensor após verificar a leitura."),
                 fixtures.record("locked","Unit travada","A Unit fica travada ao iniciar."),
                 fixtures.record("copy","Copiar Unit","A Unit não copia para a próxima etapa.")]
        fixtures.source_fixture(self.settings.source,records,"s2");build(self.settings)
        found=self.service.search("unit sensor",20)
        found["topic_terms"]=["unit"]
        selected=self.service.evidence(found)
        self.assertEqual({"locked","copy"},{r["source_id"] for r in selected["results"]})
        found["query"]="proposta unit medidor"
        self.assertIn("proposal",{r["source_id"] for r in self.service.evidence(found)["results"]})

    def test_completely_general_prompt_does_not_search_instruction_words(self):
        with patch.object(self.service,"search",wraps=self.service.search) as search:
            value=self.client.post('/knowledge/conversation',json={"message":"Estou com um problema no sistema. Mostre opções para escolher.","request_id":str(uuid.uuid4())},headers=self.headers)
            self.assertEqual(200,value.status_code)
            search.assert_not_called()
            self.assertEqual([],value.json['results'])


if __name__ == "__main__":
    unittest.main()
