"""Histórico local com revisões por ID e ativação atômica de snapshots."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .validation import ImportFailure, KINDS, canonical, require, stage

DDL = """
CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY, package_id TEXT NOT NULL, version TEXT NOT NULL,
    catalog_hash TEXT NOT NULL, created_at TEXT NOT NULL, report TEXT NOT NULL,
    UNIQUE(package_id, version));
CREATE TABLE IF NOT EXISTS revisions (
    package_id TEXT NOT NULL, id TEXT NOT NULL, fingerprint TEXT NOT NULL,
    kind TEXT NOT NULL, payload TEXT NOT NULL, searchable INTEGER NOT NULL,
    PRIMARY KEY(package_id, id, fingerprint));
CREATE TABLE IF NOT EXISTS membership (
    snapshot_id TEXT NOT NULL REFERENCES snapshots(id), package_id TEXT NOT NULL,
    id TEXT NOT NULL, fingerprint TEXT NOT NULL,
    PRIMARY KEY(snapshot_id, id),
    FOREIGN KEY(package_id,id,fingerprint) REFERENCES revisions(package_id,id,fingerprint));
CREATE TABLE IF NOT EXISTS active_packages (
    package_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES snapshots(id));
CREATE TABLE IF NOT EXISTS import_runs (
    id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
    actor TEXT NOT NULL, status TEXT NOT NULL, report TEXT NOT NULL);
CREATE VIEW IF NOT EXISTS active_records AS
    SELECT m.package_id,m.snapshot_id,r.id,r.kind,r.payload,r.fingerprint,r.searchable
    FROM active_packages a JOIN membership m ON m.snapshot_id=a.snapshot_id
    JOIN revisions r ON r.package_id=m.package_id AND r.id=m.id AND r.fingerprint=m.fingerprint;
