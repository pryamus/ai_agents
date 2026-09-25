"""Агент с инструментами: план -> grep -> ruff -> итог (практика 2.6).

Показывает полный стек: ToolRegistry (схемы для LLM, валидация, таймауты)
внутри AgentLoop из лабораторной 2.5. По умолчанию сценарий идёт через
ScriptedLLM (офлайн, воспроизводимо); флаг --live подключает реальный API.

    python run_tools_agent.py                  # сценарий grep -> ruff -> итог
    python run_tools_agent.py --show-schema    # что именно видит LLM
    python run_tools_agent.py --live           # нужен LLM_BASE_URL/LLM_API_KEY/LLM_MODEL
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))
_CODE_ROOT = LAB.parent
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))
_LAB_2_5 = _CODE_ROOT / "lab_2_5_loop"
if str(_LAB_2_5) not in sys.path:
    sys.path.insert(0, str(_LAB_2_5))  # AgentLoop/ToolError живут в лабораторной 2.5

from agent import AgentLoop, JsonlLogger, build_system_prompt
from tool_impls import default_registry

from shared.llm import ScriptedLLM, make_llm

DEFAULT_ROOT = LAB  # в лаборатории есть TODO и замечания линтера? см. README

# Сценарий «хорошей» модели: точные имена и аргументы из описаний
SCENARIO = [
    ('{"thought": "сначала найду TODO", "action": "tool", "tool": "grep_search", '
     '"args": {"pattern": "TODO", "path": ".", "include": "*.py"}}'),
    ('{"thought": "теперь проверю код линтером", "action": "tool", "tool": "ruff_lint", '
     '"args": {"path": "."}}'),
    ('{"thought": "данные собраны", "action": "final", "answer": "Готово: '
     'grep_search нашёл TODO-комментарии, ruff_lint сообщил замечания — '
     'оба результата в истории шагов агента."}'),
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Демо агента с инструментами (2.6)")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT,
                        help="каталог, с которым работает агент (корень для путей)")
    parser.add_argument("--task", default="Найди TODO в коде и проверь каталог линтером")
    parser.add_argument("--show-schema", action="store_true",
                        help="напечатать JSON Schema инструментов (промпт для LLM)")
    parser.add_argument("--live", action="store_true",
                        help="использовать реальный LLM API вместо сценария")
    parser.add_argument("--log", type=Path, default=LAB / "logs" / "tools_run.jsonl")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    registry = default_registry(root=args.root)
    system_prompt = build_system_prompt(registry)

    if args.show_schema:
        print("-- схемы инструментов, которые видит LLM --")
        for spec in registry.schema_list():
            print(json.dumps(spec, ensure_ascii=False, indent=2))
        print()

    if args.live:
        llm = make_llm()
        if isinstance(llm, ScriptedLLM):
            print("LLM API не настроен: задайте LLM_BASE_URL, LLM_API_KEY, LLM_MODEL",
                  file=sys.stderr)
            return 2
    else:
        llm = ScriptedLLM(responses=SCENARIO)

    logger = JsonlLogger(args.log)
    loop = AgentLoop(llm, registry, system_prompt=system_prompt,
                     max_steps=6, tool_timeout=10, logger=logger)
    result = loop.run(args.task)

    print(f"статус: {result.status}, шагов: {result.steps}, run_id: {result.run_id}")
    print("\n-- события шагов (лог) --")
    for rec in logger.records:
        if rec["event"] in {"tool_call", "tool_result", "tool_error", "final", "run_finish"}:
            view = {k: rec[k] for k in ("step", "event", "tool", "code", "took_ms",
                                        "result_chars", "status", "level") if k in rec}
            print("  " + json.dumps(view, ensure_ascii=False))
    print(f"\n-- ответ --\n{result.answer}")
    print(f"\nполный JSONL-лог: {args.log}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
