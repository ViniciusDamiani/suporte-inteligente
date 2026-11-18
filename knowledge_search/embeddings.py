"""E5 ONNX em CPU. Rede usada somente pelo comando explícito preparar-modelo."""
import hashlib
import os
import tempfile
import threading
from pathlib import Path

from .config import SearchError

MODEL = "intfloat/multilingual-e5-small"
REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
FILES = {
    "model.onnx": ("onnx/model_qint8_avx512_vnni.onnx", 118346824, "dd476dd0c2514e9b9be83aeb3853fac0763e0bdf4a71645407587d77c48a2d88"),
    "tokenizer.json": ("tokenizer.json", 17082730, "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39"),
}
MODEL_KEY = MODEL + "@" + REVISION + ":qint8:mean:l2:384:v1"
DIMENSION = 384


def verified(path, specification):
    if not path.is_file() or path.stat().st_size != specification[1]:
        return False
    with path.open("rb") as stream:
        hasher = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
        digest = hasher.hexdigest()
    return digest == specification[2]


def prepare_model(folder, progress=print):
    """Baixa pesos públicos fixados por revisão, tamanho e SHA-256; não envia textos."""
    import requests
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, specification in FILES.items():
        target = folder / name
        if verified(target, specification):
            progress(f"Já conferido: {name}")
            continue
        progress(f"Baixando {name} ({specification[1] / 1024**2:.1f} MiB)")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=folder, suffix=".download", delete=False) as stream:
                temporary = Path(stream.name)
                url = f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{specification[0]}"
                with requests.get(url, stream=True, timeout=(15, 90)) as response:
                    response.raise_for_status()
                    total = 0
                    for block in response.iter_content(1024 * 1024):
                        total += len(block)
                        if total > specification[1]:
                            raise SearchError("Download excede o tamanho previsto do modelo.")
                        stream.write(block)
            if not verified(temporary, specification):
                raise SearchError("Download do modelo incompleto ou com integridade inválida.")
            os.replace(temporary, target)
        except requests.RequestException as exc:
            raise SearchError("Não foi possível baixar o modelo. Confira a conexão e execute preparar-modelo novamente.") from exc
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
    return {"model": MODEL, "revision": REVISION, "bytes": sum(v[1] for v in FILES.values()), "verified": True}


class LocalEmbedder:
    key = MODEL_KEY
    dimension = DIMENSION

    def __init__(self, folder, threads=2):
        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise SearchError("Dependências da busca ausentes. Instale requirements.txt.") from exc
        folder = Path(folder)
        if not all(verified(folder / name, spec) for name, spec in FILES.items()):
            raise SearchError("Modelo local ausente ou inválido. Execute python -m knowledge_search preparar-modelo.")
        self.np = np
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.tokenizer.no_truncation()
        self.tokenizer.enable_padding(pad_id=1, pad_token="<pad>")
        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, min(threads, 8))
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        try:
            self.session = ort.InferenceSession(str(folder / "model.onnx"), sess_options=options, providers=["CPUExecutionProvider"])
        except Exception as exc:
            raise SearchError("Não foi possível carregar o modelo local. Confira a instalação e os arquivos do modelo.") from exc
        self.input_names = {i.name for i in self.session.get_inputs()}
        self.lock = threading.Lock()

    def fits(self, text):
        # Não truncamos documentos silenciosamente: o preparador subdivide se necessário.
        with self.lock:
            return len(self.tokenizer.encode("passage: " + text).ids) <= 512

    def encode(self, texts, *, query=False):
        np = self.np
        with self.lock:
            encoded = self.tokenizer.encode_batch([("query: " if query else "passage: ") + t for t in texts])
            if any(len(e.ids) > 512 for e in encoded):
                raise SearchError("Texto excede o limite do modelo local. Reduza a consulta ou reconstrua os trechos.", 400)
            inputs = {"input_ids": np.asarray([e.ids for e in encoded], dtype=np.int64),
                      "attention_mask": np.asarray([e.attention_mask for e in encoded], dtype=np.int64),
                      "token_type_ids": np.asarray([e.type_ids for e in encoded], dtype=np.int64)}
            try:
                output = self.session.run(None, {k: v for k, v in inputs.items() if k in self.input_names})[0]
            except Exception as exc:
                raise SearchError("Não foi possível calcular os embeddings com o modelo local.") from exc
        mask = inputs["attention_mask"][..., None]
        vectors = (output * mask).sum(axis=1) / mask.sum(axis=1)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if vectors.shape != (len(texts), self.dimension) or not np.isfinite(vectors).all() or (norms <= 0).any():
            raise SearchError("O modelo retornou embeddings inválidos.")
        return (vectors / norms).astype("<f4")


_model = None
_model_settings = None
_lock = threading.Lock()


def get_embedder(settings):
    global _model, _model_settings
    key = (str(settings.model_dir.resolve()), settings.threads)
    with _lock:
        if _model is None or key != _model_settings:
            candidate = LocalEmbedder(settings.model_dir, settings.threads)
            _model, _model_settings = candidate, key
        return _model
