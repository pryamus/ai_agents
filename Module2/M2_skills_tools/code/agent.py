"""Цикл агента: планирование -> исполнение -> проверка -> следующий шаг (тема 2.5).

Реализует классическую схему ReAct без привязки к провайдеру:

    step N:   LLM (план/решение)          — plan
              -> диспетчеризация инструмента — act (с таймаутом и ретраями)
              -> проверка результата        — check (валидация/классификация ошибки)
              -> результат -> истории       -> step N+1

Протокол «модель -> рантайм» — один JSON-объект (строгая схема Decision):

    {"thought": "...", "action": "tool", "tool": "grep_search", "args": {...}}
    {"thought": "...", "action": "final", "answer": "..."}

Почему не голый текст и не только function-calling: JSON-решение
* валидируется pydantic-схемой до исполнения (модель не может «вызвать»
  несуществующий инструмент молча);
* воспроизводимо мокается без сети (ScriptedLLM) — практика отладки (2.5)
  и вызовов инструментов (2.6) не требует ключей;
* совместимо с любым OpenAI-совместимым endpoint'ом без tools-протокола.
В проде предпочитают нативный function-calling — здесь видна механика.

Каждое событие пишется в JSONL-лог: без наблюдаемости агент не отлаживается.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

_CODE_ROOT = Path(__file__).resolve().parents[1]
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))  # запуск из каталога лаборатории: import shared

from shared.llm import LLM, LLMError, Message, truncate

# Лимиты по умолчанию (значения обсуждаются в лекции 2.5)
DEFAULT_MAX_STEPS = 8
DEFAULT_TOOL_TIMEOUT = 5.0        # секунд на один вызов инструмента
DEFAULT_TOOL_RETRIES = 1          # повтор только для retryable-ошибок
DEFAULT_PARSE_RETRIES = 2         # шансы модели выдать валидный JSON
DEFAULT_MAX_TOOL_ERRORS = 3       # подряд — и агент останавливается
TOOL_RESULT_LIMIT = 4000          # символов результата в историю


# ---------------------------------------------------------------------------
# Протокол решений модели (строгая схема)
# ---------------------------------------------------------------------------

class Decision(BaseModel):
    """Одно решение модели: вызвать инструмент или завершиться."""

    model_config = ConfigDict(extra="forbid")  # лишние ключи — ошибка, а не молчаливое игнорирование

    thought: str = Field(min_length=1, description="краткое рассуждение (CoT) перед действием")
    action: Literal["tool", "final"]
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    answer: str | None = None

    @model_validator(mode="after")
    def _check_payload(self) -> Decision:
        if self.action == "tool" and not self.tool:
            raise ValueError("action='tool' требует непустого поля 'tool'")
        if self.action == "final" and not (self.answer or "").strip():
            raise ValueError("action='final' требует непустого поля 'answer'")
        return self


def parse_decision(raw: str) -> tuple[Decision | None, str | None]:
    """Разобрать ответ модели. Возвращает (решение, ошибка_парсинга)."""
    text = raw.strip()
    # Частый формат: модель заворачивает JSON в markdown-фенсы
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[len("json"):]
    text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"не JSON: {exc}"
    if not isinstance(data, dict):
        return None, f"ожидался JSON-объект, получен {type(data).__name__}"
    try:
        return Decision(**data), None
    except ValidationError as exc:
        detail = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        return None, f"нарушение схемы: {detail}"


# ---------------------------------------------------------------------------
# Ошибки инструментов и протокол хоста
# ---------------------------------------------------------------------------

class ToolError(RuntimeError):
    """Ошибка вызова инструмента. retryable=True -> имеет смысл повтор."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ToolHost(Protocol):
    """Контракт, который реализуют DictToolHost (2.5) и ToolRegistry (2.6)."""

    def names(self) -> list[str]: ...

    def schema_list(self) -> list[dict[str, Any]]:
        """[{"name", "description", "params": {...json schema properties...}}]"""

    def dispatch(self, name: str, args: dict[str, Any]) -> str:
        """Валидация аргументов + исполнение. Бросает ToolError."""


@dataclass(frozen=True)
class SimpleTool:
    """Инструмент-функция для DictToolHost: имя, описание, JSON Schema, код."""

    name: str
    description: str
    params: dict[str, Any]                     # JSON Schema properties
    fn: Callable[..., str]
    required: list[str] = field(default_factory=list)


