"""Глоссарий предметной области: «онтология-лайт» для обогащения (тема 2.7).

Полноценная онтология — граф сущностей и связей («сервис зависит от базы»,
«эндпоинт принадлежит API»). Здесь — минимальный рабочий слой: термины +
синонимы + определения. Этого достаточно, чтобы снять главную боль retrieval:
пользователь и документы говорят разными словами («откат» vs «rollback»,
«чанк» vs «фрагмент»).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Term:
    term: str                 # каноническое имя
    aliases: list[str] = field(default_factory=list)  # синонимы/англицизмы/формы
    definition: str = ""      # одно-два предложения для подстановки в промпт


class Glossary:
    def __init__(self, terms: list[Term]) -> None:
        self.terms = terms
        self._patterns: list[tuple[Term, re.Pattern]] = []
        for term in terms:
            variants = sorted({term.term, *term.aliases}, key=len, reverse=True)
            pattern = re.compile(
                r"\b(" + "|".join(re.escape(v) for v in variants) + r")\b",
                re.IGNORECASE,
            )
            self._patterns.append((term, pattern))

    @classmethod
    def from_json(cls, path: Path | str) -> Glossary:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([Term(**item) for item in raw["terms"]])

    def lookup(self, text: str) -> list[Term]:
        """Найти термины, упомянутые в тексте (по термину или любому алиасу)."""
        return [term for term, pattern in self._patterns if pattern.search(text)]

    def define(self, term: str) -> str | None:
        """Определение по точному имени или алиасу (case-insensitive)."""
        wanted = term.casefold()
        for item in self.terms:
            if item.term.casefold() == wanted or wanted in {a.casefold() for a in item.aliases}:
                return item.definition
        return None

    def expand(self, query: str) -> str:
        """Блок определений найденных терминов — вставляется в промпт до retrieval."""
        found = self.lookup(query)
        if not found:
            return ""
        lines = ["Термины предметной области:"]
        lines += [f"- {t.term}: {t.definition}" for t in found]
        return "\n".join(lines)
