"""Тесты обогащения (тема 2.7): кэш, глоссарий, enrich end-to-end.

Запуск: python -m pytest lab_2_7_enrichment -q  (из каталога code/)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
_CODE_ROOT = LAB.parent
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))

from docs_cache import CacheError, DocCache
from enrich import build_docs_index, enrich, main
from glossary import Glossary

GLOSSARY = LAB / "data" / "glossary.json"
CORPUS = LAB / "corpus"


def test_cache_add_file_and_dedup(tmp_path: Path):
    cache = DocCache(tmp_path / "cache")
    src = tmp_path / "doc.md"
    src.write_text("# Заголовок\n\nТекст.", encoding="utf-8")

    first = cache.add_file(src, source="doc")
    second = cache.add_file(src, source="doc")
    assert first.sha == second.sha
    assert len(list((tmp_path / "cache").glob("*.md"))) == 1  # копия одна
    assert len(cache.list_docs()) == 1


def test_cache_refresh_detects_change(tmp_path: Path):
    cache = DocCache(tmp_path / "cache")
    src = tmp_path / "doc.md"
    src.write_text("версия 1", encoding="utf-8")
    old = cache.add_file(src, source="doc")

    assert cache.refresh_file(tmp_path / "missing.md", source="unknown") is None
    src.write_text("версия 2", encoding="utf-8")
    new = cache.refresh_file(src, source="doc")
    assert new is not None and new.sha != old.sha


def test_cache_url_requires_fetcher_and_supports_ttl(tmp_path: Path):
    cache = DocCache(tmp_path / "cache", ttl_seconds=-1)  # TTL уже истёк
    with pytest.raises(CacheError, match="офлайн"):
        cache.add_url("https://example.com/docs")

    record = cache.add_url("https://example.com/docs",
                           fetcher=lambda url: f"# Копия {url}")
    assert record.kind == "url" and record.stale
    assert cache.stale_sources() == ["https://example.com/docs"]


def test_glossary_lookup_by_alias_case_insensitive():
    glossary = Glossary.from_json(GLOSSARY)
    found = glossary.lookup("Как делать ЧАНКИ для rollback?")
    assert {t.term for t in found} == {"чанк", "откат"}
    assert glossary.lookup("про погоду") == []
    assert "384" in (glossary.define("embedding") or "")
    assert glossary.define("неизвестно") is None


def test_glossary_expand_block():
    glossary = Glossary.from_json(GLOSSARY)
    block = glossary.expand("что такое таймаут и ретрай")
    assert "таймаут" in block and "ретрай" in block
    assert glossary.expand("про погоду") == ""


def _index(tmp_path: Path):
    cache = DocCache(tmp_path / "cache")
    for doc in sorted(CORPUS.glob("*.md")):
        cache.add_file(doc, source=doc.name)
    return cache, build_docs_index(cache, embedder="tfidf")


def test_enrich_combines_glossary_and_docs(tmp_path: Path):
    cache, index = _index(tmp_path)
    ctx = enrich("как откатить неудачный деплой", cache,
                 Glossary.from_json(GLOSSARY), index=index)
    assert "откат" in ctx.terms and "деплой" in ctx.terms
    assert any("deploy" in f for f in ctx.files)  # атрибуция источника
    assert "rollback" in ctx.block or "откат" in ctx.block


def test_enrich_respects_budget(tmp_path: Path):
    from shared.llm import approx_tokens

    cache, index = _index(tmp_path)
    ctx = enrich("таймаут деплой откат чанк эмбеддинг", cache,
                 Glossary.from_json(GLOSSARY), index=index, budget_tokens=400)
    assert approx_tokens(ctx.block) <= 400 + 400  # бюджет + служебные допуски


def test_enrich_without_terms_still_searches(tmp_path: Path):
    cache, index = _index(tmp_path)
    ctx = enrich("коды ошибок эндпоинтов", cache,
                 Glossary.from_json(GLOSSARY), index=index, k=2)
    assert ctx.terms == []  # терминов глоссария в вопросе нет
    assert len(ctx.files) <= 2


def test_demo_main_returns_zero(tmp_path: Path):
    assert main(["--cache", str(tmp_path / "c"),
                 "--question", "как откатить деплой"]) == 0
