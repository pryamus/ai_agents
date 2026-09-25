"""Отладка агента: анализ логов неудачного промпта и его починка (практика 2.5).

Ход работы (ровно то, что требуется в плане курса):

  1. Запуск с промптом V1 (смутным) -> агент падает, JSONL-лог полон ERROR.
  2. Анализ лога: какие события, что они значат, куда смотреть.
  3. Правка промпта -> V2 (протокол + список инструментов + few-shot)
     -> тот же сценарий проходит чисто.
  4. Дополнительно: таймаут медленного инструмента -> retry -> деградация.

Запуск:  python debug_failure.py     (логи пишутся в logs/)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))
_CODE_ROOT = LAB.parent
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))

from agent import AgentLoop, DictToolHost, JsonlLogger, SimpleTool, build_system_prompt

from shared.llm import ScriptedLLM

LOG_DIR = LAB / "logs"

# ---------------------------------------------------------------------------
# Инструменты сценария (упрощённые — полный grep и linter будут в 2.6)
# ---------------------------------------------------------------------------

def _grep(pattern: str, path: str = ".") -> str:
    root = Path(path)
    found = []
    for file in sorted(root.rglob("*.py")):
        if any(part in {".git", "__pycache__", "logs"} for part in file.parts):
            continue
        for lineno, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
            if pattern in line:
                found.append(f"{file.relative_to(root)}:{lineno}: {line.strip()}")
    return "\n".join(found[:50]) or "совпадений нет"


TOOLS = [
    SimpleTool(
        name="grep_search",
        description="Построчный поиск литерала в *.py файлах каталога",
        params={
            "pattern": {"type": "string", "description": "что искать"},
            "path": {"type": "string", "description": "корень поиска"},
        },
        fn=_grep,
        required=["pattern"],
    ),
]
HOST = DictToolHost(TOOLS)

# Промпт V1 — типичная «первая версия»: роль есть, протокола и инструментов нет
PROMPT_V1 = (
    "Ты — агент-помощник по коду. Работай аккуратно и помогай пользователю "
    "решать задачи быстрее."
)

# Промпт V2 — собирается из тех же данных, что видит модель (описания инструментов)
PROMPT_V2 = build_system_prompt(HOST)


def section(title: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


def print_log(path: Path, limit: int = 12) -> list[dict]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    print(f"\n-- JSONL-лог {path.relative_to(LAB)} ({len(records)} событий) --")
    for rec in records[:limit]:
        compact = {k: v for k, v in rec.items() if v is not None and k not in {"run_id"}}
        print("  " + json.dumps(compact, ensure_ascii=False))
    if len(records) > limit:
        print(f"  ... и ещё {len(records) - limit} событий")
    return records


def analyze(records: list[dict]) -> None:
    print("\n-- Анализ ERROR/WARN событий --")
    problems = [r for r in records if r["level"] in {"ERROR", "WARN"}]
    for rec in problems:
        print(f"  [{rec['level']}] шаг {rec.get('step')}: {rec['event']} — {rec.get('error') or rec.get('reason') or rec.get('status') or ''}")
    if not problems:
        print("  ошибок нет")


def main() -> int:
    # -----------------------------------------------------------------------
    section("Шаг 1: прогон с плохим промптом V1 (ScriptedLLM имитирует модель)")
    # -----------------------------------------------------------------------
    bad_llm = ScriptedLLM(responses=[
        # модель выдумала имя инструмента "search" вместо grep_search
        '{"thought": "поищу TODO", "action": "tool", "tool": "search", "args": {"pattern": "TODO"}}',
        # см. промпт V1: модели негде узнать протокол -> болтовня вместо JSON
        "Сейчас поищу TODO в проекте, секунду.",
        "Как я и говорил, формат ответа тут не определён...",
        "Вот мои мысли по поводу задачи: думаю, стоит начать с обзора файлов.",
    ])
    logger1 = JsonlLogger(LOG_DIR / "run1_bad.jsonl")
    loop1 = AgentLoop(bad_llm, HOST, system_prompt=PROMPT_V1,
                      max_steps=6, logger=logger1)
    result1 = loop1.run("Найди все TODO в проекте и перечисли их")
    print(f"статус: {result1.status!r}, шагов: {result1.steps}, ошибка: {result1.error}")

    records1 = print_log(LOG_DIR / "run1_bad.jsonl")
    analyze(records1)

    # -----------------------------------------------------------------------
    section("Шаг 2: что показал лог (вывод для инженера)")
    # -----------------------------------------------------------------------
    print(
        """