"""


def now():
    return datetime.now(timezone.utc).isoformat()


def connect(path):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=30)
    try:
        db.execute("PRAGMA foreign_keys=ON")
        # A primeira criação também precisa do bloqueio: outro processo não
        # pode observar tabelas novas com user_version ainda igual a zero.
        db.execute("BEGIN IMMEDIATE")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        require(version in (0, 1), "banco_incompativel", "Versão do armazenamento não suportada.")
        if version == 0:
            require(not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone(),
                    "banco_incompativel", "Use um arquivo novo ou um banco criado pelo importador.")
        for statement in DDL.split(";"):
            if statement.strip():
                db.execute(statement)
        db.execute("PRAGMA user_version=1")
        db.commit()
        return db
    except BaseException:
        db.close()
        raise


def _audit(db, run_id, started, actor, report):
    db.execute("INSERT INTO import_runs VALUES (?,?,?,?,?,?)",
               (run_id, started, now(), actor, report["estado"], canonical(report)))


def _changes(db, package_id, previous):
    db.execute("""CREATE TEMP TABLE previous AS
        SELECT r.id,r.fingerprint,r.kind,r.searchable FROM membership m JOIN revisions r
        ON r.package_id=m.package_id AND r.id=m.id AND r.fingerprint=m.fingerprint
        WHERE m.snapshot_id=? AND m.package_id=?""", (previous, package_id))
    db.execute("CREATE UNIQUE INDEX previous_id ON previous(id)")
    report = {}
    for kind in KINDS:
        added, updated, unchanged = db.execute("""SELECT
            COALESCE(SUM(p.id IS NULL),0),
            COALESCE(SUM(p.id IS NOT NULL AND p.fingerprint<>s.fingerprint),0),
            COALESCE(SUM(p.fingerprint=s.fingerprint),0)
            FROM incoming.staged s LEFT JOIN previous p ON p.id=s.id WHERE s.kind=?""", (kind,)).fetchone()
        removed = db.execute("""SELECT COUNT(*) FROM previous p LEFT JOIN incoming.staged s ON s.id=p.id
            WHERE p.kind=? AND s.id IS NULL""", (kind,)).fetchone()[0]
        lost = db.execute("""SELECT COUNT(*) FROM previous p LEFT JOIN incoming.staged s ON s.id=p.id
            WHERE p.kind=? AND p.searchable=1 AND (s.id IS NULL OR s.searchable=0)""", (kind,)).fetchone()[0]
        report[kind] = {"incluidos": added, "atualizados": updated, "inalterados": unchanged,
                        "retirados": removed, "retirados_da_pesquisa": lost}
    return report


def _activate(db, staged_path, report, run_id, started, actor):
    db.execute("ATTACH DATABASE ? AS incoming", (str(staged_path),))
    # Serializa escritores; comparações e mudança do ponteiro usam a mesma transação.
    db.execute("BEGIN IMMEDIATE")
    package_id, version = report["pacote_id"], report["pacote_versao"]
    existing = db.execute("SELECT id,catalog_hash FROM snapshots WHERE package_id=? AND version=?",
                          (package_id, version)).fetchone()
    active = db.execute("SELECT snapshot_id FROM active_packages WHERE package_id=?", (package_id,)).fetchone()
    if existing:
        require(existing[1] == report["catalogo_sha256"], "versao_alterada", "Uma versão já importada foi alterada. Gere uma nova versão.")
        require(active and active[0] == existing[0], "versao_historica", "Versão histórica não pode substituir silenciosamente a versão ativa.")
        report.update(estado="sem_alteracoes", snapshot_id=existing[0])
        report["alteracoes"] = _changes(db, package_id, active[0])
    else:
        snapshot_id = str(uuid.uuid4())
        report.update(estado="ativado", snapshot_id=snapshot_id)
        report["alteracoes"] = _changes(db, package_id, active[0] if active else None)
        db.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?)",
                   (snapshot_id, package_id, version, report["catalogo_sha256"], now(), canonical(report)))
        db.execute("""INSERT OR IGNORE INTO revisions
            SELECT ?,id,fingerprint,kind,payload,searchable FROM incoming.staged""", (package_id,))
        db.execute("""INSERT INTO membership SELECT ?,?,id,fingerprint FROM incoming.staged""", (snapshot_id, package_id))
        db.execute("""INSERT INTO active_packages VALUES (?,?)
            ON CONFLICT(package_id) DO UPDATE SET snapshot_id=excluded.snapshot_id""", (package_id, snapshot_id))
    _audit(db, run_id, started, actor, report)
    db.commit()
    return report


def import_package(catalog, database=None, *, validate_only=False, actor="operador_local", progress=None):
    """Valida em disco temporário; só então abre uma transação no armazenamento.

    Sem APIs externas. O acesso ao arquivo SQLite é administrativo. O consumidor
    futuro deve autorizar o usuário antes de devolver registros ou chamar modelos.
    """
    require(validate_only or database is not None, "banco_obrigatorio", "Informe o banco de destino.")
    require(isinstance(actor, str) and bool(actor.strip()), "operador_obrigatorio", "Identifique o operador da carga.")
    run_id, started = str(uuid.uuid4()), now()
    try:
        with tempfile.TemporaryDirectory(prefix="suporte-import-") as directory:
            staged_path = Path(directory) / "validated.sqlite3"
            with closing(sqlite3.connect(staged_path)) as staging:
                report = stage(catalog, staging, progress)
            report["execucao_id"] = run_id
            if validate_only:
                return {**report, "estado": "validado"}
            with closing(connect(database)) as db:
                try:
                    return _activate(db, staged_path, report, run_id, started, actor)
                except BaseException:
                    db.rollback()
                    raise
    except (ImportFailure, OSError, sqlite3.Error) as exc:
        detail = exc.detail if isinstance(exc, ImportFailure) else {
            "codigo": "erro_armazenamento", "mensagem": "Falha de leitura ou gravação; verifique caminhos, espaço, permissões e uso do banco."}
        report = {"estado": "rejeitado", "execucao_id": run_id, "erros": [detail], "ativacao_realizada": False}
        if not validate_only and database is not None:
            try:
                with closing(connect(database)) as db:
                    _audit(db, run_id, started, actor, report)
                    db.commit()
            except (OSError, sqlite3.Error, ImportFailure):
                report["auditoria_persistida"] = False
        return report


def inspect_database(path, *, history=False):
    path = Path(path).resolve()
    require(path.is_file(), "banco_ausente", "Banco de importação ainda não existe.")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        require(db.execute("PRAGMA user_version").fetchone()[0] == 1, "banco_incompativel", "Arquivo não é um banco do importador v1.")
        if history:
            rows = db.execute("SELECT started_at,finished_at,actor,report FROM import_runs ORDER BY rowid DESC LIMIT 100")
            return {"execucoes": [{"inicio": a, "fim": b, "operador": c, **json.loads(d)} for a, b, c, d in rows]}
        rows = db.execute("""SELECT s.report FROM active_packages a JOIN snapshots s ON s.id=a.snapshot_id ORDER BY s.package_id""")
        return {"pacotes_ativos": [json.loads(row[0]) for row in rows]}
