"""Реестр инструментов (тема 2.6): @tool, JSON Schema для LLM, валидация, таймауты.

Три обязанности между моделью и «сырым» Python-кодом:

1. **Описать** функцию для LLM: имя + docstring + JSON Schema, собранные из
   аннотаций сигнатуры (pydantic-модель -> model_json_schema()).
   От качества описания зависит, выберет ли модель инструмент и с какими
   аргументами — это то же «описание функций для LLM» из теории.
2. **Валидировать** аргументы ДО вызова: extra="forbid", обязательные поля,
   типы. Ошибка валидации — это данные для модели (feedback), а не exception
   наружу.
3. **Изолировать** исполнение: таймаут, обрезка вывода, опциональная
   привязка к корню каталога (защита от path traversal).

Реестр реализует ToolHost из lab_2_5_loop/agent.py — тот же цикл агента
работает с ним без изменений.
"""

from __future__ import annotations

import inspect
import json
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Any, get_type_hints

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

_LAB_2_5 = Path(__file__).resolve().parents[1] / "lab_2_5_loop"
if str(_LAB_2_5) not in sys.path:
    sys.path.insert(0, str(_LAB_2_5))  # цикл и ToolError живут в лабораторной 2.5

from agent import ToolError

DEFAULT_TOOL_TIMEOUT = 15.0     # секунд на исполнение
DEFAULT_MAX_OUTPUT = 4000       # символов результата, уходящих модели
DOC_PARAM_RE = r"^(\w+)\s*:\s*(.+)$"  # строки "name: описание" в docstring


# ---------------------------------------------------------------------------
# Описание функции для LLM
# ---------------------------------------------------------------------------

def _first_paragraph(doc: str | None) -> str:
    """Краткое описание инструмента: первый абзац docstring."""
    if not doc:
        return ""
    for block in doc.strip().split("\n\n"):
        text = " ".join(line.strip() for line in block.splitlines())
        if text:
            return text
    return ""


def _param_docs(doc: str | None) -> dict[str, str]:
    """Извлечь описания параметров из строк вида «name: текст»."""
    import re

    docs: dict[str, str] = {}
    if not doc:
        return docs
    for line in doc.splitlines():
        match = re.match(DOC_PARAM_RE, line.strip())
        if match and match.group(1) not in docs:
            docs[match.group(1)] = match.group(2).strip()
    return docs


def build_args_model(fn: Callable[..., Any]) -> type[BaseModel]:
    """Собрать pydantic-модель аргументов из сигнатуры функции.

    * обязательность — по отсутствию default;
    * описание параметра — из docstring («name: текст»);
    * extra="forbid" — лишние ключи от модели (hallucinated args) отклоняются.
    """
    hints = get_type_hints(fn)
    sig = inspect.signature(fn)
    param_docs = _param_docs(inspect.getdoc(fn))
    fields: dict[str, Any] = {}

    for name, param in sig.parameters.items():
        if name in {"self", "cls"} or param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        annotation = hints.get(name, str)
        description = param_docs.get(name)
        if param.default is inspect.Parameter.empty:
            default = Field(description=description)          # обязательный
        else:
            default = Field(default=param.default, description=description)
        fields[name] = (annotation, default)

    return create_model(
        f"{fn.__name__}_args",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


@dataclass(frozen=True)
class ToolSpec:
    """Готовый инструмент: описание для LLM + валидатор + исполнитель."""

    name: str
    description: str
    params_schema: dict[str, Any]      # JSON Schema (properties/required/типы)
    validator: type[BaseModel]
    fn: Callable[..., Any]
    timeout: float = DEFAULT_TOOL_TIMEOUT
    max_output: int = DEFAULT_MAX_OUTPUT


def tool(
    name: str | None = None,
    *,
    description: str | None = None,
    timeout: float = DEFAULT_TOOL_TIMEOUT,
    max_output: int = DEFAULT_MAX_OUTPUT,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Декоратор: превратить функцию в инструмент с готовым ToolSpec."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        model = build_args_model(fn)
        schema = model.model_json_schema()
        schema.pop("title", None)  # служебное поле pydantic — модели оно не нужно
        spec = ToolSpec(
            name=name or fn.__name__,
            description=description or _first_paragraph(inspect.getdoc(fn)),
            params_schema=schema,
            validator=model,
            fn=fn,
            timeout=timeout,
            max_output=max_output,
        )
        fn.__tool_spec__ = spec
        return fn  # функция остаётся обычной — её можно вызывать и в тестах напрямую

    return decorator


# ---------------------------------------------------------------------------
# Реестр (реализует ToolHost цикла из 2.5)
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Реестр инструментов: регистрация -> схемы для промпта -> dispatch.

    root (опционально) — если задан, строковые аргументы-пути не должны
    выходить за его пределы: простейшая защита от path traversal.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self.root = root.resolve() if root else None

    def register(self, item: ToolSpec | Callable[..., Any]) -> ToolSpec:
        spec = item if isinstance(item, ToolSpec) else getattr(item, "__tool_spec__", None)
        if spec is None:
            raise ToolError(
                "registration",
                f"{getattr(item, '__name__', item)} не обёрнут декоратором @tool",
            )
        if spec.name in self._tools:
            raise ToolError("registration", f"инструмент {spec.name!r} уже зарегистрирован")
        self._tools[spec.name] = spec
        return spec

    # -- ToolHost ------------------------------------------------------------
    def names(self) -> list[str]:
        return sorted(self._tools)

    def schema_list(self) -> list[dict[str, Any]]:
        """Что видит LLM в системном промпте: имя + описание + схема аргументов."""
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "params": spec.params_schema,
            }
            for spec in sorted(self._tools.values(), key=lambda s: s.name)
        ]

    def dispatch(self, name: str, args: dict[str, Any]) -> str:
        """Валидация -> путь-проверка -> вызов с таймаутом -> нормализация вывода."""
        spec = self._tools.get(name)
        if spec is None:
            raise ToolError(
                "unknown_tool",
                f"нет инструмента {name!r}; доступны: {', '.join(self.names())}",
            )

        # 1. Валидация аргументов по той же схеме, что увидит LLM
        try:
            validated = spec.validator.model_validate(args)
        except ValidationError as exc:
            detail = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
            )
            raise ToolError("invalid_args", detail) from exc

        # 2. Пути — только внутрь разрешённого корня (если корень задан)
        data = validated.model_dump()
        if self.root is not None:
            for key, value in data.items():
                if key in {"path", "file", "dir"} and isinstance(value, str):
                    target = (self.root / value).resolve() if not Path(value).is_absolute() \
                        else Path(value).resolve()
                    if not target.is_relative_to(self.root):
                        raise ToolError(
                            "permission",
                            f"путь {value!r} выходит за разрешённый корень {self.root}",
                        )
                    data[key] = str(target)

        # 3. Исполнение с таймаутом (зависшая функция не вешает цикл агента)
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(spec.fn, **data)
            try:
                result = future.result(timeout=spec.timeout)
            except FutureTimeoutError as exc:
                raise ToolError(
                    "timeout",
                    f"{name} не ответил за {spec.timeout} с",
                    retryable=True,
                ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        # 4. Нормализация: любой тип -> строка для модели, с обрезкой вывода
        #    (время исполнения цикл агента меряет сам — событие tool_result)
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=1)
        if len(text) > spec.max_output:
            text = text[: spec.max_output] + \
                f"\n... [обрезано: показано {spec.max_output} из {len(text)} символов]"
        return text
