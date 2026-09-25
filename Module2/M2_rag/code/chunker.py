"""Чанкинг: нарезка кода и документов на фрагменты для векторного индекса.

Зачем чанкить, а не индексировать файл целиком:

* вектор — семантика одного смысла; смешанный файл из 10 функций даёт
  «усреднённый» вектор, который плохо бьётся в поиск;
* в контекстное окно кладут релевантные фрагменты, а не весь репозиторий;
* мелкие чанки (300–500 токенов) точнее по рангу, но теряют связность —
  поэтому overlap и группировка по функциям/классам.

Для Python используется AST (парсер): функция/класс целиком — естественная
грань чанка. Если парсинг невозможен (синтаксическая ошибка) — откат на
окно по строкам с перекрытием.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_CHARS = 1200   # ~300 токенов на чанк
DEFAULT_OVERLAP = 100      # перекрытие окна, чтобы не рвать контекст посередине
MAX_FILE_CHARS = 200_000   # защита от гигантских файлов (дампы, бандлы)

SKIP_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", "dist", "build", ".next",
}
CODE_EXTS = {".py"}
DOC_EXTS = {".md", ".txt", ".rst"}


@dataclass(frozen=True)
class Chunk:
    """Один фрагмент для индексации и попадания в контекст."""

    chunk_id: str      # "path/to/file.py:10-42" — стабильный ID для дедупликации
    path: str          # путь относительно корня, posix
    start_line: int    # 1-based, включительно
    end_line: int
    text: str
    language: str      # "py", "md", ...
    kind: str          # "code" | "doc"

    @property
    def approx_tokens(self) -> int:
        return max(1, len(self.text) // 4)

    @property
    def location(self) -> str:
        return f"{self.path}:{self.start_line}-{self.end_line}"


# ---------------------------------------------------------------------------
# Низкоуровневые нарезки
# ---------------------------------------------------------------------------

def _window_spans(
    lines: list[str], start: int, end: int, max_chars: int, overlap: int
) -> list[tuple[int, int]]:
    """Нарезать строки [start, end] (1-based) на окна не больше max_chars."""
    spans: list[tuple[int, int]] = []
    win_start = start
    size = 0
    for lineno in range(start, end + 1):
        line_len = len(lines[lineno - 1]) + 1
        if size + line_len > max_chars and lineno > win_start:
            spans.append((win_start, lineno - 1))
            win_start = max(win_start + 1, lineno - max(1, overlap // max(1, max_chars // 10)))
            win_start = max(win_start + 1, lineno - overlap) if lineno - overlap > win_start else win_start + 1
            size = sum(len(lines[i - 1]) + 1 for i in range(win_start, lineno + 1))
        else:
            size += line_len
    if win_start <= end:
        spans.append((win_start, end))
    # страховка от пустых окон
    return [(a, b) for a, b in spans if a <= b] or [(start, end)]


def _python_spans(source: str, max_chars: int, overlap: int) -> list[tuple[int, int]]:
    """Границы чанков Python: top-level узлы (функции, классы, импорты)."""
    lines = source.splitlines()
    if not lines:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _window_spans(lines, 1, len(lines), max_chars, overlap)

    spans: list[tuple[int, int]] = []
    for node in tree.body:
        decorators = getattr(node, "decorator_list", [])
        start = min([node.lineno, *(d.lineno for d in decorators)])
        end = node.end_lineno or node.lineno
        if spans and start <= spans[-1][1]:          # пересечение (на практике редко)
            spans[-1] = (spans[-1][0], max(spans[-1][1], end))
        else:
            # комментарии/шапка файла перед первым узлом — в отдельное окно
            if not spans and start > 1:
                spans.append((1, start - 1))
            spans.append((start, end))

    if not spans:
        spans = [(1, len(lines))]

    # Раздувшиеся узлы режем окнами
    result: list[tuple[int, int]] = []
    for a, b in spans:
        block_len = sum(len(lines[i - 1]) + 1 for i in range(a, b + 1))
        if block_len > max_chars:
            result.extend(_window_spans(lines, a, b, max_chars, overlap))
        else:
            result.append((a, b))
    return result


def _markdown_spans(source: str, max_chars: int, overlap: int) -> list[tuple[int, int]]:
    """Границы чанков Markdown: разрез по заголовкам (секция = чанк)."""
    lines = source.splitlines()
    if not lines:
        return []
    starts = [i for i, line in enumerate(lines, start=1) if line.startswith("#")]
    if not starts:
        return _window_spans(lines, 1, len(lines), max_chars, overlap)

    spans: list[tuple[int, int]] = []
    if starts[0] > 1:
        spans.append((1, starts[0] - 1))
    for idx, s in enumerate(starts):
        e = (starts[idx + 1] - 1) if idx + 1 < len(starts) else len(lines)
        spans.append((s, e))

    result: list[tuple[int, int]] = []
    for a, b in spans:
        block_len = sum(len(lines[i - 1]) + 1 for i in range(a, b + 1))
        if block_len > max_chars:
            result.extend(_window_spans(lines, a, b, max_chars, overlap))
        else:
            result.append((a, b))
    return result


# ---------------------------------------------------------------------------
# Публичное API
# ---------------------------------------------------------------------------

def chunk_text(
    path: Path,
    root: Path,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Нарезать файл на чанки (пустой список — для бинарных/пустых файлов)."""
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    if not source.strip() or len(source) > MAX_FILE_CHARS:
        return []

    rel = path.relative_to(root).as_posix()
    ext = path.suffix.lower()
    language = ext.lstrip(".") or "txt"

    if ext in CODE_EXTS:
        spans, kind = _python_spans(source, max_chars, overlap), "code"
    elif ext in DOC_EXTS:
        spans = _markdown_spans(source, max_chars, overlap) if ext in {".md", ".rst"} \
            else _window_spans(source.splitlines(), 1, len(source.splitlines()), max_chars, overlap)
        kind = "doc"
    else:
        spans, kind = _window_spans(source.splitlines(), 1, len(source.splitlines()), max_chars, overlap), "doc"

    lines = source.splitlines()
    chunks: list[Chunk] = []
    for a, b in spans:
        text = "\n".join(lines[a - 1 : b]).strip()
        if not text:
            continue
        chunks.append(
            Chunk(
                chunk_id=f"{rel}:{a}-{b}",
                path=rel,
                start_line=a,
                end_line=b,
                text=text,
                language=language,
                kind=kind,
            )
        )
    return chunks


def iter_source_files(root: Path, exts: set[str] | None = None) -> list[Path]:
    """Собрать файлы для индексации, пропуская служебные каталоги."""
    exts = exts or (CODE_EXTS | DOC_EXTS)
    result: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in exts:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        result.append(path)
    return result


def chunk_tree(
    root: Path,
    *,
    exts: set[str] | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Проиндексировать всё дерево: файлы -> чанки (согласованный порядок)."""
    chunks: list[Chunk] = []
    for path in iter_source_files(root, exts):
        chunks.extend(chunk_text(path, root, max_chars=max_chars, overlap=overlap))
    return chunks
