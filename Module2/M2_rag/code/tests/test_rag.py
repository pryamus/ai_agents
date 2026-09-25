"""Тесты лабораторной 2.4: чанкинг, индекс, FastAPI-контракты.

Запуск: python -m pytest lab_2_4_rag -q  (из каталога code/)
В тестах принудительно используется TF-IDF: детерминированно, офлайн,
без скачивания моделей. MiniLM проверяется вручную (см. README).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

LAB = Path(__file__).resolve().parents[1]
CODE = LAB.parent
sys.path.insert(0, str(LAB))
sys.path.insert(0, str(CODE))

from chunker import Chunk, chunk_text, chunk_tree
from context import pack_context
from embedders import TfidfEmbedder
from index import SearchHit, VectorIndex

# ---------------------------------------------------------------------------
# Чанкинг
# ---------------------------------------------------------------------------

def test_python_chunking_splits_top_level_defs(tmp_path: Path):
    src = tmp_path / "sample.py"
    src.write_text(
        '"""Модуль."""\n'
        "import os\n"
        "\n"
        "def alpha():\n"
        "    return 1\n"
        "\n"
        "def beta():\n"
        "    return 2\n",
        encoding="utf-8",
    )
    chunks = chunk_text(src, tmp_path)
    texts = "\n".join(c.text for c in chunks)
    assert "def alpha" in texts and "def beta" in texts
    # каждый чанк не вылезает за лимит (+запас на последнюю строку)
    assert all(c.approx_tokens < 1000 for c in chunks)
    assert chunks[0].path == "sample.py"
    assert chunks[0].kind == "code"


def test_broken_python_falls_back_to_windows(tmp_path: Path):
    src = tmp_path / "broken.py"
    src.write_text("def oops(:\n" + "# строка\n" * 50, encoding="utf-8")
    chunks = chunk_text(src, tmp_path, max_chars=200, overlap=50)
    assert chunks, "нечего не найдено — оконная нарезка должна работать без парсера"
    assert all(len(c.text) <= 400 for c in chunks)


def test_markdown_chunking_by_headings(tmp_path: Path):
    doc = tmp_path / "readme.md"
    doc.write_text("# A\n" + "a\n" * 3 + "\n# B\n" + "b\n" * 3, encoding="utf-8")
    chunks = chunk_text(doc, tmp_path)
    assert len(chunks) >= 2
    assert chunks[0].kind == "doc"


def test_chunk_tree_skips_service_dirs(tmp_path: Path):
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.py").write_text("def f(): pass", encoding="utf-8")
    (tmp_path / "ok.py").write_text("def f(): pass", encoding="utf-8")
    chunks = chunk_tree(tmp_path)
    assert {c.path for c in chunks} == {"ok.py"}


# ---------------------------------------------------------------------------
# Индекс: TF-IDF + косинусный top-k
# ---------------------------------------------------------------------------

class _OtherEmbedder(TfidfEmbedder):
    """Другой тип эмбеддера — для проверки несовместимости при load()."""

    name = "other"


def test_index_search_ranks_relevant_chunk_first():
    # Важно для TF-IDF: запрос должен содержать токены корпуса ДОСЛОВНО
    # («скидка» не находит «скидки» — у стемминга/эмбеддингов это другие методы).
    chunks = [
        Chunk("a.py:1-3", "a.py", 1, 3,
              "скидки промокод: расчёт величины скидки", "py", "code"),
        Chunk("b.py:1-3", "b.py", 1, 3,
              "платежи обработка платежа и возврата", "py", "code"),
        Chunk("c.md:1-3", "c.md", 1, 3,
              "деплой документация по деплою сервиса", "md", "doc"),
    ]
    embedder = TfidfEmbedder()
    index = VectorIndex(embedder)
    index.build(chunks, embedder)

    hits = index.search("скидки промокод", k=2)
    assert hits[0].chunk.path == "a.py"
    assert 0.0 < hits[0].score <= 1.0
    assert len(hits) == 2


def test_index_save_load_roundtrip(tmp_path: Path):
    embedder = TfidfEmbedder()
    chunks = [Chunk("x.py:1-1", "x.py", 1, 1, "токен для проверки сохранения", "py", "code")]
    index = VectorIndex(embedder)
    index.build(chunks, embedder)
    index.save(tmp_path / "idx")

    restored = VectorIndex.load(tmp_path / "idx", TfidfEmbedder())
    assert restored.size == 1
    assert restored.search("токен сохранения")[0].chunk.path == "x.py"

    # а вот с другим типом эмбеддера — ошибка (векторы несопоставимы)
    with pytest.raises(RuntimeError, match="эмбеддер"):
        VectorIndex.load(tmp_path / "idx", _OtherEmbedder())


def test_unbuilt_index_raises():
    with pytest.raises(RuntimeError, match="не построен"):
        VectorIndex(TfidfEmbedder()).search("запрос")


# ---------------------------------------------------------------------------
# Контекст под бюджет
# ---------------------------------------------------------------------------

def _hit(text: str, score: float) -> SearchHit:
    return SearchHit(Chunk(f"f:{1}-{2}", "f", 1, 2, text, "py", "code"), score)


def test_pack_context_respects_budget():
    hits = [_hit("слово " * 500, 0.9), _hit("второй чанк " * 400, 0.8)]
    prompt, used = pack_context("вопрос?", hits, budget_tokens=500)
    assert 1 <= len(used) <= 2
    assert "вопрос?" in prompt
    # грубая проверка: промпт не раздулся до размера всех чанков целиком
    from shared.llm import approx_tokens

    assert approx_tokens(prompt) < 500 + 300  # бюджет + служебные допуски


def test_pack_context_includes_locations():
    hits = [_hit("содержимое", 0.5)]
    prompt, used = pack_context("q", hits)
    assert "f:1-2" in prompt and used == hits


# ---------------------------------------------------------------------------
# FastAPI-контракты
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path: Path):
    import api
    from fastapi.testclient import TestClient

    # Глобальное состояние приложения shared между тестами — сбрасываем явно,
    # иначе /health увидит индекс, построенный предыдущим тестом.
    api._INDEX = None
    api._STATS = {"root": None, "files_indexed": 0}

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "# Руководство\n\nЗдесь про скидочные промокоды для клиентов.", encoding="utf-8"
    )
    (tmp_path / "pay.py").write_text(
        "def refund(amount: int) -> None:\n    '''оформить возврат платежа'''\n",
        encoding="utf-8",
    )
    with TestClient(api.app) as test_client:
        yield test_client, tmp_path


def test_search_requires_index(client):
    test_client, _ = client
    resp = test_client.post("/search", json={"query": "скидка"})
    assert resp.status_code == 409


def test_index_and_search_flow(client):
    test_client, root = client
    resp = test_client.post("/index", json={"path": str(root), "embedder": "tfidf"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chunks"] >= 2 and body["embedder"] == "tfidf" and body["dim"] > 0

    resp = test_client.post("/search", json={"query": "возврат платежа", "k": 3})
    assert resp.status_code == 200
    hits = resp.json()["hits"]
    assert hits[0]["path"] == "pay.py"
    assert hits[0]["start_line"] >= 1


def test_ask_returns_answer_and_context(client, monkeypatch):
    test_client, root = client
    monkeypatch.delenv("LLM_API_KEY", raising=False)  # офлайн: мок-ответ
    assert test_client.post("/index", json={"path": str(root), "embedder": "tfidf"}).status_code == 200

    resp = test_client.post("/ask", json={"question": "что со скидками и промокодами?"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"]
    assert body["context_files"], "контекст должен быть передан и вернуться"
    assert body["context_tokens_approx"] <= body["budget_tokens"] + 300


def test_health(client):
    test_client, _ = client
    health = test_client.get("/health").json()
    assert health["status"] == "ok" and health["indexed"] is False
