"""Contrato v1 do catálogo JSON e dos registros JSONL preparados."""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path, PureWindowsPath

SCHEMA_VERSION = "1.0.0"
SNAPSHOT_MODE = "snapshot_completo_dos_arquivos_preparados"
KINDS = ("fontes", "conhecimento", "recursos_banco", "vinculos")
HASH = re.compile(r"^[0-9a-f]{64}$")


class ImportFailure(ValueError):
    def __init__(self, code, message, file=None, line=None):
        super().__init__(message)
        self.detail = {"codigo": code, "mensagem": message}
        if file is not None:
            self.detail["arquivo"] = str(file)
        if line is not None:
            self.detail["linha"] = line


def require(condition, code, message):
    if not condition:
        raise ImportFailure(code, message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    try:
        return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()
    except UnicodeError as exc:
        raise ImportFailure("unicode_invalido", "Texto contém sequência Unicode inválida.") from exc


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "json_chave_duplicada", "JSON contém chave duplicada.")
        result[key] = value
    return result


def _constant(_):
    raise ImportFailure("json_numero_invalido", "NaN e Infinity não são valores JSON válidos.")


def _float(value):
    result = float(value)
    require(math.isfinite(result), "json_numero_invalido", "Número fora da faixa suportada.")
    return result


def parse_json(raw):
    try:
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, ImportFailure):
            raise
        raise ImportFailure("json_invalido", "Conteúdo JSON inválido ou codificação diferente de UTF-8.") from exc


def safe_path(base, relative):
    require(isinstance(relative, str) and bool(relative.strip()), "caminho_invalido", "Caminho relativo obrigatório.")
    win = PureWindowsPath(relative)
    require(not win.drive and not win.root and "\\" not in relative and ":" not in relative,
            "caminho_invalido", "Use caminhos relativos com barras normais, dentro do pacote.")
    require(all(part not in ("", ".", "..") for part in relative.split("/")),
            "caminho_invalido", "Caminho contém segmento vazio ou navegação para outra pasta.")
    target = (base / relative).resolve()
    require(target.is_relative_to(base.resolve()), "caminho_invalido", "Arquivo fora da pasta do catálogo.")
    require(target.is_file(), "arquivo_ausente", "Arquivo declarado não encontrado.")
    return target


def read_small(path, limit=4 * 1024 * 1024):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "arquivo_grande", "Arquivo excede o limite permitido.")
    return raw


def load_catalog(path):
    path = Path(path).resolve()
    raw = read_small(path)
    catalog = parse_json(raw)
    require(isinstance(catalog, dict), "catalogo_invalido", "Catálogo deve ser um objeto JSON.")
    if "catalogo" in catalog:
        pointer = catalog
        require(pointer.get("schema_versao") == SCHEMA_VERSION, "schema_incompativel", "Versão do apontador não suportada.")
        path = safe_path(path.parent, pointer["catalogo"])
        raw = read_small(path)
        require(hashlib.sha256(raw).hexdigest() == pointer.get("catalogo_sha256"),
                "hash_catalogo", "Hash do catálogo difere do apontador.")
        catalog = parse_json(raw)
        require(isinstance(catalog, dict) and catalog.get("pacote_versao") == pointer.get("pacote_preparado"),
                "versao_catalogo", "Versão do pacote difere do apontador.")
    require(catalog.get("schema_versao") == SCHEMA_VERSION, "schema_incompativel", "Somente o contrato 1.0.0 é suportado.")
    require(catalog.get("modo") == SNAPSHOT_MODE, "carga_parcial", "A carga exige uma versão completa do pacote.")
    for key in ("pacote_id", "pacote_versao"):
        require(isinstance(catalog.get(key), str) and bool(catalog[key].strip()), "catalogo_invalido", f"Campo {key} obrigatório.")
    require(isinstance(catalog.get("arquivos"), list) and bool(catalog["arquivos"]), "catalogo_invalido", "Lista de arquivos obrigatória.")
    for key in ("entidades", "vinculos"):
        require(type(catalog.get(key)) is int and catalog[key] >= 0, "catalogo_invalido", f"Contagem {key} inválida.")
    require(catalog.get("pendencias_estruturais") == 0, "pendencias", "Pacote declara pendências estruturais.")
    entries, seen, destinations = [], set(), set()
    for entry in catalog["arquivos"]:
        require(isinstance(entry, dict) and type(entry.get("importar")) is bool, "catalogo_invalido", "Cada entrada exige importar booleano.")
        if not entry["importar"]:
            continue
        relative = entry.get("arquivo")
        try:
            file_path = safe_path(path.parent, relative)
            require(file_path not in seen, "arquivo_duplicado", "Arquivo declarado mais de uma vez.")
            seen.add(file_path)
            kind = entry.get("destino_sugerido")
            require(kind in KINDS, "destino_invalido", "Destino de importação não suportado.")
            auxiliary = kind == "recursos_banco"
            require(entry.get("formato") == ("json" if auxiliary else "jsonl"), "formato_invalido", "Formato incompatível com o destino.")
            require(entry.get("papel") == ("recurso_auxiliar" if auxiliary else "registros"), "papel_invalido", "Papel incompatível com o destino.")
            require(type(entry.get("bytes")) is int and entry["bytes"] >= 0, "catalogo_invalido", "Tamanho inválido.")
            require(isinstance(entry.get("sha256"), str) and HASH.fullmatch(entry["sha256"]), "catalogo_invalido", "SHA-256 inválido.")
            require((auxiliary and entry.get("registros") is None) or
                    (not auxiliary and type(entry.get("registros")) is int and entry["registros"] >= 0),
                    "catalogo_invalido", "Contagem de registros inválida.")
        except ImportFailure as exc:
            exc.detail["arquivo"] = str(relative)
            raise
        destinations.add(kind)
        entries.append((entry, file_path))
    require({"fontes", "conhecimento", "vinculos"} <= destinations, "carga_incompleta", "Pacote deve declarar fontes, conhecimento e vínculos.")
    return catalog, hashlib.sha256(raw).hexdigest(), entries