class DictToolHost:
    """Минимальный хост: словарь SimpleTool. Полноценный реестр — тема 2.6."""

    def __init__(self, tools: list[SimpleTool]) -> None:
        self._tools = {t.name: t for t in tools}

    def names(self) -> list[str]:
        return sorted(self._tools)

    def schema_list(self) -> list[dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description, "params": t.params}
            for t in self._tools.values()
        ]

    def dispatch(self, name: str, args: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            # Hallucinated tool name — классическая ошибка планировщика
            raise ToolError(
                "unknown_tool",
                f"нет инструмента {name!r}; доступны: {', '.join(self.names())}",
            )
        missing = [p for p in tool.required if p not in args]
        if missing:
            raise ToolError("invalid_args", f"не переданы аргументы: {', '.join(missing)}")
        extra = [a for a in args if a not in [*tool.required, *tool.params]]
        if extra:
            raise ToolError("invalid_args", f"лишние аргументы: {', '.join(extra)}")
        try:
            return tool.fn(**args)
        except TypeError as exc:
            raise ToolError("invalid_args", f"аргументы не подошли функции: {exc}") from exc
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError("runtime", f"{type(exc).__name__}: {exc}") from exc


# ---------------------------------------------------------------------------
# Наблюдаемость: JSONL-лог событий агента
# ---------------------------------------------------------------------------

class JsonlLogger:
    """Структурное логирование: одна строка = одно событие (JSON lines).

    Формат события: ts, run_id, level, event, step + поля события.
    Такие логи удобно грепать: jq 'select(.level=="ERROR")' run.jsonl.
    """

    def __init__(self, path: Path | None = None, run_id: str | None = None) -> None:
        self.path = path
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self.records: list[dict[str, Any]] = []
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, *, level: str = "INFO", step: int | None = None, **data: Any) -> dict:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "run_id": self.run_id,
            "level": level,
            "event": event,
            "step": step,
            **data,
        }
        self.records.append(record)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    @property
    def errors(self) -> list[dict[str, Any]]:
        return [r for r in self.records if r["level"] == "ERROR"]


# ---------------------------------------------------------------------------
# Промпты
# ---------------------------------------------------------------------------

SYSTEM_TEMPLATE = """Ты — автономный агент над кодовой базой.
Твои инструменты:
{tools_block}

Протокол ответа — СТРОГО один JSON-объект, без markdown и пояснений вокруг:
  {{"thought": "<рассуждение>", "action": "tool", "tool": "<имя>", "args": {{<аргументы>}}}}
  {{"thought": "<рассуждение>", "action": "final", "answer": "<итоговый ответ>"}}
Правила:
- выбирай только инструменты из списка; несуществующие имена запрещены;
- action="final" завершает работу — выдавай полный ответ пользователю.
"""

PARSE_FIX = (
    "Твой последний ответ не прошёл валидацию: {error}.\n"
    "Ответь СНОВА одним JSON-объектом по протоколу из системной инструкции. "
    "Без markdown, без текста вокруг."
)

TOOL_ERROR_FEEDBACK = (
    "Инструмент {tool} вернул ошибку [{code}]: {error}\n"
    "Не повторяй вызов без изменений: исправь аргументы или возьми другой инструмент."
)

TOOL_OK_FEEDBACK = "Результат инструмента {tool}:\n{result}"

FINAL_FIX = (
    "Ответ пустой или не прошёл проверку: {error}.\n"
    "Дай итоговый ответ по протоколу action=\"final\"."
)


def render_tools_block(host: ToolHost) -> str:
    """Описание инструментов для LLM: имя, параметры-схема, назначение."""
    lines = []
    for spec in host.schema_list():
        params = json.dumps(spec["params"], ensure_ascii=False)
        lines.append(f"- {spec['name']}({params}) — {spec['description']}")
    return "\n".join(lines) if lines else "(инструментов нет — сразу action=\"final\")"


