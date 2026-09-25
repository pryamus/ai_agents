"""Плоский векторный индекс: косинусный top-k поиск на numpy.

Для кодовой базы в тысячи чанков «перебор» (flat index) быстрее точных
ANN-структур: матрица 5k x 384 считается за микросекунды. HNSW/FAISS нужны,
когда чанков миллионы — в рамках курса упоминаем, но не используем.

Хранение на диске: vectors.npy + chunks.json + meta.json — индекс
переиспользуется между запусками сервиса (warm start).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from chunker import Chunk
from embedders import Embedder


@dataclass(frozen=True)
class SearchHit:
    chunk: Chunk
    score: float   # косинусное сходство [-1..1], у нормированных векторов [0..1]


class VectorIndex:
    """Матрица векторов + чанки-пейлоады + embedder для запросов."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self.embedder = embedder
        self.chunks: list[Chunk] = []
        self.vectors: np.ndarray | None = None  # (n_chunks, dim) float32

    @property
    def is_built(self) -> bool:
        return self.vectors is not None and len(self.chunks) > 0

    @property
    def size(self) -> int:
        return len(self.chunks)

    def build(self, chunks: list[Chunk], embedder: Embedder) -> dict:
        """Заиндексировать чанки: fit (если нужно) -> encode -> (n, dim)."""
        started = time.perf_counter()
        self.embedder = embedder
        self.chunks = list(chunks)
        if not chunks:
            self.vectors = None
            return {"chunks": 0, "dim": 0, "took_ms": 0.0}
        texts = [c.text for c in chunks]
        embedder.fit(texts)                       # TF-IDF: учить словарь; BERT: no-op
        self.vectors = embedder.encode(texts)
        took_ms = (time.perf_counter() - started) * 1000
        return {
            "chunks": len(chunks),
            "dim": int(self.vectors.shape[1]),
            "took_ms": round(took_ms, 1),
            "embedder": embedder.name,
        }

    def search(self, query: str, k: int = 5) -> list[SearchHit]:
        """Top-k чанков по косинусу. Один encode запроса + одно умножение матриц."""
        if not self.is_built or self.embedder is None:
            raise RuntimeError("индекс не построен — сначала POST /index")
        q = self.embedder.encode([query])[0]                     # (dim,)
        scores = self.vectors @ q                                # (n,)
        k = min(k, len(self.chunks))
        order = np.argsort(-scores)[:k]
        return [SearchHit(chunk=self.chunks[int(i)], score=float(scores[int(i)])) for i in order]

    # -- persistence --------------------------------------------------------
    def save(self, directory: Path) -> None:
        if not self.is_built or self.embedder is None:
            raise RuntimeError("нечего сохранять: индекс не построен")
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "vectors.npy", self.vectors)
        (directory / "chunks.json").write_text(
            json.dumps([asdict(c) for c in self.chunks], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        (directory / "meta.json").write_text(
            json.dumps(
                {"embedder": self.embedder.name, "dim": self.embedder.dim, "count": len(self.chunks)},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.embedder.save_state(directory)

    @classmethod
    def load(cls, directory: Path, embedder: Embedder) -> VectorIndex:
        """Восстановить индекс. embedder обязан совпадать по типу с сохранённым!"""
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
        if meta["embedder"] != embedder.name:
            raise RuntimeError(
                f"индекс построен эмбеддером {meta['embedder']!r}, а запросы пойдут "
                f"через {embedder.name!r} — векторы несопоставимы"
            )
        index = cls(embedder)
        index.vectors = np.load(directory / "vectors.npy")
        raw = json.loads((directory / "chunks.json").read_text(encoding="utf-8"))
        index.chunks = [Chunk(**c) for c in raw]
        embedder.load_state(directory)  # TF-IDF: вернуть обученный векторайзер
        return index
