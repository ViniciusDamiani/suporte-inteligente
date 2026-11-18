import json
import logging
import math
import threading
import time

from api.text_utils import keywords
from .config import SearchError
from .documents import valid_query
from .embeddings import get_embedder
from .storage import check_current, readonly


def fuse(text_ids, vector_ids, k=60):
    """RRF combina posições, não mistura escalas BM25/cosseno."""
    scores = {}
    for ranked in (text_ids, vector_ids):
        for rank, key in enumerate(dict.fromkeys(ranked), 1):
            scores[key] = scores.get(key, 0.0) + 1 / (k + rank)
    return sorted(scores, key=lambda key: (-scores[key], key))


class SearchService:
    def __init__(self, settings, embedder_factory=get_embedder):
        self.settings = settings
        self.embedder_factory = embedder_factory
        self._cache_key = None
        self._vectors = None
        self._ids = None
        self._lock = threading.Lock()

    def status(self):
        with readonly(self.settings.source) as source, readonly(self.settings.index) as index:
            info = check_current(source, index)
            return {k: info[k] for k in ("documents", "chunks", "mode", "created_at", "access")}

    def _vector_search(self, index, info, query, count):
        import numpy as np
        embedder = self.embedder_factory(self.settings)
        if embedder.key != info["model"] or embedder.dimension != info["dimension"]:
            raise SearchError("Modelo local diferente do modelo do índice. Refaça a indexação.")
        query_vector = np.asarray(embedder.encode([query], query=True)[0], dtype="<f4")
        if query_vector.shape != (info["dimension"],) or not np.isfinite(query_vector).all():
            raise SearchError("Vetor da consulta inválido.")
        cache_key = (info["source_signature"], info["model"], info["created_at"], info["chunks"])
        with self._lock:
            if cache_key != self._cache_key:
                rows = index.execute("SELECT id,vector FROM chunks ORDER BY id").fetchall()
                if any(r[1] is None or len(r[1]) != info["dimension"] * 4 for r in rows):
                    raise SearchError("Índice vetorial incompleto. Refaça a indexação.")
                vectors = np.stack([np.frombuffer(r[1], dtype="<f4") for r in rows]) if rows else np.empty((0, info["dimension"]), dtype="<f4")
                if not np.isfinite(vectors).all():
                    raise SearchError("Índice contém vetores inválidos.")
                self._vectors, self._ids = vectors, [r[0] for r in rows]
                self._cache_key = cache_key
            vectors, ids = self._vectors, self._ids
        similarities = vectors @ query_vector
        ranked = np.argsort(-similarities, kind="stable")
        return [(ids[int(i)], float(similarities[i])) for i in ranked[:count] if similarities[i] >= self.settings.min_similarity]

    def search(self, query, limit=8):
        query = valid_query(query)
        if type(limit) is not int or not 1 <= limit <= 20:
            raise SearchError("Limite de resultados deve ficar entre 1 e 20.", 400)
        if not math.isfinite(self.settings.min_similarity) or not 0 <= self.settings.min_similarity <= 1:
            raise SearchError("Limite de similaridade configurado fora do intervalo permitido.")
        terms = keywords(query, limit=30)
        if not terms:
            raise SearchError("Descreva o problema com mais detalhes.", 400)
        started = time.monotonic()
        with readonly(self.settings.source) as source, readonly(self.settings.index) as index:
            info = check_current(source, index)
            expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
            textual = [r[0] for r in index.execute("SELECT rowid FROM search_fts WHERE search_fts MATCH ? ORDER BY bm25(search_fts,2.0,1.0),rowid LIMIT 80", (expression,))]
            vectors, warnings = [], []
            if info["mode"] == "hybrid":
                try:
                    vectors = self._vector_search(index, info, query, 80)
                except (SearchError, ImportError, OSError, RuntimeError) as exc:
                    logging.getLogger(__name__).warning("Busca vetorial indisponível: %s", type(exc).__name__)
                    warnings.append("A pesquisa por significado está indisponível nesta consulta. Foram usados somente os termos informados.")
                    # Falha operacional não expõe caminhos ou detalhes internos ao navegador.
            else:
                warnings.append("A pesquisa por significado ainda não foi preparada. Foram usados somente os termos informados.")
            vector_ids = [r[0] for r in vectors]
            vector_scores = dict(vectors)
            ranked = fuse(textual, vector_ids)
            documents, results = set(), []
            for identifier in ranked:
                row = index.execute("""SELECT c.*,d.package_id,d.source_id,d.metadata,d.origin,d.fingerprint
                    FROM chunks c JOIN documents d ON d.key=c.document_key WHERE c.id=?""", (identifier,)).fetchone()
                if row["document_key"] in documents:
                    continue
                documents.add(row["document_key"])
                via = (["textual"] if identifier in textual else []) + (["vector"] if identifier in vector_scores else [])
                original = source.execute(
                    "SELECT payload FROM active_records WHERE package_id=? AND id=? AND fingerprint=?",
                    (row["package_id"], row["source_id"], row["fingerprint"]),
                ).fetchone()
                data = json.loads(original["payload"]).get("dados", {}) if original else {}
                # Classifica pelo registro completo, pois o trecho recuperado pode conter só o problema.
                has_solution = any(isinstance(data.get(field), str) and data[field].strip()
                                   for field in ("solucao_documentada", "solucao_candidata"))
                ticket = data.get("ticket")
                ticket_reference = str(ticket).strip() if isinstance(ticket, (str, int)) and not isinstance(ticket, bool) else ""
                results.append({"document_key": row["document_key"], "chunk_key": row["key"], "source_id": row["source_id"],
                                "package_id": row["package_id"], "title": row["title"], "excerpt": row["text"],
                                "position": row["position"], "start": row["start"], "end": row["end"],
                                "metadata": json.loads(row["metadata"]), "origin": json.loads(row["origin"]),
                                "matched_by": via, "has_solution": bool(has_solution), "ticket_reference": ticket_reference})
                if len(results) == limit:
                    break
        return {"query": query, "mode": "hybrid" if info["mode"] == "hybrid" and not warnings else "textual",
                "results": results, "warnings": warnings, "generated_answer": None, "generation_status": "pending",
                "source_count": info["documents"], "seconds": round(time.monotonic() - started, 3)}

    def document(self, key):
        if not isinstance(key, str) or len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise SearchError("Referência inválida.", 400)
        with readonly(self.settings.source) as source, readonly(self.settings.index) as index:
            check_current(source, index)
            row = index.execute("SELECT * FROM documents WHERE key=?", (key,)).fetchone()
            if row is None:
                raise SearchError("Fonte não encontrada no acervo ativo.", 404)
            return {k: json.loads(row[k]) if k in ("metadata", "origin") else row[k]
                    for k in ("key", "source_id", "package_id", "title", "body", "metadata", "origin")}

    def evidence(self, result):
        """Fichas sob demanda a partir da projeção autorizada, sem reindexar o acervo."""
        from .dialogue_context import GENERIC, technical_terms, symptom_text, projected_sections
        candidates = []
        query_terms = set(keywords(result.get("query", "")))
        query_terms = {term for term in query_terms if term not in GENERIC or term == "unit"}
        topics = set(result.get("topic_terms", []))
        requests = set(keywords("proposta orçamento inclusão incluir adicionar melhoria instalação implementação engenharia"))
        wants_request = bool(query_terms & requests)
        for rank, item in enumerate(result["results"][:20]):
            doc = self.document(item["document_key"])
            sections = projected_sections(doc["body"])
            symptom = symptom_text(sections.get("Problema relatado", ""))
            signature = technical_terms(item.get("title", "") + " " + symptom) - query_terms
            concrete = bool(technical_terms(symptom) - query_terms)
            relevant = set(keywords(item.get("title", "") + " " + symptom, limit=1000))
            if topics and not topics.intersection(relevant):
                continue
            title_terms = set(keywords(item.get("title", "")))
            if not wants_request and title_terms.intersection(keywords("proposta orçamento")):
                continue
            if query_terms and not query_terms.intersection(relevant):
                continue
            coverage = len(query_terms & relevant) / max(1, len(query_terms))
            has_action = any(sections.get(label, "").strip() for label in ("Solução documentada", "Solução candidata"))
            score = coverage * 10 + concrete * 2 + has_action * .5 + 1 / (rank + 1)
            # Reservas por campo: uma descrição longa não pode expulsar ação/resultado.
            quotas = {"Área técnica": 80, "Problema normalizado": 140,
                      "Problema relatado": 200, "Diagnóstico documentado": 180,
                      "Solução documentada": 360, "Solução candidata": 200,
                      "Resultado documentado": 180, "Pendências": 140,
                      "Versão da ocorrência histórica": 80, "Versão corrigida informada": 80,
                      "Aplicabilidade": 180}
            parts = []
            for label, value in sections.items():
                size = quotas[label]
                parts.append(label + ": " + value[:size] + (" [trecho reduzido]" if len(value) > size else ""))
            candidates.append((score, signature, {**item, "excerpt": "\n\n".join(parts)}))
        # Diversidade local: evita gastar os três lugares com a mesma descrição.
        selected, signatures = [], []
        while candidates and len(selected) < 3:
            def adjusted(candidate):
                score, signature, _ = candidate
                similarity = max((len(signature & previous) / max(1, len(signature | previous))
                                  for previous in signatures), default=0)
                return score - 2 * similarity
            best = max(range(len(candidates)), key=lambda i: adjusted(candidates[i]))
            _, signature, item = candidates.pop(best)
            selected.append(item)
            signatures.append(signature)
        return {**result, "results": selected}
