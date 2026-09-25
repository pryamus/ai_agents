"""Рендер шаблонов из CLI + линт (практика 3.3).

Запуск:  python render.py --template codegen --set func_name=parity --set spec="..."
          python render.py --template refactor --set goal="..." --set source="@file.py"
Значение вида @путь читается из файла.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))

from lint import lint_prompt
from templates import TEMPLATES, PromptError, render


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Рендер промптов из шаблонов (3.3)")
    parser.add_argument("--template", choices=sorted(TEMPLATES), required=True)
    parser.add_argument("--set", action="append", default=[],
                        help="VAR=значение (значение @файл читается с диска)")
    parser.add_argument("--lint", action="store_true", help="прогнать линтер промптов")
    return parser.parse_args(argv)


def _resolve(value: str) -> str:
    if value.startswith("@"):
        return Path(value[1:]).read_text(encoding="utf-8")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    values: dict[str, str] = {}
    for item in args.set:
        if "=" not in item:
            print(f"ошибка: {item!r} — нужен формат VAR=значение", file=sys.stderr)
            return 2
        key, value = item.split("=", 1)
        values[key] = _resolve(value)
    try:
        rendered = render(args.template, **values)
    except PromptError as exc:
        print(f"ошибка контракта: {exc}", file=sys.stderr)
        return 2
    print(f"--- system (~{rendered.tokens_approx} токенов всего) ---")
    print(rendered.system)
    print("--- user ---")
    print(rendered.user)
    if args.lint:
        findings = lint_prompt(rendered, max_tokens=TEMPLATES[args.template].max_tokens)
        print("--- lint ---")
        if not findings:
            print("замечаний нет")
        for finding in findings:
            print(f"  [{finding.code}] {finding.message}")
        return 1 if any(f.code in ("no-role", "over-budget") for f in findings) else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