1. tool_error [unknown_tool]: модель назвала инструмент 'search' —
   в промпте V1 списка инструментов НЕТ, модель угадывает имена.
2. parse_error x3: модель отвечает прозой — в V1 не описан JSON-протокол,
   рантайм честно вернул ей ошибку валидации (parse_retries исчерпан).
3. Цикл остановлен по лимиту ошибок, а не завис: каждый отказ — событие
   в JSONL с шагом, кодом и сырым ответом модели (raw).

Вывод: чинить нужно ПРОМПТ (первопричина), а не цикл: дать протокол
и точечный список инструментов.
"""
    )
    print("-- diff промптов --")
    print(f"V1 ({len(PROMPT_V1)} симв.): {PROMPT_V1!r}")
    print(f"V2 ({len(PROMPT_V2)} симв.): системный протокол + описания инструментов:")
    print(PROMPT_V2)

    # -----------------------------------------------------------------------
    section("Шаг 3: прогон с починенным промптом V2 (та же модель, тот же хост)")
    # -----------------------------------------------------------------------
    good_llm = ScriptedLLM(responses=[
        ('{"thought": "использую описанный grep_search", "action": "tool", '
         '"tool": "grep_search", "args": {"pattern": "TODO", "path": "."}}'),
        ('{"thought": "данные собраны", "action": "final", "answer": "Найдены TODO '
          'в файлах проекта (см. результат grep_search); полный список — в ответе агента."}'),
    ])
    logger2 = JsonlLogger(LOG_DIR / "run2_fixed.jsonl")
    loop2 = AgentLoop(good_llm, HOST, system_prompt=PROMPT_V2,
                      max_steps=6, logger=logger2)
    result2 = loop2.run("Найди все TODO в проекте и перечисли их")
    print(f"статус: {result2.status!r}, шагов: {result2.steps}")
    print(f"ответ: {result2.answer}")

    records2 = print_log(LOG_DIR / "run2_fixed.jsonl", limit=8)
    analyze(records2)

    print("\n-- сравнение прогонов --")
    print(f"  V1: статус={result1.status}, ERROR/WARN={sum(1 for r in records1 if r['level'] in {'ERROR', 'WARN'})}")
    print(f"  V2: статус={result2.status}, ERROR/WARN={sum(1 for r in records2 if r['level'] in {'ERROR', 'WARN'})}")

    # -----------------------------------------------------------------------
    section("Шаг 4: таймаут инструмента -> retry -> деградация")
    # -----------------------------------------------------------------------
    def slow_tool() -> str:
        time.sleep(2.0)
        return "наконец-то результат"

    tools_b = TOOLS + [SimpleTool(
        name="slow_tool", description="Ненадёжный внешний сервис (спит 2 с)",
        params={}, fn=slow_tool, required=[],
    )]
    host_b = DictToolHost(tools_b)
    timeout_llm = ScriptedLLM(responses=[
        '{"thought": "попробую внешний сервис", "action": "tool", "tool": "slow_tool", "args": {}}',
        ('{"thought": "таймаут -> беру быстрый аналог", "action": "final", "answer": '
         '"slow_tool не ответил за 0.5 с (2 попытки); данные получены альтернативным путём."}'),
    ])
    logger3 = JsonlLogger(LOG_DIR / "run3_timeout.jsonl")
    loop3 = AgentLoop(timeout_llm, host_b, system_prompt=build_system_prompt(host_b),
                      max_steps=5, tool_timeout=0.5, tool_retries=1, logger=logger3)
    result3 = loop3.run("Получи данные внешним сервисом")
    print(f"статус: {result3.status!r}, шагов: {result3.steps}")
    records3 = print_log(LOG_DIR / "run3_timeout.jsonl", limit=10)
    analyze(records3)
    print(
        """
Механика: timeout -> retryable=True -> 1 повтор с backoff -> после
исчерпания повторов ошибка ушла модели как feedback, модель деградировала
на быстрый путь и завершилась корректно (status=ok), а не упала.
"""
    )

    all_clean = result2.status == "ok" and result3.status == "ok"
    print("ИТОГ:", "после правки промпта и с таймаутами всё работает" if all_clean else "ЕСТЬ ПРОБЛЕМЫ")
    return 0 if all_clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
