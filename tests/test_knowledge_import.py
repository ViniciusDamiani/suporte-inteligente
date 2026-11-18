"""Cenários de integridade/atualização usando exclusivamente dados sintéticos."""
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

from knowledge_import.storage import import_package, inspect_database
from knowledge_import.__main__ import main
from knowledge_import.validation import ImportFailure, SNAPSHOT_MODE, canonical, digest, parse_json


def entity(identifier="caso_ticket:1"):
    kind, original = identifier.split(":", 1)
    data = {"assunto": "Falha sintética", "data": None, "numero_erro": "E123"}
    return {"id": identifier, "tipo": kind, "grupo_conhecimento": "Tickets", "id_origem": original,
            "origem": {"arquivo_relativo": "origem.csv", "registro_id": original},
            "metadados": {"cliente_referencia": None, "versao_referencia": None,
                          "estado_revisao": "pendente", "permissao_de_acesso_requerida": True,
                          "apto_recomendacao_automatica": False, "indexacao": "nao_executada", "disponivel_pesquisa": True},
            "dados": data, "conteudo_sha256": digest(data)}


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "store.sqlite3"
        self.source = {"id": "fonte:1", "tipo": "arquivo", "arquivo_relativo": "referencia/log.txt",
                       "disponibilidade": "extrato", "acesso_automatico_ao_caminho": False}
        self.link = {"id": "vinculo:1", "origem_id": "caso_ticket:1", "destino_id": "fonte:1",
                     "relacao": "extraida_da_fonte", "estado": "pendente", "origem_vinculo": "origem.csv",
                     "condicao_documentada": "", "prova_de_causalidade": False}

    def package(self, version="1", records=None, links=None, sources=None):
        folder = self.root / ("package_" + version)
        folder.mkdir(exist_ok=True)
        records = [entity()] if records is None else records
        links = [self.link] if links is None else links
        sources = [self.source] if sources is None else sources
        entries = []
        for kind, objects in (("conhecimento", records), ("fontes", sources), ("vinculos", links)):
            name = kind + ".jsonl"
            raw = "".join(canonical(item) + "\n" for item in objects).encode("utf-8")
            (folder / name).write_bytes(raw)
            entries.append({"arquivo": name, "formato": "jsonl", "papel": "registros", "importar": True,
                            "registros": len(objects), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "destino_sugerido": kind})
        raw = b'{"tabelas": []}'
        (folder / "auxiliar.json").write_bytes(raw)
        entries.append({"arquivo": "auxiliar.json", "formato": "json", "papel": "recurso_auxiliar", "importar": True,
                        "registros": None, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "destino_sugerido": "recursos_banco"})
        # Não deve sequer abrir uma entrada excluída nem varrer outros arquivos.
        entries.append({"arquivo": "nao_existe.json", "importar": False})
        (folder / "fora_catalogo.jsonl").write_text("invalid JSON", encoding="utf-8")
        catalog = {"schema_versao": "1.0.0", "pacote_id": "teste", "pacote_versao": version,
                   "modo": SNAPSHOT_MODE, "pendencias_estruturais": 0, "entidades": len(records),
                   "vinculos": len(links), "arquivos": entries}
        path = folder / "catalogo.json"
        path.write_text(canonical(catalog), encoding="utf-8")
        return path

    def edit_catalog(self, path, change):
        catalog = json.loads(path.read_text(encoding="utf-8"))
        change(catalog)
        path.write_text(canonical(catalog), encoding="utf-8")

    def run_import(self, path, **kwargs):
        return import_package(path, self.db, actor="teste", **kwargs)

    def rows(self, sql):
        with closing(sqlite3.connect(self.db)) as connection:
            return connection.execute(sql).fetchall()

    def assert_rejected(self, path, code):
        result = self.run_import(path)
        self.assertEqual("rejeitado", result["estado"], result)
        self.assertEqual(code, result["erros"][0]["codigo"], result)
        return result

    def test_first_import_preserves_content_and_excludes_undeclared_files(self):
        result = self.run_import(self.package())
        self.assertEqual("ativado", result["estado"], result)
        self.assertEqual(4, len(self.rows("SELECT id FROM active_records")))
        payload = json.loads(self.rows("SELECT payload FROM active_records WHERE kind='conhecimento'")[0][0])
        self.assertEqual(entity(), payload)
        self.assertEqual(1, len(inspect_database(self.db)["pacotes_ativos"]))

    def test_import_and_search_flag_publishes_index_from_validated_snapshot(self):
        from knowledge_search.config import Settings
        from knowledge_search.service import SearchService
        from test_knowledge_search import FixtureEmbedder
        item = entity()
        item["dados"]["problema_relatado"] = "Redler sem velocidade"
        item["conteudo_sha256"] = digest(item["dados"])
        path = self.package(records=[item])
        settings = Settings(self.db, self.root / "search.sqlite3", self.root / "models")
        embedder = FixtureEmbedder()
        with patch("knowledge_search.config.Settings.from_env", return_value=settings), patch("knowledge_search.embeddings.get_embedder", return_value=embedder), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = main(["importar", "--catalogo", str(path), "--banco", str(self.db), "--atualizar-busca"])
        self.assertEqual(0, code)
        result = SearchService(settings, lambda _: embedder).search("redler")
        self.assertEqual("caso_ticket:1", result["results"][0]["source_id"])

    def test_search_failure_preserves_successful_import_and_returns_distinct_code(self):
        from knowledge_search.config import SearchError
        output = io.StringIO()
        with patch("knowledge_search.embeddings.get_embedder", side_effect=SearchError("Modelo ausente")), redirect_stdout(output), redirect_stderr(io.StringIO()):
            code = main(["importar", "--catalogo", str(self.package()), "--banco", str(self.db), "--atualizar-busca"])
        self.assertEqual(2, code)
        result = json.loads(output.getvalue())
        self.assertEqual("ativado", result["estado"])
        self.assertTrue(result["busca"]["importacao_preservada"])
        self.assertEqual(1, len(inspect_database(self.db)["pacotes_ativos"]))

    def test_repeat_does_not_duplicate_revisions_or_snapshot(self):
        path = self.package()
        self.run_import(path)
        result = self.run_import(path)
        self.assertEqual("sem_alteracoes", result["estado"])
        self.assertEqual([(1,)], self.rows("SELECT COUNT(*) FROM snapshots"))
        self.assertEqual([(4,)], self.rows("SELECT COUNT(*) FROM revisions"))
        self.assertEqual(2, len(inspect_database(self.db, history=True)["execucoes"]))

    def test_update_add_remove_and_history(self):
        self.run_import(self.package(records=[entity(), entity("caso_ticket:2")]))
        changed = entity()
        changed["dados"]["assunto"] = "Atualizado"
        changed["conteudo_sha256"] = digest(changed["dados"])
        result = self.run_import(self.package("2", [changed, entity("caso_ticket:3")]))
        changes = result["alteracoes"]["conhecimento"]
        self.assertEqual((1, 1, 1), (changes["incluidos"], changes["atualizados"], changes["retirados"]))
        self.assertEqual([], self.rows("SELECT id FROM active_records WHERE id='caso_ticket:2'"))
        self.assertEqual([(2,)], self.rows("SELECT COUNT(*) FROM revisions WHERE id='caso_ticket:1'"))
        self.assertEqual([(1,)], self.rows("SELECT COUNT(*) FROM revisions WHERE id='caso_ticket:2'"))

    def test_metadata_only_change_removes_search_eligibility(self):
        self.run_import(self.package())
        changed = entity()
        changed["metadados"]["disponivel_pesquisa"] = False
        result = self.run_import(self.package("2", [changed]))
        self.assertEqual(1, result["alteracoes"]["conhecimento"]["atualizados"])
        self.assertEqual(1, result["alteracoes"]["conhecimento"]["retirados_da_pesquisa"])
        self.assertEqual([(0,)], self.rows("SELECT searchable FROM active_records WHERE kind='conhecimento'"))

    def test_missing_eligibility_is_not_permission_to_search(self):
        item = entity()
        del item["metadados"]["disponivel_pesquisa"]
        self.run_import(self.package(records=[item]))
        self.assertEqual([(0,)], self.rows("SELECT searchable FROM active_records WHERE kind='conhecimento'"))

    def test_failure_keeps_previous_snapshot_and_audits_rejection(self):
        first = self.run_import(self.package())
        link = {**self.link, "destino_id": "fonte:inexistente"}
        result = self.assert_rejected(self.package("2", links=[link]), "vinculo_orfao")
        self.assertIn("linha", result["erros"][0])
        self.assertEqual(first["snapshot_id"], inspect_database(self.db)["pacotes_ativos"][0]["snapshot_id"])
        self.assertEqual([(1,)], self.rows("SELECT COUNT(*) FROM snapshots"))
        self.assertEqual("rejeitado", inspect_database(self.db, history=True)["execucoes"][0]["estado"])

    def test_transaction_rolls_back_if_activation_write_fails(self):
        first = self.run_import(self.package())
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("CREATE TRIGGER fail_activation BEFORE UPDATE ON active_packages BEGIN SELECT RAISE(ABORT,'test failure'); END")
        changed = entity()
        changed["metadados"]["estado_revisao"] = "nova revisao"
        self.assert_rejected(self.package("2", [changed]), "erro_armazenamento")
        self.assertEqual([(1,)], self.rows("SELECT COUNT(*) FROM snapshots"))
        self.assertEqual([(4,)], self.rows("SELECT COUNT(*) FROM revisions"))
        self.assertEqual(first["snapshot_id"], inspect_database(self.db)["pacotes_ativos"][0]["snapshot_id"])

    def test_validate_only_does_not_create_database(self):
        result = self.run_import(self.package(), validate_only=True)
        self.assertEqual("validado", result["estado"])
        self.assertFalse(self.db.exists())

    def test_existing_version_cannot_be_changed_or_reactivated(self):
        old_path = self.package()
        self.run_import(old_path)
        changed = entity()
        changed["metadados"]["estado_revisao"] = "alterado"
        self.assert_rejected(self.package(records=[changed]), "versao_alterada")
        old_path = self.package()
        self.run_import(self.package("2"))
        self.assert_rejected(old_path, "versao_historica")

    def test_duplicate_ids_across_files_rejected(self):
        self.assert_rejected(self.package(records=[entity(), entity()]), "id_duplicado")

    def test_invalid_hash_required_fields_and_policy(self):
        for mutation, code in (
            (lambda item: item["dados"].update(assunto="alterado sem hash"), "hash_conteudo"),
            (lambda item: item.pop("origem"), "envelope_invalido"),
            (lambda item: item["metadados"].update(apto_recomendacao_automatica=True), "politica_invalida"),
            (lambda item: item["metadados"].update(disponivel_pesquisa="sim"), "metadados_invalidos"),
        ):
            with self.subTest(code=code):
                item = entity()
                mutation(item)
                self.assert_rejected(self.package(records=[item]), code)

    def test_bad_manifest_hash_size_counts_schema_and_partial(self):
        for mutation, code in (
            (lambda c: c["arquivos"][0].update(sha256="0" * 64), "hash_arquivo"),
            (lambda c: c["arquivos"][0].update(bytes=1), "tamanho_arquivo"),
            (lambda c: c["arquivos"][0].update(registros=2), "contagem_arquivo"),
            (lambda c: c.update(entidades=2), "contagem_pacote"),
            (lambda c: c.update(modo="incremental"), "carga_parcial"),
            (lambda c: c.update(schema_versao="2.0.0"), "schema_incompativel"),
            (lambda c: c.update(pendencias_estruturais=1), "pendencias"),
            (lambda c: c["arquivos"][1].update(importar=False), "carga_incompleta"),
        ):
            with self.subTest(code=code):
                path = self.package()
                self.edit_catalog(path, mutation)
                self.assert_rejected(path, code)

    def test_unsafe_paths_rejected(self):
        for value in ("../outside.jsonl", "C:/data.jsonl", "/data.jsonl", "a\\b.jsonl", "a//b.jsonl"):
            with self.subTest(path=value):
                path = self.package()
                self.edit_catalog(path, lambda c: c["arquivos"][0].update(arquivo=value))
                self.assert_rejected(path, "caminho_invalido")

    def test_invalid_json_duplicate_keys_and_nonfinite_numbers(self):
        for raw in (b'{"id":1,"id":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e9999}', b'{bad', b'\xff'):
            with self.subTest(raw=raw), self.assertRaises(ImportFailure):
                parse_json(raw)

    def test_root_pointer_checks_hash_and_version(self):
        path = self.package()
        pointer = self.root / "CATALOGO.json"
        value = {"schema_versao": "1.0.0", "pacote_preparado": "1", "catalogo": "package_1/catalogo.json",
                 "catalogo_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        pointer.write_text(canonical(value), encoding="utf-8")
        self.assertEqual("ativado", self.run_import(pointer)["estado"])
        value["catalogo_sha256"] = "0" * 64
        pointer.write_text(canonical(value), encoding="utf-8")
        self.assert_rejected(pointer, "hash_catalogo")

    def test_multiple_packages_are_isolated(self):
        self.run_import(self.package())
        path = self.package("2", records=[], links=[], sources=[])
        self.edit_catalog(path, lambda c: c.update(pacote_id="outro"))
        self.assertEqual("ativado", self.run_import(path)["estado"])
        self.assertEqual([(4,)], self.rows("SELECT COUNT(*) FROM active_records WHERE package_id='teste'"))

    def test_different_empty_database_is_not_overwritten(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("CREATE TABLE unrelated (id INTEGER)")
        self.assert_rejected(self.package(), "banco_incompativel")
        self.assertEqual([("unrelated",)], self.rows("SELECT name FROM sqlite_master WHERE type='table'"))

    def test_concurrent_repeat_creates_one_snapshot(self):
        path = self.package()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.run_import, [path, path]))
        self.assertEqual(["ativado", "sem_alteracoes"], sorted(result["estado"] for result in results), results)
        self.assertEqual([(1,)], self.rows("SELECT COUNT(*) FROM snapshots"))

    def test_cli_writes_report_and_returns_error_for_rejection(self):
        path = self.package()
        output = self.root / "report.json"
        args = ["--catalogo", str(path), "--banco", str(self.db)]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(0, main(["importar", *args, "--relatorio", str(output)]))
            self.assertEqual(0, main(["status", *args]))
            self.assertEqual(1, main(["importar", *args, "--relatorio", str(output)]))
            path.write_text("invalid JSON", encoding="utf-8")
            self.assertEqual(1, main(["importar", *args]))
        self.assertEqual("ativado", json.loads(output.read_text(encoding="utf-8"))["estado"])

    def test_invalid_unicode_is_reported(self):
        with self.assertRaises(ImportFailure):
            digest({"texto": "\ud800"})


if __name__ == "__main__":
    unittest.main()