def text_fields(record, names):
    for name in names:
        require(isinstance(record.get(name), str) and bool(record[name].strip()), "campo_obrigatorio", f"Campo {name} deve ser texto não vazio.")


def validate_record(record, kind):
    require(isinstance(record, dict), "registro_invalido", "Registro deve ser objeto JSON.")
    text_fields(record, ("id",))
    require(record["id"] == record["id"].strip(), "id_invalido", "ID não pode ter espaços nas extremidades.")
    if kind == "fontes":
        text_fields(record, ("tipo", "arquivo_relativo", "disponibilidade"))
        require(record.get("acesso_automatico_ao_caminho") is False, "acesso_fonte", "Fonte deve proibir acesso automático ao caminho.")
        require(record["id"].startswith("fonte:"), "id_invalido", "Fonte deve ter prefixo fonte:.")
    elif kind == "vinculos":
        text_fields(record, ("origem_id", "destino_id", "relacao", "estado", "origem_vinculo"))
        require(record["id"].startswith("vinculo:"), "id_invalido", "Vínculo deve ter prefixo vinculo:.")
        require(type(record.get("prova_de_causalidade")) is bool and isinstance(record.get("condicao_documentada"), str),
                "vinculo_invalido", "Condição ou prova de causalidade inválida.")
    else:
        fields = {"id", "tipo", "grupo_conhecimento", "id_origem", "origem", "metadados", "dados", "conteudo_sha256"}
        require(set(record) == fields, "envelope_invalido", "Campos do envelope diferem do contrato 1.0.0.")
        text_fields(record, ("tipo", "id_origem", "conteudo_sha256"))
        require(record["id"] == record["tipo"] + ":" + record["id_origem"], "id_invalido", "ID deve combinar tipo e ID de origem.")
        require(record["grupo_conhecimento"] in ("Tickets", "Regras de Negocio", "Processos", "Transversal"), "grupo_invalido", "Grupo desconhecido.")
        origin = record["origem"]
        require(isinstance(origin, dict) and set(origin) == {"arquivo_relativo", "registro_id"}, "origem_invalida", "Procedência incompleta.")
        text_fields(origin, ("arquivo_relativo", "registro_id"))
        metadata = record["metadados"]
        required = {"cliente_referencia", "versao_referencia", "estado_revisao", "permissao_de_acesso_requerida", "apto_recomendacao_automatica", "indexacao"}
        optional = {"disponivel_pesquisa", "uso_na_recomendacao", "finalidade"}
        require(isinstance(metadata, dict) and required <= metadata.keys() and metadata.keys() <= required | optional,
                "metadados_invalidos", "Metadados diferem do contrato 1.0.0.")
        for key in ("cliente_referencia", "versao_referencia"):
            require(metadata[key] is None or isinstance(metadata[key], str), "metadados_invalidos", f"Campo {key} deve ser texto ou nulo.")
        text_fields(metadata, ("estado_revisao", "indexacao"))
        require(metadata["permissao_de_acesso_requerida"] is True and metadata["apto_recomendacao_automatica"] is False
                and metadata["indexacao"] == "nao_executada", "politica_invalida", "Preserve acesso obrigatório, revisão e ausência de indexação do contrato v1.")
        for key in optional & metadata.keys():
            expected = bool if key == "disponivel_pesquisa" else str
            require(type(metadata[key]) is expected, "metadados_invalidos", f"Tipo inválido para {key}.")
        require(isinstance(record["dados"], dict), "dados_invalidos", "Dados devem ser um objeto JSON.")
        require(HASH.fullmatch(record["conteudo_sha256"]) and digest(record["dados"]) == record["conteudo_sha256"],
                "hash_conteudo", "Hash do conteúdo difere dos dados do registro.")


