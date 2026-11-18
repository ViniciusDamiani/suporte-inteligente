import argparse
import json
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv

from .config import ROOT, SearchError, Settings
from .embeddings import get_embedder, prepare_model
from .service import SearchService
from .storage import build


def main(argv=None):
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Busca local no acervo JSON importado, sem API de LLM.")
    parser.add_argument("comando", choices=("preparar-modelo", "indexar", "status", "buscar"))
    parser.add_argument("--banco", type=Path, help="Banco de conhecimento gerado pelo importador")
    parser.add_argument("--indice", type=Path, help="Arquivo SQLite separado para o índice")
    parser.add_argument("--modelo-dir", type=Path, help="Pasta dos arquivos ONNX locais")
    parser.add_argument("--somente-texto", action="store_true", help="Prepara apenas a parte textual; não representa busca híbrida")
    parser.add_argument("--consulta", help="Texto a pesquisar")
    parser.add_argument("--relatorio", type=Path, help="Arquivo novo para o relatório JSON")
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env()
        settings = replace(settings, **{key: value for key, value in (("source", args.banco), ("index", args.indice), ("model_dir", args.modelo_dir)) if value is not None})
        if args.relatorio and (args.relatorio.exists() or args.relatorio.resolve() in (settings.source.resolve(), settings.index.resolve()) or args.relatorio.resolve().is_relative_to(settings.model_dir.resolve())):
            raise SearchError("Escolha um relatório novo e separado dos bancos e arquivos do modelo.", 400)
        progress = lambda message: print(message, file=sys.stderr, flush=True)
        if args.comando == "preparar-modelo":
            result = prepare_model(settings.model_dir, progress)
        elif args.comando == "indexar":
            result = build(settings, None if args.somente_texto else get_embedder(settings), progress)
        elif args.comando == "buscar":
            result = SearchService(settings).search(args.consulta)
        else:
            result = SearchService(settings).status()
        encoded = json.dumps(result, ensure_ascii=False, indent=2)
        if args.relatorio:
            args.relatorio.parent.mkdir(parents=True, exist_ok=True)
            with args.relatorio.open("x", encoding="utf-8") as stream:
                stream.write(encoded + "\n")
        print(encoded)
        return 0
    except (SearchError, sqlite3.Error, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
