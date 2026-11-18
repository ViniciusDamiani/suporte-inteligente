"""Limpeza de texto usada pela busca e geração."""
import re
from .config import SearchError


def clean_text(text):
    try:
        text.encode("utf-8")
    except UnicodeError as exc:
        raise SearchError("Texto contém sequência Unicode inválida.") from exc
    # Reutiliza os padrões de CPF/CNPJ sem pontuação e telefone dos tickets.
    from api.text_utils import anonymize
    text = anonymize(text)
    # Mascaramento por padrões; não substitui revisão de dados confidenciais.
    text = re.sub(r"(?i)(?:[a-z]:[\\/]|\\\\|file://)[^\r\n\t\"'<>|;,]*", "[CAMINHO_REMOVIDO]", text)
    text = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "[EMAIL]", text)
    text = re.sub(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", "[CPF]", text)
    text = re.sub(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", "[CNPJ]", text)
    text = re.sub(r'''(?ix)\b(senha|password|token|api[_-]?key|authorization)["']?\s*[:=]\s*(?:"[^"\r\n]*"|'[^'\r\n]*'|(?:Bearer\s+)?[^\s,;}]+)''', r"\1=[REMOVIDO]", text)
    return text