def stage(catalog_path, connection, progress=None):
    """Valida bytes realmente lidos e prepara uma base temporária descartável."""
    catalog, catalog_hash, entries = load_catalog(catalog_path)
    connection.execute("""CREATE TABLE staged (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
        fingerprint TEXT NOT NULL, searchable INTEGER NOT NULL,
        origin TEXT, destination TEXT, file TEXT NOT NULL, line INTEGER)""")
    counts = dict.fromkeys(KINDS, 0)
    files = []
    for entry, path in sorted(entries, key=lambda pair: KINDS.index(pair[0]["destino_sugerido"])):
        relative, kind = entry["arquivo"], entry["destino_sugerido"]
        if progress:
            progress(relative)
        hasher, size, count, line_number = hashlib.sha256(), 0, 0, None
        try:
            with path.open("rb") as stream:
                if kind == "recursos_banco":
                    raw = stream.read(64 * 1024 * 1024 + 1)
                    require(len(raw) <= 64 * 1024 * 1024, "arquivo_grande", "Recurso auxiliar excede 64 MiB.")
                    hasher.update(raw)
                    size = len(raw)
                    record = parse_json(raw)
                    require(isinstance(record, (dict, list)), "recurso_invalido", "Recurso auxiliar deve ser objeto ou lista JSON.")
                    payload = canonical(record)
                    connection.execute("INSERT INTO staged VALUES (?,?,?,?,?,?,?,?,?)",
                                       ("recurso:" + relative, kind, payload, digest(record), 0, None, None, relative, None))
                    count = 1
                else:
                    line_number = 0
                    while True:
                        raw = stream.readline(16 * 1024 * 1024 + 1)
                        if not raw:
                            break
                        line_number += 1
                        require(len(raw) <= 16 * 1024 * 1024, "linha_grande", "Linha JSONL excede 16 MiB.")
                        hasher.update(raw)
                        size += len(raw)
                        require(bool(raw.strip()), "linha_vazia", "JSONL não deve conter linhas vazias.")
                        record = parse_json(raw)
                        validate_record(record, kind)
                        payload = canonical(record)
                        # Ausência de elegibilidade explícita não autoriza pesquisa.
                        searchable = int(kind == "conhecimento" and record["metadados"].get("disponivel_pesquisa") is True)
                        connection.execute("INSERT INTO staged VALUES (?,?,?,?,?,?,?,?,?)", (
                            record["id"], kind, payload, digest(record), searchable,
                            record.get("origem_id") if kind == "vinculos" else None,
                            record.get("destino_id") if kind == "vinculos" else None, relative, line_number))
                        count += 1
            require(size == entry["bytes"], "tamanho_arquivo", "Tamanho do arquivo difere do catálogo.")
            require(hasher.hexdigest() == entry["sha256"], "hash_arquivo", "Hash do arquivo difere do catálogo.")
            require(kind == "recursos_banco" or count == entry["registros"], "contagem_arquivo", "Contagem de registros difere do catálogo.")
        except sqlite3.IntegrityError as exc:
            raise ImportFailure("id_duplicado", "ID repetido no pacote.", relative, line_number) from exc
        except ImportFailure as exc:
            exc.detail.update({"arquivo": relative})
            if line_number is not None:
                exc.detail["linha"] = line_number
            raise
        counts[kind] += count
        files.append({"arquivo": relative, "registros": count, "bytes": size})
    require(counts["conhecimento"] == catalog["entidades"] and counts["vinculos"] == catalog["vinculos"],
            "contagem_pacote", "Contagens totais diferem do catálogo.")
    orphan = connection.execute("""SELECT l.file,l.line FROM staged l
        LEFT JOIN staged a ON a.id=l.origin AND a.kind IN ('fontes','conhecimento')
        LEFT JOIN staged b ON b.id=l.destination AND b.kind IN ('fontes','conhecimento')
        WHERE l.kind='vinculos' AND (a.id IS NULL OR b.id IS NULL) LIMIT 1""").fetchone()
    if orphan:
        raise ImportFailure("vinculo_orfao", "Origem ou destino do vínculo não existe entre fontes e entidades.", *orphan)
    connection.commit()
    return {"pacote_id": catalog["pacote_id"], "pacote_versao": catalog["pacote_versao"],
            "catalogo_sha256": catalog_hash, "contagens": counts, "arquivos": files}
