"""Artefatos locais sem dependências externas e sem sobrescrever uma execução."""
import csv
import html
import json
from pathlib import Path


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def escape(value):
    return html.escape(str(value), quote=True)


def percent(value):
    return "Não se aplica" if value is None else f"{value:.1%}"


def render(report):
    summary = report["summary"]
    state = "Metas atendidas nesta suíte" if summary["quality_passed"] else "Há metas ou cenários não atendidos"
    rows = "".join(f'<tr><th>{escape(name)}</th><td>{percent(m["value"])}</td><td>{m["n"]}</td></tr>' for name, m in summary["metrics"].items())
    gates = "".join(f'<li>{escape(g["name"])}: meta {percent(g["expected"])}; obtido {percent(g["actual"])} — {"atendida" if g["passed"] else "não atendida"}</li>' for g in summary["gates"])
    pending = "".join(f'<li><strong>{escape(p["id"])}</strong>: {escape(p["reason"])}</li>' for p in report["pending_coverage"])
    cases = []
    for case in report["cases"]:
        failures = [c for c in case["checks"] if not c["passed"]]
        label = "PASSOU" if case["passed"] else ("ERRO DE EXECUÇÃO" if "error" in case else "FALHOU")
        details = {k: case[k] for k in ("expected", "actual", "messages", "error") if k in case}
        cases.append(f'<article class="{"ok" if case["passed"] else "fail"}"><h3>{escape(case["id"])} · {escape(case["title"])}</h3><p><b>{label}</b> · {escape(case["kind"])}</p>'
                     + (f'<pre>{escape(dump(failures))}</pre>' if failures else "")
                     + f'<details><summary>Resultado, resposta e referências</summary><pre>{escape(dump(details))}</pre></details>'
                     + f'<details><summary>Todas as verificações ({len(case["checks"])})</summary><pre>{escape(dump(case["checks"]))}</pre></details></article>')
    comparison = "Sem execução anterior informada." if report["comparison"] is None else dump(report["comparison"])
    metadata = {k: report[k] for k in ("suite", "inputs", "code_sha256", "python_version", "configuration", "execution_mode")}
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>Avaliação do suporte inteligente</title><style>
body{{font:16px/1.55 system-ui,sans-serif;color:#182c40;background:#f4f7fa;margin:0}}main{{max-width:1050px;margin:auto;padding:28px}}
h1,h2,h3{{line-height:1.25}}.lead,article{{background:white;border:1px solid #dce4eb;border-radius:10px;padding:20px;margin:18px 0}}
.ok{{border-left:5px solid #267855}}.fail{{border-left:5px solid #b94d24}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;background:#f4f6f9;padding:14px}}
table{{border-collapse:collapse;width:100%;background:white}}th,td{{text-align:left;border-bottom:1px solid #dce4eb;padding:8px}}summary{{cursor:pointer;margin:10px 0}}
@media(max-width:600px){{main{{padding:14px}}article{{padding:12px}}th,td{{padding:5px;font-size:14px}}}}</style></head><body><main>
<h1>Avaliação do suporte inteligente</h1><p>Gerado em {escape(report["created_at"])} (UTC)</p>
<section class="lead"><h2>{state}</h2><p><b>{summary["passed"]} de {summary["total"]}</b> cenários passaram; {summary["failed"]} falharam; {summary["execution_errors"]} erros de execução.</p>
<p>{escape(report["suite"]["purpose"])}</p><p>Rótulos sintéticos pendentes de revisão técnica. Resultados não equivalem à homologação da base real.</p></section>
<h2>Métricas</h2><table><thead><tr><th>Métrica</th><th>Resultado</th><th>Cenários</th></tr></thead><tbody>{rows}</tbody></table>
<p>Precision@k divide os acertos por k, mesmo com menos resultados. Recall e MRR consideram apenas consultas com fontes pertinentes; empty_correct apenas consultas negativas. As médias são por cenário. Erros de execução contam como falha. A taxa de resposta mede fidelidade, referências e mensagens verificáveis, não uma avaliação semântica por especialista.</p>
<h2>Metas declaradas</h2><ul>{gates}</ul><p>A aprovação exige todas as metas e todos os cenários atendidos.</p>
<h2>Cobertura pendente (não contabilizada como sucesso)</h2><ul>{pending}</ul>
<h2>Comparação</h2><pre>{escape(comparison)}</pre><h2>Cenários</h2>{''.join(cases)}
<h2>Rastreabilidade</h2><details><summary>Versões, configuração e hashes SHA-256</summary><pre>{escape(dump(metadata))}</pre></details>
<p>Consulte revisao-humana.csv para registrar parecer técnico. Alterações nesse arquivo não mudam os resultados automáticos.</p>
</main></body></html>'''


def write(report, output):
    output = Path(output)
    # Não apaga nem reutiliza diretórios existentes, mesmo que estejam vazios.
    output.mkdir(parents=True, exist_ok=False)
    (output / "relatorio.json").write_text(dump(report) + "\n", encoding="utf-8")
    (output / "relatorio.html").write_text(render(report), encoding="utf-8")
    with (output / "revisao-humana.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(["cenario", "titulo", "resultado_automatico", "rotulo_validado", "resposta_adequada", "referencias_corretas", "revisor", "data", "observacoes"])
        for case in report["cases"]:
            # Evita execução de fórmulas ao abrir rótulos externos em planilha.
            safe = lambda text: "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text
            writer.writerow([safe(case["id"]), safe(case["title"]), "passou" if case["passed"] else "falhou", "", "", "", "", "", ""])
    return output
