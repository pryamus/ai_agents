"""Doctor окружения: связка IDE + агент + инструменты в наличии (тема 3.2).

Проверяет то, что нужно практике курса: Python, pytest, ruff, git и CLI
opencode. Каждая проверка — {name, ok, detail, hint}: врач ставит диагноз
и сразу выписывает рецепт. Опциональные компоненты не роняют exit-код.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))

MIN_PYTHON = (3, 11)


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    hint: str = ""
    required: bool = True


def _version_of(binary: str, *args: str) -> str:
    try:
        proc = subprocess.run(
            [binary, *args], capture_output=True, check=False,
            encoding="utf-8", errors="replace", timeout=15,
        )
    except (FileNotFoundError, OSError):
        return ""
    if proc.returncode != 0:
        return ""
    return ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()[0][:80]


def check_python() -> Check:
    ok = sys.version_info >= MIN_PYTHON
    return Check(
        "python",
        ok,
        f"{sys.version.split()[0]} (нужен >={'.'.join(map(str, MIN_PYTHON))})",
        "установите Python 3.11+ и перезапустите shell",
    )


def check_module(name: str, hint: str) -> Check:
    found = importlib.util.find_spec(name) is not None
    return Check(name, found, "импортируется" if found else "не найден", hint)


def check_binary(name: str, version_args: tuple[str, ...], hint: str,
                 required: bool = True) -> Check:
    path = shutil.which(name)
    if path is None:
        return Check(name, False, "нет в PATH", hint, required)
    return Check(name, True, _version_of(path, *version_args) or path, hint, required)


def run_doctor() -> list[Check]:
    """Все проверки связки. Порядок — от базового к агентному слою."""
    return [
        check_python(),
        check_module("pytest", "pip install pytest"),
        check_binary("ruff", ("--version",), "pip install ruff"),
        check_binary("git", ("--version",), "установите git и добавьте в PATH"),
        check_binary("opencode", ("--version",), "npm install -g @opencode/cli"),
        check_binary("node", ("--version",), "опционально: нужен только для npm-установки",
                     required=False),
    ]


def render_md(checks: list[Check]) -> str:
    lines = ["# Doctor окружения", ""]
    for check in checks:
        mark = "✓" if check.ok else ("✗" if check.required else "○")
        req = "" if check.required else " (опционально)"
        lines.append(f"- {mark} **{check.name}**{req}: {check.detail}")
        if not check.ok:
            lines.append(f"  → {check.hint}")
    failed = [c.name for c in checks if not c.ok and c.required]
    lines += ["", "Итог: " + ("всё обязательное на месте" if not failed
                              else f"не хватает: {', '.join(failed)}")]
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Проверка связки IDE+агент+инструменты (3.2)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--md-out", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    checks = run_doctor()
    if args.json:
        print(json.dumps([asdict(c) for c in checks], ensure_ascii=False, indent=1))
    else:
        print(render_md(checks))
    if args.md_out:
        args.md_out.write_text(render_md(checks), encoding="utf-8")
    return 0 if all(c.ok for c in checks if c.required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
