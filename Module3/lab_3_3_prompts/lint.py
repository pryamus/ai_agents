"""Линтер промптов: структурные проверки до отправки модели (тема 3.3).

Ловит дешёвые дефекты, которые дорого стоят в ответе: нет роли, нет формата
ответа, нет ограничений, расплывчатые глаголы без критериев, превышение
бюджета. Эвристики помечены как эвристики — линтер советует, решает человек.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))

from templates import RenderedPrompt

FORMAT_MARKERS = ("формат", "структура", "json", "таблица", "список", "diff-план", "```")
VAGUE_VERBS = ("улучши", "почини", "исправь", "доделай", "разберись", "оптимизируй")


@dataclass
class LintFinding:
    code: str      # no-role | no-format | no-constraints-hint | vague-verb | over-budget
    message: str


def lint_prompt(rendered: RenderedPrompt, *, max_tokens: int = 4000) -> list[LintFinding]:
    """Проверить отрендеренный промпт. Пусто = замечаний нет."""
    findings: list[LintFinding] = []
    if not rendered.system.strip():
        findings.append(LintFinding("no-role", "пустой system: у модели нет роли"))
    blob = (rendered.system + "\n" + rendered.user).casefold()
    if not any(marker in blob for marker in FORMAT_MARKERS):
        findings.append(LintFinding(
            "no-format", "не задан формат ответа (JSON/таблица/структура/список)"))
    for verb in VAGUE_VERBS:
        if re.search(rf"\b{re.escape(verb)}\b", blob):
            findings.append(LintFinding(
                "vague-verb",
                f"расплывчатый глагол {verb!r} без критериев готовности"))
            break
    if rendered.tokens_approx > max_tokens:
        findings.append(LintFinding(
            "over-budget",
            f"~{rendered.tokens_approx} токенов при бюджете {max_tokens}"))
    return findings
