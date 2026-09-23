"""CLI-демо RAG без сервера: индексация -> поиск -> сборка промпта (-> ответ).

    python rag_demo.py --query "как агент ограничивает число шагов"
    python rag_demo.py --query "..." --embedder tfidf --k 5 --save index_cache
    python rag_demo.py --query "..." --ask          # + вызов LLM (нужны ключи)

Показывает весь путь данных темы 2.4: файлы -> чанки -> векторы -> top-k ->
бюджет контекста -> промпт для модели.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_CODE_ROOT = Path(__file__).resolve().parents[1]
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))  # запуск из каталога лаборатории: import shared

from chunker import chunk_tree
from context import pack_context
from embedders import make_embedder
from index import VectorIndex

from shared.llm import approx_tokens, make_llm

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUERY = "как ограничить число шагов агента и что будет при превышении лимита"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Демо RAG по кодовой базе курса")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="каталог для индексации")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="поисковый запрос")
    parser.add_argument("--embedder", choices=["auto", "tfidf", "minilm"], default="auto")
    parser.add_argument("--k", type=int, default=5, help="сколько чанков искать")
    parser.add_argument("--budget", type=int, default=2000, help="бюджет токенов на контекст")
    parser.add_argument("--save", type=Path, default=None, help="куда сохранить индекс")
    parser.add_argument("--load", type=Path, default=None, help="загрузить индекс вместо построения")
    parser.add_argument("--ask", action="store_true", help="передать собранный промпт в LLM")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    embedder = make_embedder(args.embedder)

    # 1. Источник -> чанки -> векторы
    if args.load:
        index = VectorIndex.load(args.load, embedder)
        print(f"[load] индекс из {args.load}: {index.size} чанков, embedder={embedder.name}")
    else:
        chunks = chunk_tree(args.root)
        index = VectorIndex(embedder)
        stats = index.build(chunks, embedder)
        files = len({c.path for c in chunks})
        print(
            f"[index] {files} файлов -> {stats['chunks']} чанков, dim={stats['dim']}, "
            f"embedder={embedder.name}, {stats['took_ms']} мс"
        )
        if args.save:
            index.save(args.save)
            print(f"[save] индекс сохранён в {args.save}")

    # 2. Запрос -> вектор -> top-k
    hits = index.search(args.query, k=args.k)
    if not hits:
        print("ничего не найдено — попробуйте переформулировать запрос", file=sys.stderr)
        return 1

    print(f"\n[search] запрос: {args.query!r}")
    for rank, hit in enumerate(hits, start=1):
        print(f"  {rank}. {hit.score:.3f}  {hit.chunk.location}")

    # 3. top-k -> промпт в рамках бюджета контекстного окна
    prompt, used = pack_context(args.query, hits, budget_tokens=args.budget)
    print(
        f"\n[context] использовано чанков: {len(used)} из {len(hits)}, "
        f"~{approx_tokens(prompt)} токенов при бюджете {args.budget}"
    )
    print("\n----- собранный промпт -----")
    print(prompt)
    print("-----------------------------")

    # 4. Опционально: реальный (или mock) вызов LLM
    if args.ask:
        answer = make_llm().chat(
            [
                {"role": "system", "content": "Отвечай строго по контексту."},
                {"role": "user", "content": prompt},
            ]
        )
        print("\n[answer]", answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
