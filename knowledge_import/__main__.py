"""Execute: python -m knowledge_import --help."""
import argparse
import getpass
import json
import sqlite3
import sys
from pathlib import Path

from .storage import import_package, inspect_database
from .validation import ImportFailure

PROJECT = Path(__file__).resolve().parent.parent


def main(argv=None):
    parser = argparse.ArgumentParser(description="Valida e importa o catálogo JSON do conhecimento para armazenamento local versionado.")
    parser.add_argument("comando", choices=("validar", "importar", "status", "historico"))
    parser.add_argument("--catalogo", type=Path, default=PROJECT / "DataSetBase" / "CATALOGO_IMPORTACAO.json")
    parser.add_argument("--banco", type=Path, default=PROJECT / "instance" / "knowledge.sqlite3")
    parser.add_argument("--relatorio", type=Path, help="Grava o resultado JSON também neste arquivo.")
    parser.add_argument("--operador", default=getpass.getuser())
    parser.add_argument("--atualizar-busca", action="store_true", help="Após importar, prepara a busca híbrida local (modelo deve estar instalado).")
    args = parser.parse_args(argv)
    if args.atualizar_busca and args.comando != "importar":
        parser.error("--atualizar-busca só pode ser usado com importar.")
    try:
        if args.relatorio:
            output = args.relatorio.resolve()
            # Evita sobrescrever qualquer entrada do pacote ou o próprio banco.
            if output == args.banco.resolve() or output.is_relative_to(args.catalogo.resolve().parent):
                raise ImportFailure("relatorio_invalido", "Grave o relatório fora da pasta do catálogo e separado do banco.")
            if output.exists():
                raise ImportFailure("relatorio_existente", "Escolha um nome novo para o relatório.")
            output.parent.mkdir(parents=True, exist_ok=True)
        if args.comando in ("status", "historico"):
            result = inspect_database(args.banco, history=args.comando == "historico")
        else:
            result = import_package(args.catalogo, args.banco, validate_only=args.comando == "validar",
                                    actor=args.operador, progress=lambda name: print(f"Validando {name}", file=sys.stderr))
        search_failed = False
        if args.atualizar_busca and result.get("estado") in ("ativado", "sem_alteracoes"):
            try:
                from dataclasses import replace
                from dotenv import load_dotenv
                from knowledge_search.config import Settings
                from knowledge_search.embeddings import get_embedder
                from knowledge_search.storage import build
                load_dotenv(PROJECT / ".env")
                settings = replace(Settings.from_env(), source=args.banco)
                result["busca"] = build(settings, get_embedder(settings), lambda message: print(message, file=sys.stderr, flush=True))
            except (ValueError, OSError, sqlite3.Error, ImportError) as exc:
                search_failed = True
                result["busca"] = {"estado": "pendente", "erro": str(exc), "importacao_preservada": True}
        if args.relatorio:
            with args.relatorio.open("x", encoding="utf-8") as output:
                json.dump(result, output, ensure_ascii=False, indent=2)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if search_failed else (1 if result.get("estado") == "rejeitado" else 0)
    except (ImportFailure, OSError, sqlite3.Error) as exc:
        detail = exc.detail if isinstance(exc, ImportFailure) else {"codigo": "erro_arquivo", "mensagem": str(exc)}
        print(json.dumps({"estado": "erro", "erros": [detail]}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
