"""FastAPI-сервис RAG: индексация кодовой базы, поиск, ответ с контекстом.

Эндпоинты:
    GET  /health   — состояние сервиса (построен ли индекс, каким эмбеддером)
    POST /index    — (пере)построить индекс по директории
    POST /search   — top-k релевантных чанков
    POST /ask      — retrieval + сборка промпта под бюджет + вызов LLM

Запуск:  uvicorn api:app --reload  (из каталога lab_2_4_rag)
Демо без сервера: python rag_demo.py --query "..."
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

_CODE_ROOT = Path(__file__).resolve().parents[1]
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))  # запуск из каталога лаборатории: import shared

from chunker import chunk_tree
from context import pack_context
from embedders import EmbedderError, make_embedder
from index import VectorIndex

from shared.llm import approx_tokens, make_llm

# Корень индексации по умолчанию — весь курс (каталог выше code/)
DEFAULT_ROOT = Path(__file__).resolve().parents[2]

app = FastAPI(
    title="RAG service (lab 2.4)",
    description="Индексация кодовой базы + векторный поиск + сборка контекста",
    version="1.0",
)

# Состояние сервиса (для курса — достаточно глобального атрибута;
# в проде — внешнее хранилище, чтобы пережить рестарт/масштабирование)
_INDEX: VectorIndex | None = None
_STATS: dict = {"root": None, "files_indexed": 0}


class IndexRequest(BaseModel):
    path: str | None = Field(default=None, description="директория для индексации; null = корень курса")
    embedder: Literal["auto", "tfidf", "minilm"] = "auto"
    max_chars: int = Field(default=1200, ge=200, le=8000, description="максимум символов на чанк")


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    k: int = Field(default=5, ge=1, le=20)


class AskRequest(BaseModel):
    question: str = Field(min_length=2)
    k: int = Field(default=5, ge=1, le=20)
    budget_tokens: int = Field(default=2000, ge=200, le=32000)


def _require_index() -> VectorIndex:
    if _INDEX is None or not _INDEX.is_built:
        raise HTTPException(status_code=409, detail="индекс не построен: сначала POST /index")
    return _INDEX


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "indexed": _INDEX is not None and _INDEX.is_built,
        "chunks": _INDEX.size if _INDEX else 0,
        "embedder": _INDEX.embedder.name if _INDEX and _INDEX.embedder else None,
        "root": _STATS["root"],
    }


@app.post("/index")
def build_index(req: IndexRequest) -> dict:
    """Индексация: чанкинг -> fit/encode -> матрица векторов."""
    global _INDEX, _STATS
    root = Path(req.path).resolve() if req.path else DEFAULT_ROOT
    if not root.is_dir():
        raise HTTPException(status_code=400, detail=f"директория не найдена: {root}")

    started = time.perf_counter()
    try:
        embedder = make_embedder(req.embedder)
    except EmbedderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    chunks = chunk_tree(root, max_chars=req.max_chars)
    index = VectorIndex(embedder)
    stats = index.build(chunks, embedder)

    _INDEX = index
    _STATS = {"root": str(root), "files_indexed": len({c.path for c in chunks})}
    return {
        "root": str(root),
        "files": _STATS["files_indexed"],
        "chunks": stats["chunks"],
        "embedder": embedder.name,
        "dim": stats["dim"],
        "took_ms": round((time.perf_counter() - started) * 1000, 1),
    }


@app.post("/search")
def search(req: SearchRequest) -> dict:
    index = _require_index()
    started = time.perf_counter()
    hits = index.search(req.query, k=req.k)
    return {
        "query": req.query,
        "took_ms": round((time.perf_counter() - started) * 1000, 1),
        "hits": [
            {
                "path": h.chunk.path,
                "start_line": h.chunk.start_line,
                "end_line": h.chunk.end_line,
                "score": round(h.score, 4),
                "preview": h.chunk.text[:300],
            }
            for h in hits
        ],
    }


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    """RAG end-to-end: найти -> уложить в бюджет -> передать контекст модели."""
    index = _require_index()
    hits = index.search(req.question, k=req.k)
    if not hits:
        raise HTTPException(status_code=404, detail="по запросу ничего не найдено")

    prompt, used = pack_context(req.question, hits, budget_tokens=req.budget_tokens)
    answer = make_llm().chat(
        [
            {"role": "system", "content": "Ты отвечаешь строго по предоставленному контексту."},
            {"role": "user", "content": prompt},
        ]
    )
    return {
        "answer": answer,
        "context_files": [h.chunk.location for h in used],
        "context_tokens_approx": approx_tokens(prompt),
        "budget_tokens": req.budget_tokens,
    }
