import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    source: Path
    index: Path
    model_dir: Path
    threads: int = 2
    min_similarity: float = 0.85

    @classmethod
    def from_env(cls):
        return cls(Path(os.getenv("KNOWLEDGE_DATABASE", ROOT / "instance/knowledge.sqlite3")),
                   Path(os.getenv("KNOWLEDGE_SEARCH_DATABASE", ROOT / "instance/search.sqlite3")),
                   Path(os.getenv("KNOWLEDGE_MODEL_DIR", ROOT / "instance/models/multilingual-e5-small")),
                   int(os.getenv("KNOWLEDGE_EMBEDDING_THREADS", "2")),
                   float(os.getenv("KNOWLEDGE_MIN_SIMILARITY", "0.85")))


class SearchError(ValueError):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status