# ---------------------------------------------------------------------------
# Результат и сам цикл
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    status: str                 # ok | max_steps | parse_error | tool_error | llm_error
    answer: str | None
    steps: int
    run_id: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class AgentLoop:
    """План-исполнение-проверка с лимитами, таймаутами и обработкой ошибок."""

    def __init__(
        self,
        llm: LLM,
        tools: ToolHost,
        *,
        system_prompt: str,
        max_steps: int = DEFAULT_MAX_STEPS,
        tool_timeout: float = DEFAULT_TOOL_TIMEOUT,
        tool_retries: int = DEFAULT_TOOL_RETRIES,
        parse_retries: int = DEFAULT_PARSE_RETRIES,
        logger: JsonlLogger | None = None,
        answer_check: Callable[[str], tuple[bool, str]] | None = None,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.tool_timeout = tool_timeout
        self.tool_retries = tool_retries
        self.parse_retries = parse_retries
        self.logger = logger or JsonlLogger()
        self.answer_check = answer_check

    # -- фазы ---------------------------------------------------------------

    def _call_tool(self, name: str, args: dict[str, Any]) -> str:
        """act + check: вызов с таймаутом и классификацией результата."""
        started = time.perf_counter()
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(self.tools.dispatch, name, args)
            try:
                result = future.result(timeout=self.tool_timeout)
            except FutureTimeoutError as exc:
                raise ToolError(
                    "timeout",
                    f"инструмент {name} не ответил за {self.tool_timeout} с",
                    retryable=True,
                ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        took_ms = round((time.perf_counter() - started) * 1000, 1)
        self.logger.log("tool_result", step=self._step, tool=name, took_ms=took_ms,
                        result_chars=len(result))
        return result

    def run(self, task: str) -> AgentResult:
        """Главный цикл. Гарантированно завершается: по шагам, ошибке или финалу."""
        self._step = 0
        parse_attempts = 0
        final_fix_used = False
        error_streak = 0

        messages: list[Message] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": task},
        ]
        self.logger.log("run_start", task=task, tools=self.tools.names(),
                        max_steps=self.max_steps)
        started = time.perf_counter()

        def finish(status: str, *, answer: str | None = None, error: str | None = None) -> AgentResult:
            self.logger.log(
                "run_finish", level="ERROR" if status != "ok" else "INFO",
                status=status, steps=self._step,
                took_ms=round((time.perf_counter() - started) * 1000, 1),
                error=error,
            )
            return AgentResult(status=status, answer=answer, steps=self._step,
                               run_id=self.logger.run_id, error=error)

        for step in range(1, self.max_steps + 1):
            self._step = step

            # -- plan: решение модели --------------------------------------
            try:
                raw = self.llm.chat(messages)
            except LLMError as exc:
                self.logger.log("llm_error", level="ERROR", step=step, error=str(exc))
                return finish("llm_error", error=str(exc))
            self.logger.log("llm_decision_raw", step=step, raw_chars=len(raw))

            decision, parse_error = parse_decision(raw)
            if decision is None:
                # check не пройден: валидация ответа модели
                parse_attempts += 1
                self.logger.log("parse_error", level="ERROR", step=step,
                                error=parse_error, attempt=parse_attempts, raw=raw[:500])
                if parse_attempts > self.parse_retries:
                    return finish("parse_error", error=f"модель не смогла ответить по схеме: {parse_error}")
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user",
                                 "content": PARSE_FIX.format(error=parse_error)})
                continue
            parse_attempts = 0
            messages.append({"role": "assistant", "content": raw})

            # -- финал -----------------------------------------------------
            if decision.action == "final":
                answer = (decision.answer or "").strip()
                if self.answer_check is not None:
                    valid, why = self.answer_check(answer)
                    if not valid and not final_fix_used:
                        final_fix_used = True
                        self.logger.log("final_rejected", level="WARN", step=step, reason=why)
                        messages.append({"role": "user",
                                         "content": FINAL_FIX.format(error=why)})
                        continue
                    if not valid:
                        return finish("parse_error", error=f"ответ не прошёл проверку: {why}")
                self.logger.log("final", step=step, answer_chars=len(answer))
                return finish("ok", answer=answer)

            # -- act: вызов инструмента с ретраями ------------------------
            self.logger.log("tool_call", step=step, tool=decision.tool, args=decision.args)
            attempts = 0
            call_ok = False
            while True:
                try:
                    result = self._call_tool(decision.tool, decision.args)
                    error_streak = 0
                    call_ok = True
                    break
                except ToolError as exc:
                    attempts += 1
                    self.logger.log("tool_error", level="ERROR", step=step,
                                    tool=decision.tool, code=exc.code,
                                    retryable=exc.retryable, attempt=attempts,
                                    error=str(exc))
                    if exc.retryable and attempts <= self.tool_retries:
                        time.sleep(0.1 * attempts)  # маленький backoff
                        continue
                    # check не пройден: ошибка уходит модели как обратная связь
                    error_streak += 1
                    messages.append({"role": "user", "content": TOOL_ERROR_FEEDBACK.format(
                        tool=decision.tool, code=exc.code, error=str(exc))})
                    if error_streak >= DEFAULT_MAX_TOOL_ERRORS:
                        return finish("tool_error",
                                      error=f"{error_streak} ошибок инструментов подряд")
                    break

            if not call_ok:
                continue  # следующий шаг: модель работает с ошибкой в истории

            # -- check -> следующий шаг: результат в историю ---------------
            messages.append({"role": "user", "content": TOOL_OK_FEEDBACK.format(
                tool=decision.tool, result=truncate(result, TOOL_RESULT_LIMIT))})

        self.logger.log("max_steps", level="WARN", step=self._step)
        return finish("max_steps", error=f"исчерпан лимит шагов ({self.max_steps})")


def build_system_prompt(tools: ToolHost) -> str:
    """Собрать системный промпт с блоком описаний инструментов."""
    return SYSTEM_TEMPLATE.format(tools_block=render_tools_block(tools))
