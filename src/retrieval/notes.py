import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Protocol

import numpy as np
from pydantic import Field

from src.errors import ModelError
from src.models import StrictModel
from src.observability.telemetry import Metrics, event


class Note(StrictModel):
    note_id: str
    customer_id: int = Field(gt=0)
    kind: str
    recorded_at: date
    text: str = Field(min_length=1, max_length=20000)
    synthetic: bool


class Evidence(StrictModel):
    source_id: str
    customer_id: int
    text: str
    similarity: float = Field(ge=-1, le=1)


class Embedder(Protocol):
    identity: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


class DemoEmbedder:
    """Stable hashed bag-of-words: offline test/demonstration ONLY, not semantic AI."""

    identity = "demo-hash-bow-v1-512"

    def embed(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), 512), dtype=float)
        for i, text in enumerate(texts):
            for word in re.findall(r"[a-z]+", text.lower()):
                bucket = int(hashlib.sha256(word.encode()).hexdigest()[:8], 16) % 512
                matrix[i, bucket] += 1
        return matrix


class OpenAIEmbedder:
    def __init__(self, client, model: str):
        self.client = client
        self.model = model
        self.identity = f"openai:{model}"

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = []
        try:
            for offset in range(0, len(texts), 64):
                result = self.client.embeddings.create(
                    model=self.model, input=texts[offset : offset + 64]
                )
                vectors.extend(
                    item.embedding for item in sorted(result.data, key=lambda x: x.index)
                )
        except Exception as exc:
            raise ModelError("Embedding provider unavailable") from exc
        array = np.asarray(vectors, dtype=float)
        if array.ndim != 2 or len(array) != len(texts) or not np.isfinite(array).all():
            raise ModelError("Invalid embedding response")
        return array


def chunk_text(text: str, size: int = 120, overlap: int = 20) -> list[str]:
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("Invalid chunk size/overlap")
    words = text.split()
    chunks = []
    for start in range(0, len(words), size - overlap):
        chunks.append(" ".join(words[start : start + size]))
        if start + size >= len(words):
            break
    return chunks


def cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    if matrix.ndim != 2 or query.ndim != 1 or matrix.shape[1] != query.shape[0]:
        raise ValueError("Embedding dimension mismatch")
    if not np.isfinite(query).all() or not np.isfinite(matrix).all():
        raise ValueError("Non-finite embeddings")
    denom = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query)
    return np.clip(
        np.divide(matrix @ query, denom, out=np.zeros(len(matrix)), where=denom > 0), -1, 1
    )


class NotesIndex:
    def __init__(
        self, directory: Path, embedder: Embedder, metrics: Metrics, cache_dir: Path | None = None
    ):
        self.embedder = embedder
        self.metrics = metrics
        self.chunks: list[dict] = []
        seen = set()
        for path in sorted(directory.glob("*.json")):
            for raw in json.loads(path.read_text(encoding="utf-8")):
                note = Note.model_validate(raw)
                if not note.synthetic or note.note_id in seen:
                    raise ValueError("Notes must be synthetic with unique identifiers")
                seen.add(note.note_id)
                for i, text in enumerate(chunk_text(note.text)):
                    self.chunks.append(
                        {
                            "source_id": f"{note.note_id}#{i}",
                            "customer_id": note.customer_id,
                            "text": text,
                        }
                    )
        if not self.chunks:
            raise ValueError("No customer notes available")
        fingerprint = hashlib.sha256(
            json.dumps([embedder.identity, self.chunks], sort_keys=True).encode()
        ).hexdigest()
        cache = cache_dir / f"{fingerprint}.npy" if cache_dir else None
        if cache and cache.exists():
            self.matrix = np.load(cache, allow_pickle=False)
        else:
            self.matrix = embedder.embed([c["text"] for c in self.chunks])
            if cache:
                cache.parent.mkdir(parents=True, exist_ok=True)
                # A rename keeps readers from observing partially written cache files.
                import tempfile

                with tempfile.NamedTemporaryFile(
                    dir=cache.parent, suffix=".npy", delete=False
                ) as handle:
                    np.save(handle, self.matrix, allow_pickle=False)
                    temp = Path(handle.name)
                temp.replace(cache)
        if (
            self.matrix.ndim != 2
            or len(self.matrix) != len(self.chunks)
            or not np.isfinite(self.matrix).all()
        ):
            raise ValueError("Invalid retrieval cache")

    def search(self, query: str, customer_id: int | None = None, top_k: int = 3) -> list[Evidence]:
        if not query.strip() or len(query) > 2000 or not 1 <= top_k <= 10:
            raise ValueError("Invalid retrieval query")
        self.metrics.increment("rag_queries_total")
        candidates = [
            i
            for i, chunk in enumerate(self.chunks)
            if customer_id is None or chunk["customer_id"] == customer_id
        ]
        if not candidates:
            return []
        query_vector = self.embedder.embed([query])[0]
        scores = cosine_similarity(query_vector, self.matrix[candidates])
        order = sorted(
            range(len(candidates)),
            key=lambda j: (-scores[j], self.chunks[candidates[j]]["source_id"]),
        )[:top_k]
        results = [
            Evidence(**self.chunks[candidates[j]], similarity=float(scores[j]))
            for j in order
            if scores[j] > 0
        ]
        event("rag_retrieval", customer_id=customer_id, count=len(results))
        return results
