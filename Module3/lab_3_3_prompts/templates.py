"""Библиотека шаблонов промптов: рендер, контракт переменных, бюджет (тема 3.3).

Шаблон — это код: именованные переменные `{var}`, few-shot примеры,
ограничения и бюджет токенов. Рендер строгий: неизвестная переменная или
незакрытый плейсхолдер — ошибка, а не молчаливый мусор в промпте.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))
_CODE_ROOT = LAB.parent
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))  # approx_tokens из shared

from shared.llm import approx_tokens

PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


class PromptError(RuntimeError):
    """Нарушение контракта шаблона: нет переменной, лишний ключ, превышен бюджет."""


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    description: str
    system: str
    user_template: str
    variables: tuple[str, ...]
    few_shot: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    max_tokens: int = 4000


@dataclass
class RenderedPrompt:
    system: str
    user: str
    tokens_approx: int


def _placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER_RE.findall(text))


TEMPLATES: dict[str, PromptTemplate] = {
    "codegen": PromptTemplate(
        name="codegen",
        description="Генерация функции по спецификации",
        system="Ты — генератор Python-кода. Отвечай только кодом в ```python-блоке.",
        user_template=(
            "Напиши функцию `{func_name}`.\n"
            "Спецификация: {spec}\n"
            "Ограничения: {constraints_text}\n"
            "{few_shot_block}"
        ),
        variables=("func_name", "spec"),
        few_shot=(
            "Пример: parity(n) -> 'чет' если n % 2 == 0 иначе 'нечет'.",
        ),
        constraints=("только код, без пояснений", "аннотации типов обязательны"),
        max_tokens=2000,
    ),
    "refactor": PromptTemplate(
        name="refactor",
        description="Рефакторинг с сохранением поведения",
        system="Ты — инженер по рефакторингу. Поведение кода менять запрещено.",
        user_template=(
            "Отрефактори исходник ради цели: {goal}.\n"
            "Исходник:\n```python\n{source}\n```\n"
            "{few_shot_block}"
            "Верни diff-план списком: файл:строки — что и зачем."
        ),
        variables=("goal", "source"),
        few_shot=(
            "Пример цели: 'вынести повторяющийся try/except в хелпер без смены исключений'.",
        ),
        constraints=("поведение не менять", "ответ — список правок, не код целиком"),
        max_tokens=3000,
    ),
    "explain": PromptTemplate(
        name="explain",
        description="Объяснение логики кода",
        system="Ты — наставник. Объясняй просто, но точно.",
        user_template=(
            "Объясни, что делает код, для уровня {audience}.\n"
            "Код:\n```python\n{source}\n```\n"
            "Структура ответа: назначение → пошагово → краевые случаи."
        ),
        variables=("audience", "source"),
        constraints=("структура из трёх частей", "без переписывания кода"),
        max_tokens=2500,
    ),
}


def render(name: str, **values: str) -> RenderedPrompt:
    """Подставить переменные в шаблон. Строго: только объявленные переменные."""
    try:
        template = TEMPLATES[name]
    except KeyError as exc:
        raise PromptError(f"нет шаблона {name!r}; есть: {sorted(TEMPLATES)}") from exc

    unknown = [k for k in values if k not in template.variables]
    if unknown:
        raise PromptError(f"лишние переменные {unknown}; разрешены {list(template.variables)}")

    text = template.user_template
    for var in template.variables:
        if var not in values:
            raise PromptError(f"нет переменной {var!r} для шаблона {name!r}")
        text = text.replace("{" + var + "}", values[var])

    leftover = _placeholders(text) - set(template.variables) - {
        "constraints_text", "few_shot_block"}  # служебные — подставляются ниже
    if leftover:
        raise PromptError(f"незакрытые плейсхолдеры после подстановки: {sorted(leftover)}")

    constraints_text = "; ".join(template.constraints)
    text = text.replace("{constraints_text}", constraints_text)
    few_shot_block = "".join(f"> {ex}\n" for ex in template.few_shot)
    text = text.replace("{few_shot_block}", few_shot_block + ("\n" if few_shot_block else ""))

    tokens = approx_tokens(template.system) + approx_tokens(text)
    if tokens > template.max_tokens:
        raise PromptError(
            f"промпт ~{tokens} токенов при бюджете {template.max_tokens}: "
            f"сократите {sorted(values)}"
        )
    return RenderedPrompt(system=template.system, user=text, tokens_approx=tokens)
