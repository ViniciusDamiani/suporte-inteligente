import json
import sqlite3
import tempfile
import time
from contextlib import closing, contextmanager
from pathlib import Path

from api.text_utils import keywords
from .config import SearchError
from .documents import PROJECTION_VERSION, chunks, digest, project

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE documents (key TEXT PRIMARY KEY,package_id TEXT NOT NULL,source_id TEXT NOT NULL,
 fingerprint TEXT NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL,metadata TEXT NOT NULL,origin TEXT NOT NULL);
CREATE TABLE chunks (id INTEGER PRIMARY KEY,key TEXT UNIQUE NOT NULL,document_key TEXT NOT NULL REFERENCES documents(key),
 position INTEGER NOT NULL,start INTEGER NOT NULL,end INTEGER NOT NULL,title TEXT NOT NULL,text TEXT NOT NULL,
 embedding_hash TEXT NOT NULL,vector BLOB);
CREATE INDEX chunks_document ON chunks(document_key);
CREATE INDEX chunks_embedding ON chunks(embedding_hash);
CREATE VIRTUAL TABLE search_fts USING fts5(title,body,tokenize='unicode61 remove_diacritics 2');
"""


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@contextmanager
def readonly(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise SearchError("Base local ainda não preparada. Execute a importação e a indexação do acervo.")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        yield db


def source_signature(db):
    if db.execute("PRAGMA user_version").fetchone()[0] != 1:
        raise SearchError("O arquivo de origem não é um banco válido do importador.")
    rows = db.execute("SELECT package_id,snapshot_id FROM active_packages ORDER BY package_id").fetchall()
    return digest(json_text([list(r) for r in rows]))


def open_index(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        app_id = db.execute("PRAGMA application_id").fetchone()[0]
        if version and (version != 1 or app_id != 1398100050):
            raise SearchError("Arquivo de índice incompatível. Use um caminho separado do banco de importação.")
        if not version:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone():
                raise SearchError("O índice precisa de um arquivo novo ou criado pela busca.")
            db.executescript(SCHEMA)
            db.execute("PRAGMA application_id=1398100050")
            db.execute("PRAGMA user_version=1")
            db.commit()
        db.execute("PRAGMA journal_mode=WAL")
        return db
    except BaseException:
        db.close()
        raise


def metadata(db):
    if db.execute("PRAGMA application_id").fetchone()[0] != 1398100050:
        raise SearchError("Arquivo não é um índice da busca local.")
    return {row[0]: json.loads(row[1]) for row in db.execute("SELECT key,value FROM meta")}


def check_current(source, index):
    info = metadata(index)
    if not info or info.get("projection") != PROJECTION_VERSION:
        raise SearchError("Índice ainda não preparado ou formato desatualizado. Execute indexar.")
    if info["source_signature"] != source_signature(source):
        raise SearchError("O acervo mudou após a indexação. Atualize o índice antes de pesquisar.")
    return info


def build(settings, embedder=None, progress=lambda message: None):
    if settings.index.resolve() == settings.source.resolve():
        raise SearchError("O índice deve ficar separado do banco importado.")
    started = time.monotonic()
    with readonly(settings.source) as source:
        signature = source_signature(source)
        rows = source.execute("SELECT * FROM active_records WHERE searchable=1 AND kind='conhecimento' ORDER BY package_id,id").fetchall()
    model_key = embedder.key if embedder else None
    cache = {}
    with closing(open_index(settings.index)) as previous:
        old_meta = metadata(previous)
        if model_key and old_meta.get("model") == model_key:
            cache = {r[0]: r[1] for r in previous.execute("SELECT embedding_hash,vector FROM chunks WHERE vector IS NOT NULL")}
    report = {"eligible_records": len(rows), "documents": 0, "chunks": 0, "excluded_projection": 0,
              "embedded": 0, "reused": 0, "source_signature": signature, "projection": PROJECTION_VERSION,
              "model": model_key, "dimension": embedder.dimension if embedder else 0,
              "mode": "hybrid" if embedder else "textual", "access": "authenticated_shared"}
    settings.index.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="search-build-", dir=settings.index.parent) as folder:
        stage_path = Path(folder) / "stage.sqlite3"
        with closing(open_index(stage_path)) as stage:
            pending = []

            def flush():
                if not pending:
                    return
                vectors = embedder.encode([text for _, _, text in pending])
                if len(vectors) != len(pending):
                    raise SearchError("Quantidade de embeddings incompatível com os trechos.")
                for (row_id, content_hash, _), vector in zip(pending, vectors):
                    import numpy as np
                    vector = np.asarray(vector, dtype="<f4")
                    if vector.shape != (embedder.dimension,) or not np.isfinite(vector).all() or abs(float(np.linalg.norm(vector)) - 1) > .01:
                        raise SearchError("Embedding sem dimensão ou normalização válida.")
                    raw = vector.tobytes()
                    stage.execute("UPDATE chunks SET vector=? WHERE id=?", (raw, row_id))
                    cache[content_hash] = raw
                report["embedded"] += len(pending)
                pending.clear()
                stage.commit()

            for row in rows:
                doc = project(row)
                if doc is None:
                    report["excluded_projection"] += 1
                    continue
                stage.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?)", tuple(doc[k] for k in ("key", "package_id", "source_id", "fingerprint", "title", "body")) + (json_text(doc["metadata"]), json_text(doc["origin"])))
                report["documents"] += 1
                for chunk in chunks(doc, embedder):
                    raw = cache.get(chunk["embedding_hash"]) if embedder else None
                    if raw is not None and len(raw) != embedder.dimension * 4:
                        raise SearchError("Vetor armazenado com tamanho inválido; reconstrua em um índice novo.")
                    cursor = stage.execute("INSERT INTO chunks(key,document_key,position,start,end,title,text,embedding_hash,vector) VALUES (?,?,?,?,?,?,?,?,?)",
                                           tuple(chunk[k] for k in ("key", "document_key", "position", "start", "end", "title", "text", "embedding_hash")) + (raw,))
                    row_id = cursor.lastrowid
                    stage.execute("INSERT INTO search_fts(rowid,title,body) VALUES (?,?,?)",
                                  (row_id, " ".join(keywords(doc["title"])), " ".join(keywords(chunk["text"], limit=10000))))
                    report["chunks"] += 1
                    if raw is not None:
                        report["reused"] += 1
                    elif embedder:
                        pending.append((row_id, chunk["embedding_hash"], chunk["embedding_text"]))
                        if len(pending) >= 16:
                            flush()
                if report["documents"] % 250 == 0:
                    progress(f"Preparados {report['documents']}/{len(rows)} documentos; {report['chunks']} trechos.")
            flush()
            stage.commit()
            report.update(seconds=round(time.monotonic() - started, 2), created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        # A publicação inteira é transacional; leitores continuam na versão anterior.
        # Reconfere a origem sob transação de leitura para não publicar um snapshot vencido.
        with readonly(settings.source) as source, closing(open_index(settings.index)) as target:
            if source_signature(source) != signature:
                raise SearchError("O acervo mudou durante a indexação. Execute novamente.")
            target.execute("ATTACH DATABASE ? AS incoming", (str(stage_path),))
            try:
                target.execute("BEGIN IMMEDIATE")
                for table in ("search_fts", "chunks", "documents", "meta"):
                    target.execute(f"DELETE FROM {table}")
                target.execute("INSERT INTO documents SELECT * FROM incoming.documents")
                target.execute("INSERT INTO chunks SELECT * FROM incoming.chunks")
                target.execute("INSERT INTO search_fts(rowid,title,body) SELECT rowid,title,body FROM incoming.search_fts")
                for key, value in report.items():
                    target.execute("INSERT INTO meta VALUES (?,?)", (key, json_text(value)))
                target.commit()
            except BaseException:
                target.rollback()
                raise
    return report
