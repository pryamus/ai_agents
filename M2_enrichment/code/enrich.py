"""Обогащение вопроса: глоссарий + внешний корпус -> контекст для агента (2.7).

Порядок важен: сначала глоссарий (дешёвый, детерминированный), потом
векторный поиск по кэшу документов (дороже), затем упаковка всего
в бюджет контекстного окна пайплайном из 2.4.

Запуск:  python enrich.py --question "как откатить деплой"
          python enrich.py --question "..." --embedder minilm --ask
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))
_CODE_ROOT = LAB.parent.parent
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))  # import shared / lab_2_4_rag
_LAB_2_4 = _CODE_ROOT / "M2_rag" / "code"
if str(_LAB_2_4) not in sys.path:
    # модули 2.4 импортируют соседей как top-level (from index import ...):
    # для кросс-лабораторного импорта нужен их каталог в пути
    sys.path.insert(0, str(_LAB_2_4))

from docs_cache import DocCache
from glossary import Glossary

from M2_rag.code.chunker import chunk_text
from M2_rag.code.context import pack_context
from M2_rag.code.embedders import make_embedder
from M2_rag.code.index import VectorIndex
from M2_rag.code.shared.llm import approx_tokens, make_llm

DEFAULT_CORPUS = LAB / "corpus"
DEFAULT_GLOSSARY = LAB / "data" / "glossary.json"


@dataclass
class EnrichedContext:
    block: str                 # готовый блок контекста для промпта
    files: list[str]           # источники из корпуса (атрибуция)
    terms: list[str]           # термины глоссария, сработавшие в вопросе
    stale_sources: list[str] = field(default_factory=list)  # просроченный кэш


def build_docs_index(cache: DocCache, *, embedder: str = "minilm") -> VectorIndex:
    """Проиндексировать содержимое кэша чанкингом и эмбеддером из 2.4."""
    emb = make_embedder(embedder)
    chunks = []
    for record in cache.list_docs():
        if record.path == "manifest.json":
            continue
        chunks += chunk_text(cache.doc_path(record), cache.root)
    index = VectorIndex(emb)
    index.build(chunks, emb)
    return index


def enrich(
    question: str,
    cache: DocCache,
    glossary: Glossary,
    *,
    index: VectorIndex,
    k: int = 4,
    budget_tokens: int = 1500,
) -> EnrichedContext:
    """Собрать обогащённый контекст: определения + релевантные документы."""
    found_terms = glossary.lookup(question)
    glossary_block = glossary.expand(question)
    reserve = approx_tokens(glossary_block) + 200  # место под глоссарий и вопрос
    hits = index.search(question, k=k)
    prompt, used = pack_context(
        question, hits, budget_tokens=max(200, budget_tokens - reserve)
    )
    block = (glossary_block + "\n\n" + prompt).strip() if glossary_block else prompt
    # Чанки ссылаются на файлы кэша (sha-имена) — отдаём наружу source-имена
    sources = {rec.path: rec.source for rec in cache.list_docs()}
    return EnrichedContext(
        block=block,
        files=[sources.get(h.chunk.path, h.chunk.path) for h in used],
        terms=[t.term for t in found_terms],
        stale_sources=cache.stale_sources(),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Обогащение вопроса внешним корпусом (2.7)")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--cache", type=Path, default=LAB / ".cache_docs")
    parser.add_argument("--glossary", type=Path, default=DEFAULT_GLOSSARY)
    parser.add_argument("--question", default="как откатить неудачный деплой")
    parser.add_argument("--embedder", choices=["auto", "tfidf", "minilm"], default="auto")
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument("--budget", type=int, default=1500)
    parser.add_argument("--ask", action="store_true", help="передать контекст в LLM")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cache = DocCache(args.cache)
    for doc in sorted(args.corpus.glob("*.md")):
        cache.add_file(doc, source=doc.name)  # документация проекта -> кэш
    glossary = Glossary.from_json(args.glossary)
    index = build_docs_index(cache, embedder=args.embedder)

    ctx = enrich(args.question, cache, glossary, index=index, k=args.k,
                 budget_tokens=args.budget)
    print(f"[terms] сработали: {ctx.terms or '—'}")
    print(f"[files] источники: {ctx.files or '—'}")
    if ctx.stale_sources:
        print(f"[warn] просрочен кэш (нужен refresh): {ctx.stale_sources}")
    print(f"[budget] ~{approx_tokens(ctx.block)} токенов при бюджете {args.budget}")
    print("\n----- обогащённый контекст -----")
    print(ctx.block)
    print("-------------------------------")
    if args.ask:
        answer = make_llm().chat(
            [
                {"role": "system", "content": "Отвечай строго по контексту."},
                {"role": "user", "content": f"{ctx.block}\n\nВопрос: {args.question}"},
            ]
        )
        print("\n[answer]", answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
