"""Связка IDE + агент + инструменты как код: генерация и проверка .vscode (3.2).

Конфигурация — артефакт, который можно генерировать, валидировать и хранить
в git: `init` создаёт `.vscode/{settings,tasks,extensions}.json`, `check`
проверяет чужие (или изменённые) конфиги на полноту и валидный JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))

VSCODE_FILES = ("settings.json", "tasks.json", "extensions.json")


def vscode_settings() -> dict:
    """Настройки: pytest как раннер, ruff как линтер/форматтер, UTF-8."""
    return {
        "python.testing.pytestArgs": ["."],
        "python.testing.pytestEnabled": True,
        "python.testing.unittestEnabled": False,
        "[python]": {
            "editor.defaultFormatter": "charliermarsh.ruff",
            "editor.formatOnSave": True,
            "editor.codeActionsOnSave": {"source.organizeImports": "explicit"},
        },
        "ruff.lineLength": 100,
        "files.encoding": "utf8",
        "files.eol": "\n",
    }


def vscode_tasks() -> dict:
    """Задачи: те же команды, что в AGENTS.md и лекциях (pytest, ruff, validate)."""
    def task(label: str, command: str) -> dict:
        return {
            "label": label,
            "type": "shell",
            "command": command,
            "presentation": {"reveal": "always", "panel": "new"},
            "problemMatcher": [],
        }

    return {
        "version": "2.0.0",
        "tasks": [
            task("pytest", "python -m pytest -q"),
            task("ruff", "ruff check ."),
            task("validate (2.3)", "python lab_2_3_agents_md/validate.py"),
        ],
    }


def vscode_extensions() -> dict:
    return {"recommendations": ["ms-python.python", "charliermarsh.ruff"]}


def render_vscode(target: Path) -> dict[str, Path]:
    """Записать три конфига. Возвращает пути записанных файлов."""
    vscode_dir = target / ".vscode"
    vscode_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "settings.json": vscode_settings(),
        "tasks.json": vscode_tasks(),
        "extensions.json": vscode_extensions(),
    }
    paths = {}
    for name, data in payloads.items():
        path = vscode_dir / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        paths[name] = path
    return paths


def validate_vscode(target: Path) -> list[str]:
    """Проверить конфиги. Возвращает список проблем (пусто = ок)."""
    problems: list[str] = []
    vscode_dir = target / ".vscode"
    for name in VSCODE_FILES:
        path = vscode_dir / name
        if not path.exists():
            problems.append(f"нет файла .vscode/{name}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f".vscode/{name}: битый JSON ({exc})")
            continue
        if name == "settings.json" and not data.get("python.testing.pytestEnabled"):
            problems.append("settings.json: pytest не включён как раннер")
        if name == "tasks.json":
            labels = {t.get("label") for t in data.get("tasks", [])}
            for want in ("pytest", "ruff"):
                if want not in labels:
                    problems.append(f"tasks.json: нет задачи {want!r}")
        if name == "extensions.json" and not data.get("recommendations"):
            problems.append("extensions.json: пустые recommendations")
    return problems


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IDE-конфиги как код (3.2)")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="сгенерировать .vscode")
    init.add_argument("--dir", type=Path, default=Path("."))
    check = sub.add_parser("check", help="проверить .vscode")
    check.add_argument("--dir", type=Path, default=Path("."))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "init":
        paths = render_vscode(args.dir)
        print("записано: " + ", ".join(str(p) for p in paths.values()))
        return 0
    problems = validate_vscode(args.dir)
    if problems:
        print("проблемы:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("конфиги в порядке: settings + tasks(pytest, ruff, validate) + extensions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
