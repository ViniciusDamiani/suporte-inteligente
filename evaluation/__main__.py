"""Uso: python -m evaluation [--saida pasta_nova] [--comparar relatorio.json]."""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .reports import write
from .runner import DEFAULT_CORPUS, DEFAULT_SUITE, ROOT, run
from .validation import EvaluationError


def main(argv=None):
    parser = argparse.ArgumentParser(description="Avaliação offline de busca e triagem com cenários versionados.")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE, help="JSON de cenários e expectativas")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS, help="JSON de tickets sintéticos")
    parser.add_argument("--saida", type=Path, help="Diretório novo para relatórios (não sobrescreve)")
    parser.add_argument("--comparar", type=Path, help="relatorio.json de uma execução anterior")
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.saida or ROOT / "instance" / "evaluation" / stamp
    try:
        if output.exists():
            raise EvaluationError("A pasta de saída já existe. Informe uma pasta nova para preservar o histórico.")
        report = run(args.suite, args.corpus, args.comparar)
        write(report, output)
    except (EvaluationError, OSError, ValueError) as exc:
        print(f"Avaliação não concluída: {exc}", file=sys.stderr)
        return 2
    summary = report["summary"]
    print(f"Avaliação concluída: {summary['passed']}/{summary['total']} cenários passaram; {summary['execution_errors']} erros de execução.")
    for case in report["cases"]:
        if not case["passed"]:
            print(f"  {case['id']}: {case.get('error') or ', '.join(sorted({c['name'] for c in case['checks'] if not c['passed']}))}")
    print(f"Relatório: {(output / 'relatorio.html').resolve()}")
    if report["comparison"] and not report["comparison"]["compatible"]:
        print("Comparação indisponível: " + report["comparison"]["reason"])
    print("Metas atendidas." if summary["quality_passed"] else "Qualidade ainda abaixo dos critérios declarados; consulte as falhas no relatório.")
    return 0 if summary["quality_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
