"""Инструменты агента: grep, git diff, ruff (практика 2.6).

Каждый инструмент — обычная функция с @tool-декоратором: реестр сам
собирает JSON Schema из сигнатуры и описания из docstring'а.

Три типа «неудачи» разделены намеренно (это ключевая идея теории 2.6):

* ``ToolError(invalid_args, ...)``   — аргументы неверны: данные для правки моделью;
* ``ToolError(timeout, retryable=True)`` — временный сбой: повторить;
* «найдено 20 замечаний линтера»     — НЕ ошибка: рабочий результат.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_CODE_ROOT = Path(__file__).resolve().parents[1]
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))  # import shared / lab_2_4_rag

from tool_registry import ToolError, ToolRegistry, tool

from lab_2_4_rag.chunker import SKIP_DIRS

GIT_TIMEOUT = 10
RUFF_TIMEOUT = 25


@tool(timeout=10)
def grep_search(
    pattern: str,
    path: str = ".",
    include: str = "*.py",
    use_regex: bool = False,
    max_results: int = 50,
) -> str:
    """Найти строки в файлах, результат: путь:номер: текст (первые max_results).

    pattern: что искать — подстрока, либо regex при use_regex=true
    path: корневой каталог поиска
    include: glob-маска имён файлов, например "*.py" или "*.md"
    use_regex: трактовать pattern как регулярное выражение
    max_results: лимит строк результата (контекст модели ограничен)
    """
    root = Path(path)
    if not root.is_dir():
        raise ToolError("invalid_args", f"каталог не найден: {path}")
    try:
        rx = re.compile(pattern if use_regex else re.escape(pattern))
    except re.error as exc:
        raise ToolError("invalid_args", f"некорректный regex: {exc}") from exc

    hits: list[str] = []
    for file in sorted(root.rglob(include)):
        if not file.is_file() or any(part in SKIP_DIRS for part in file.parts):
            continue
        try:
            lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, start=1):
            if rx.search(line):
                hits.append(f"{file.relative_to(root)}:{lineno}: {line.strip()}")
                if len(hits) >= max_results:
                    return "\n".join(hits) + f"\n... [стоп по max_results={max_results}]"
    return "\n".join(hits) or "совпадений нет"


@tool(timeout=15)
def git_diff(path: str = ".", staged: bool = False, max_chars: int = 8000) -> str:
    """Показать git diff рабочего дерева или индекса (пустой diff = «изменений нет»).

    path: каталог репозитория
    staged: true — diff индекса (git diff --staged), false — рабочего дерева
    max_chars: обрезка слишком длинного diff
    """
    target = Path(path)
    if not target.is_dir():
        raise ToolError("invalid_args", f"каталог не найден: {path}")

    cmd = ["git", "diff", "--no-color"]
    if staged:
        cmd.append("--staged")
    try:
        proc = subprocess.run(
            cmd, cwd=target, capture_output=True, check=False,
            encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise ToolError("runtime", "git не найден в PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolError("timeout", f"git diff не ответил за {GIT_TIMEOUT} с",
                        retryable=True) from exc

    if proc.returncode != 0:
        # «not a git repository» и прочие причины — runtime-ошибка, не ретраится
        raise ToolError(
            "runtime",
            f"git diff rc={proc.returncode}: {(proc.stderr or '').strip()[:300]}",
        )
    out = proc.stdout
    if not out.strip():
        # Пустой diff — валидный ответ (данные), а не исключение
        return "изменений нет (diff пуст)"
    if len(out) > max_chars:
        return out[:max_chars] + "\n... [diff обрезан]"
    return out


@tool(timeout=30)
def ruff_lint(path: str = ".", select: str = "") -> str:
    """Прогнать линтер ruff и вернуть замечания (concrete-формат).

    path: файл или каталог для проверки
    select: дополнительные коды правил через запятую, например "F,E,B"
    """
    cmd = ["ruff", "check", "--output-format", "concise"]
    if select:
        cmd += ["--select", select]
    cmd.append(path)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, check=False, encoding="utf-8",
            errors="replace", timeout=RUFF_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise ToolError("runtime", "ruff не найден в PATH: pip install ruff") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolError("timeout", f"ruff не ответил за {RUFF_TIMEOUT} с",
                        retryable=True) from exc

    output = (proc.stdout or "").strip()
    if proc.returncode == 0:
        return "Ruff: замечаний нет"
    if proc.returncode == 1:
        # Замечания линтера — это результат работы инструмента, а не падение
        count = len([ln for ln in output.splitlines() if ln.strip()])
        return f"Ruff: замечаний найдено {count}\n{output}"
    raise ToolError(
        "runtime",
        f"ruff не смог проверить код (rc={proc.returncode}): "
        f"{(proc.stderr or output)[:300]}",
    )


def default_registry(root: Path | None = None) -> ToolRegistry:
    """Стандартный набор инструментов курса, привязанный к каталогу root."""
    registry = ToolRegistry(root=root)
    for fn in (grep_search, git_diff, ruff_lint):
        registry.register(fn)
    return registry
