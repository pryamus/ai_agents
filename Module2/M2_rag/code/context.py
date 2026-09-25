"""Сборка контекста под бюджет контекстного окна (тема 2.4).

Найденные чанки не копируются в промпт слепо: каждый стоит токенов и денег,
а модель хуже отвечает при переполнении («lost in the middle»). Поэтому
отбор идёт по убыванию релевантности, пока не исчерпан бюджет токенов.
"""

from __future__ import annotations

import sys
from pathlib import Path

_CODE_ROOT = Path(__file__).resolve().parents[1]
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))  # запуск из каталога лаборатории: import shared

from index import SearchHit

from shared.llm import approx_tokens

DEFAULT_BUDGET_TOKENS = 2000   # жёсткая доля контекстного окна под retrieval
DEFAULT_MAX_HITS = 8

CONTEXT_HEADER = (
    "Контекст из репозитория (релевантные фрагменты, отсортированы по релевантности):\n"
)


def pack_context(
    question: str,
    hits: list[SearchHit],
    *,
    budget_tokens: int = DEFAULT_BUDGET_TOKENS,
    max_hits: int = DEFAULT_MAX_HITS,
) -> tuple[str, list[SearchHit]]:
    """Собрать блок контекста + вопросы в один промпт.

    Возвращает (промпт, фактически использованные hits). Обрезка по бюджету:
    чанки добавляются по одному, пока суммарная оценка не упрётся в бюджет.
    """
    used: list[SearchHit] = []
    parts: list[str] = []
    spent = approx_tokens(CONTEXT_HEADER) + approx_tokens(question) + 32  # служебный запас

    for hit in hits[:max_hits]:
        body = f"\n--- Файл: {hit.chunk.location} (релевантность {hit.score:.3f}) ---\n{hit.chunk.text}\n"
        cost = approx_tokens(body)
        if spent + cost > budget_tokens and used:
            break  # следующий чанк уже не влезает — хватит
        if not used and cost > budget_tokens:
            # первый чанк обязателен, даже если сам по себе жирный: режем его хвост
            body = hit.chunk.text[: budget_tokens * 4]
            cost = approx_tokens(body)
            body = f"\n--- Файл: {hit.chunk.location} (обрезан под бюджет) ---\n{body}\n"
        parts.append(body)
        spent += cost
        used.append(hit)

    prompt = (
        CONTEXT_HEADER
        + "".join(parts)
        + "\n---\n"
        + f"Вопрос: {question}\n"
        + "Ответь на основе контекста. Если ответа нет в контексте — прямо скажи об этом "
        + "и укажи, каких данных не хватило."
    )
    return prompt, used
