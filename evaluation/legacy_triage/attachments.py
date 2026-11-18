"""Leitura determinística de anexos. Conteúdo recebido nunca é executado."""
import csv
import hashlib
import io
import json
import re
import unicodedata
import uuid
from datetime import datetime
from pathlib import PurePosixPath

from knowledge_import.validation import ImportFailure, parse_json
from .model import TriageError, check

MAX_BYTES = 2 * 1024 * 1024
MAX_LINES = 20000
MAX_FINDINGS = 500
SUPPORTED = {".txt", ".log", ".csv", ".json", ".jsonl"}


def clean_text(text):
    try:
        text.encode("utf-8")
    except UnicodeError as exc:
        raise TriageError("Texto contém sequência Unicode inválida.") from exc
    # Mascaramento por padrões; não substitui revisão de dados confidenciais.
    text = re.sub(r"(?i)(?:[a-z]:[\\/]|\\\\|file://)[^\r\n\t\"'<>|;,]*", "[CAMINHO_REMOVIDO]", text)
    text = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "[EMAIL]", text)
    text = re.sub(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", "[CPF]", text)
    text = re.sub(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", "[CNPJ]", text)
    text = re.sub(r'''(?ix)\b(senha|password|token|api[_-]?key|authorization)["']?\s*[:=]\s*(?:"[^"\r\n]*"|'[^'\r\n]*'|(?:Bearer\s+)?[^\s,;}]+)''', r"\1=[REMOVIDO]", text)
    return text


def normalize(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


PATTERNS = (
    ("write_skipped", r"\bwrite ski(?:p|pp)ed\b", "Registro de escrita ignorada; não comprova envio."),
    ("write_error", r"escrita com problemas|write error|falha (?:na |de )?escrita", "Registro de problema de escrita; requer correlação com comando e endereço."),
    ("write_ok", r"escrita ok|write success", "API registrou sucesso de escrita; não comprova movimento físico."),
    ("write_command", r"escreveu\s*->\s*programa", "Comando registrado no PLCWrite; valor depende do cadastro e protocolo."),
    ("route_test", r"test interlock road|verify test road|teste de intertravamento da rota", "Teste de rota registrado; o marcador não informa aprovação."),
    ("route_stopping", r"start stopping|stop normal transport", "Solicitação de parada registrada; não comprova encerramento."),
    ("route_stopped", r"\bstopped\b", "Marcador de parada encontrado; conferir rota e significado na versão instalada."),
    ("route_start", r"\btransport road\b", "Marcador de transporte de rota; não confirma sozinho acionamento físico."),
    ("route_status", r"transport status|transport unit:", "Registro de estado do transporte."),
    ("route_erased", r"erase road", "Registro de limpeza de rota; requer interpretação conforme a versão."),
    ("production_erased", r"apagou a unit de transporte", "O número desta mensagem pode ser produção; não foi interpretado como Unit."),
    ("unit_event", r"\b(?:ocupacao|encerramento)\b|log[_ ]unit|log reg", "Registro relacionado à ocupação/encerramento; conferir identificadores."),
    ("alarm", r"\balarme\b|\balarm\b|\bintertravamento\b", "Menção a alarme/intertravamento; verificar texto integral, estado e contexto."),
)


def _decode(raw):
    check(raw and len(raw) <= MAX_BYTES, "Anexe um arquivo não vazio de até 2 MiB.", 413 if len(raw) > MAX_BYTES else 400)
    try:
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            text = raw.decode("utf-16")
            encoding = "UTF-16"
        else:
            try:
                text, encoding = raw.decode("utf-8-sig"), "UTF-8"
            except UnicodeDecodeError:
                text, encoding = raw.decode("cp1252"), "Windows-1252"
    except UnicodeError as exc:
        raise TriageError("Codificação não reconhecida. Exporte o texto em UTF-8.") from exc
    check(not any(ord(c) < 32 and c not in "\r\n\t" for c in text), "Arquivo contém dados binários ou caracteres de controle.")
    check(len(text.splitlines()) <= MAX_LINES, "Arquivo excede 20.000 linhas; recorte o período pertinente.")
    return text, encoding


def _records(text, suffix):
    if suffix == ".csv":
        try:
            delimiter = csv.Sniffer().sniff(text[:8192], delimiters=",;\t").delimiter
            reader = csv.DictReader(io.StringIO(text), delimiter=delimiter, strict=True)
            check(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)), "Cabeçalhos CSV ausentes ou repetidos.")
            for row in reader:
                check(None not in row and all(v is not None for v in row.values()), "Linha CSV possui quantidade incorreta de colunas.")
                yield f"linha {reader.line_num}", json.dumps(row, ensure_ascii=False)
        except csv.Error as exc:
            raise TriageError("CSV inválido. Use cabeçalho e separador vírgula, ponto e vírgula ou tabulação.") from exc
    elif suffix == ".json":
        try:
            data = parse_json(text.encode("utf-8"))
        except ImportFailure as exc:
            raise TriageError(exc.detail["mensagem"]) from exc
        prefix = ""
        if isinstance(data, dict):
            for key in ("registros", "eventos", "records", "events"):
                if isinstance(data.get(key), list):
                    data, prefix = data[key], "/" + key
                    break
        records = data if isinstance(data, list) else [data]
        check(len(records) <= MAX_LINES, "JSON excede 20.000 registros.")
        for index, row in enumerate(records):
            check(isinstance(row, dict), "Cada registro JSON deve ser um objeto.")
            yield f"JSON {prefix}/{index}" if isinstance(data, list) else "JSON /", json.dumps(row, ensure_ascii=False)
    else:
        for index, line in enumerate(text.splitlines(), 1):
            if suffix == ".jsonl" and line.strip():
                try:
                    check(isinstance(parse_json(line.encode("utf-8")), dict), "Cada linha JSONL deve conter um objeto.")
                except ImportFailure as exc:
                    raise TriageError(f"JSONL inválido na linha {index}.") from exc
            yield f"linha {index}", line


def _timestamp(line):
    pattern = r"\b(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})[ T](\d{2}:\d{2}(?::\d{2}(?:[.,]\d{1,6})?)?)(Z|[+-]\d{2}:?\d{2})?"
    match = re.search(pattern, line)
    if not match:
        return None
    date, time, zone = match.groups()
    if "/" in date:
        date = "-".join(reversed(date.split("/")))
    try:
        return datetime.fromisoformat(date + "T" + time.replace(",", ".") + (zone or "")).isoformat()
    except ValueError:
        return None


def interpret(filename, raw, request_id, occurrence_confirmed=False):
    check(isinstance(filename, str) and filename, "Nome do anexo obrigatório.")
    name = PurePosixPath(filename.replace("\\", "/")).name
    check(len(name) <= 200, "Nome do arquivo muito longo.")
    suffix = PurePosixPath(name).suffix.lower()
    check(suffix in SUPPORTED, "Leitura automática disponível para TXT, LOG, CSV, JSON e JSONL. Para imagem ou PDF, anexe uma exportação textual ou transcrição identificada.", 415)
    text, encoding = _decode(raw)
    findings, record_count, truncated = [], 0, False
    for location, line in _records(text, suffix):
        check(len(line) <= 32000, "Registro muito longo; exporte trechos menores.")
        record_count += 1
        check(record_count <= MAX_LINES, "Arquivo excede 20.000 registros.")
        value = normalize(line)
        unit_match = re.search(r"\bunit[\"']?\s*[:=]\s*[\"']?(\d{1,12})\b", value)
        unit = unit_match[1] if unit_match and "apagou a unit de transporte" not in value else None
        for event_type, pattern, explanation in PATTERNS:
            if re.search(pattern, value):
                if len(findings) >= MAX_FINDINGS:
                    truncated = True
                    break
                findings.append({"id": str(uuid.uuid4()), "type": event_type, "location": location,
                                 "timestamp": _timestamp(line), "unit": unit,
                                 "snippet": clean_text(line)[:1000], "interpretation": explanation})
    check(record_count > 0, "O arquivo não contém registros para analisar.")
    # Valida Unicode também nos campos que vieram de sequências escapadas JSON.
    try:
        json.dumps(findings, ensure_ascii=False).encode("utf-8")
    except UnicodeError as exc:
        raise TriageError("Texto contém sequência Unicode inválida.") from exc
    return {"id": str(uuid.uuid4()), "name": clean_text(name), "request_id": request_id,
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "encoding": encoding,
            "occurrence_confirmed": occurrence_confirmed, "records": record_count,
            "findings": findings, "truncated": truncated,
            "preview": clean_text(text[:1000]), "original_stored": False}
