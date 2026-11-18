"""Projeção explícita dos casos autorizados; dados administrativos não viram contexto."""
import hashlib
import json
import re

from .text import clean_text

PROJECTION_VERSION = "caso-ticket-v1-chars1000-overlap120"
FIELDS = (
    ("area_tecnica", "Área técnica"),
    ("problema_normalizado", "Problema normalizado"),
    ("problema_relatado", "Problema relatado"),
    ("diagnostico_documentado", "Diagnóstico documentado"),
    ("solucao_documentada", "Solução documentada"),
    ("solucao_candidata", "Solução candidata"),
    ("resultado_documentado", "Resultado documentado"),
    ("pendencias", "Pendências"),
    ("versao_cliente", "Versão da ocorrência histórica"),
    ("versao_corrigida", "Versão corrigida informada"),
    ("aplicabilidade_ao_caso_atual", "Aplicabilidade"),
)


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def project(row):
    payload = json.loads(row["payload"])
    metadata, data = payload.get("metadados", {}), payload.get("dados", {})
    if row["kind"] != "conhecimento" or row["searchable"] != 1 or metadata.get("disponivel_pesquisa") is not True:
        return None
    # Outros tipos exigem um contrato de conteúdo próprio. Não indexar JSON bruto.
    if payload.get("tipo") != "caso_ticket" or not isinstance(data, dict):
        return None
    title = clean_text(str(data.get("assunto") or data.get("problema_normalizado") or row["id"]))[:180]
    parts, seen = [], set()
    for field, label in FIELDS:
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        value = clean_text(value.strip())
        if value in seen:
            continue
        seen.add(value)
        parts.append(label + ": " + value)
    body = "\n\n".join(parts)
    if not body:
        return None
    key = digest(row["package_id"] + "\0" + row["id"])
    origin = payload.get("origem", {})
    # Referências são texto, jamais caminhos abertos ou links fornecidos pelo arquivo.
    source = {k: str(origin.get(k, "")) for k in ("arquivo_relativo", "registro_id")}
    meta = {k: metadata.get(k) for k in ("estado_revisao", "uso_na_recomendacao", "apto_recomendacao_automatica", "versao_referencia")}
    return {"key": key, "package_id": row["package_id"], "source_id": row["id"], "fingerprint": row["fingerprint"],
            "title": title, "body": body, "metadata": meta, "origin": source}


def chunks(document, embedder=None):
    body, start, number = document["body"], 0, 0
    while start < len(body):
        end = min(start + 1000, len(body))
        if end < len(body):
            boundary = max(body.rfind("\n", start + 600, end), body.rfind(" ", start + 600, end))
            if boundary > start:
                end = boundary
        if embedder:
            while not embedder.fits(document["title"] + "\n" + body[start:end]):
                if end - start <= 32:
                    raise ValueError("Título ou trecho não cabe no modelo de embeddings.")
                end = start + (end - start) // 2
        text = body[start:end]
        if text.strip():
            number += 1
            embedded_text = document["title"] + "\n" + text
            yield {"key": digest(document["key"] + f":{start}:{end}"), "document_key": document["key"],
                   "position": number, "start": start, "end": end, "title": document["title"],
                   "text": text, "embedding_text": embedded_text, "embedding_hash": digest(embedded_text)}
        if end == len(body):
            break
        start = max(start + 1, end - min(120, (end - start) // 4))


def valid_query(value):
    from .config import SearchError
    if not isinstance(value, str) or not 2 <= len(value.strip()) <= 2000:
        raise SearchError("Descreva a busca usando entre 2 e 2.000 caracteres.", 400)
    if not re.search(r"[^\W_]", value, flags=re.UNICODE):
        raise SearchError("Informe palavras ou um código para pesquisar.", 400)
    return clean_text(value.strip())
