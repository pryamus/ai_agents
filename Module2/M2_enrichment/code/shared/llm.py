"""Единый клиент LLM для лабораторных 2.4–2.6.

Два бэкенда за одним интерфейсом ``LLM.chat(messages) -> str``:

* :class:`OpenAICompatLLM` — реальный вызов любого OpenAI-совместимого API
  (OpenAI, OpenRouter, Together, vLLM, Ollama и т.п.) через ``/chat/completions``.
* :class:`ScriptedLLM` — детерминированный mock: заранее заданные ответы или
  функция-резидент. Позволяет отлаживать цикл агента без ключей и сети.

Переключение через переменные окружения (см. :func:`make_llm`):

    LLM_BASE_URL=https://api.openai.com/v1
    LLM_API_KEY=sk-...
    LLM_MODEL=gpt-4o-mini

Если переменные не заданы — используется mock (все примеры воспроизводимы).
"""

from __future__ import annotations

import abc
import json
import os
import time
from collections.abc import Callable, Iterable, Mapping

import httpx

Message = dict[str, str]  # {"role": "system"|"user"|"assistant"|"tool", "content": str}


class LLMError(RuntimeError):
    """Ошибка обращения к LLM (сеть, лимит, неверный ответ)."""


class LLM(abc.ABC):
    """Минимальный интерфейс чата, который понимают все агенты курса."""

    @abc.abstractmethod
    def chat(self, messages: list[Message], *, temperature: float = 0.0) -> str:
        """Вернуть текст ответа модели на историю сообщений."""


class OpenAICompatLLM(LLM):
    """Клиент OpenAI-совместимого API с повторами на временные ошибки.

    Повторяем 429/5xx/сетевые сбои с экспоненциальной задержкой — это
    базовая «отказоустойчивость» из темы 2.5 на уровне транспорта.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def chat(self, messages: list[Message], *, temperature: float = 0.0) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"model": self.model, "messages": messages, "temperature": temperature}
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}: {resp.text[:200]}",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(0.5 * (2**attempt))  # backoff: 0.5s, 1s, ...
        raise LLMError(f"LLM не ответила после {self.max_retries + 1} попыток: {last_error}")


class ScriptedLLM(LLM):
    """Mock: отдаёт заранее заготовленные ответы по очереди.

    Используется в практических работах, чтобы:

    * воспроизводить сценарий «агент падает → смотрим лог → правим промпт»
      без реальной модели (тема 2.5);
    * показать последовательность вызовов инструментов (тема 2.6).
    """

    def __init__(
        self,
        responses: Iterable[str] | None = None,
        *,
        responder: Callable[[list[Message]], str] | None = None,
    ) -> None:
        self._queue: list[str] = list(responses or [])
        self._responder = responder
        self.calls: list[list[Message]] = []  # вся история вызовов — удобно для отладки

    def chat(self, messages: list[Message], *, temperature: float = 0.0) -> str:
        self.calls.append([dict(m) for m in messages])
        if self._responder is not None:
            return self._responder(messages)
        if not self._queue:
            raise LLMError(
                "ScriptedLLM: ответы закончились — агент сделал больше шагов, "
                "чем предусмотрено сценарием"
            )
        return self._queue.pop(0)


def make_llm() -> LLM:
    """Фабрика: реальный API, если заданы переменные окружения, иначе mock."""
    base_url = os.environ.get("LLM_BASE_URL", "").strip()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    model = os.environ.get("LLM_MODEL", "").strip()
    if base_url and api_key and model:
        return OpenAICompatLLM(base_url, api_key, model)
    return ScriptedLLM(responder=_offline_fallback)


def _offline_fallback(messages: list[Message]) -> str:
    """Заглушка для /ask без настроенного API: честно сообщает об отсутствии LLM."""
    return (
        "[mock-LLM] Ключи не настроены (LLM_BASE_URL/LLM_API_KEY/LLM_MODEL), "
        "поэтому вместо ответа модели возвращён этот текст. Найденный контекст "
        "лежит в поле context_files ответа."
    )


def approx_tokens(text: str) -> int:
    """Грубая оценка числа токенов (~4 символа на токен для кода/латиницы).

    Точнее считать токенизатором модели, но для контроля лимитов контекстного
    окна в учебных примерах оценки достаточно. Для русского текста поправка
    больше (~2–3 символа на токен) — помните об этом при планировании бюджета.
    """
    return max(1, len(text) // 4)


def count_message_tokens(messages: list[Message]) -> int:
    """Оценить суммарный размер истории сообщений в токенах."""
    return sum(approx_tokens(m.get("content", "")) for m in messages) + 4 * len(messages)


def truncate(text: str, limit: int) -> str:
    """Обрезать текст до limit символов с явным маркером обрезки.

    Результат инструмента, вернувший мегабайты логов, раздувает контекстное
    окно и стоит денег — поэтому каждый ToolResult проходит через обрезку.
    """
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [обрезано: показано {limit} из {len(text)} символов]"


def dump_json(obj: object) -> str:
    """Каноничная JSON-сериализация (для промптов и логов)."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def last_user_text(messages: list[Message]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def as_mapping(text: str) -> Mapping[str, str]:
    """(вспомогательно) разобрать JSON-объект из текста модели."""
    data = json.loads(text)
    if not isinstance(data, dict):
        raise LLMError("ожидался JSON-объект")
    return data
