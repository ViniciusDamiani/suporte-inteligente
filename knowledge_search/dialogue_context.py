"""Texto para recuperação separado do histórico enviado ao modelo."""
import re

from api.text_utils import keywords, normalize

# Termos que não distinguem sintomas. Não alteram o índice nem a busca antiga.
GENERIC = set(keywords("problema problemas erro erros falha falhas generico generica relatado relatada "
                       "relata relatando informado informada informa informando apresenta apresentando "
                       "apresentado apresentada ocorre ocorrendo especifico especifica sistema "
                       "senhor senhora sr sra contato telefone ligou chamado ticket entrou unidade unit units unity"))

# Instruções de conversa não descrevem o equipamento nem o sintoma pesquisado.
CONVERSATIONAL = set(keywords("estou estamos tenho tendo preciso gostaria ajuda ajudar identificar causa "
                             "mostre mostrar sugira sugerir opcoes alternativas escolher escolha situacoes "
                             "parecido parecida parecidos parecidas semelhante semelhantes parece caso casos "
                             "existe existem algum alguma alguns algumas anterior anteriores aquele atendimento "
                             "feito fazer realizado registrada registrado conhecido resultado resposta responder "
                             "pergunta detalhe detalhes descrever explicar entendi saber consiga consegue poderia "
                             "pode podem sei sabemos quero quer queria conseguir"))

# Componentes deste acervo. São restrições locais, nunca fatos inferidos para a resposta.
TOPICS = {"unit", "plc", "clp", "scada", "supervisorio", "servidor", "viewer", "redler",
          "misturador", "dosagem", "balanca", "sensor", "impressora", "login"}


def topic_terms(turns):
    message = re.sub(r"\bunity\b", "unit", turns[0]["message"], flags=re.I)
    return sorted(set(keywords(message)) & TOPICS)


def technical_terms(text):
    return {term for term in keywords(text, limit=1000) if term not in GENERIC and not term.isdigit()}


def informative_option(label, history=""):
    # Uma alternativa precisa acrescentar algo ao componente já informado.
    return bool(technical_terms(label) - set(keywords(history, limit=1000)))


def retrieval_query(turns):
    parts, seen = [], set()
    for turn in turns:
        message = turn["message"]
        # Variação usada pelos atendentes neste acervo industrial: Unity -> Unit.
        # O relato original permanece intacto no contexto do modelo e na sessão.
        message = re.sub(r"\bunity\b", "unit", message, flags=re.I)
        if normalize(message).strip(" .!?") in ("sim", "nao") and turn.get("asked"):
            message = turn["asked"] + " " + message
        tokens = [term for term in keywords(message, limit=200) if term not in CONVERSATIONAL]
        # Conserva o componente, retirando 'problema/erro' quando há um assunto.
        message = " ".join(term for term in tokens if term not in GENERIC or term in TOPICS)
        key = normalize(message)
        if key and key not in seen:
            seen.add(key)
            parts.append(message[:300])
    return "\n".join(parts)[:1800]


def symptom_text(text):
    """Retira aberturas de contato sem transformar o relato técnico em fato novo."""
    text = re.split(r"\n\s*\d{1,2}:\d{2}", text, maxsplit=1)[0].strip()
    match = re.search(r"\b(?:relatando|informando|relata|informa|informou|relatou|diz|diiz)\b\s*(?:que\s+)?", text[:250], re.I)
    return text[match.end():].strip() if match else text


def projected_sections(text):
    from .documents import FIELDS
    labels = {label for _, label in FIELDS}
    sections, current = {}, None
    for paragraph in text.split("\n\n"):
        label, separator, value = paragraph.partition(": ")
        if separator and label in labels:
            current = label
            sections[current] = value
        elif current:
            sections[current] += "\n\n" + paragraph
    return sections
