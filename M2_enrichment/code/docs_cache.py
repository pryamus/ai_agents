"""Кэш внешних источников знаний: файлы, тексты, URL (тема 2.7).

Правило темы: агент не ходит в сеть на каждый вопрос. Источник скачивается
один раз (для URL действует TTL), дальше работа идёт с локальным кэшем —
тем же индексным пайплайном, что в лабораторной 2.4.

Сеть — только через инжектированный `fetcher`: в тестах это заглушка,
в проде — HTTP-клиент с таймаутом и ретраями из темы 2.5.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_TTL_SECONDS = 24 * 3600  # сутки: документация меняется не каждую минуту


@dataclass
class DocRecord:
    source: str        # человекопонятный идентификатор: путь, URL, имя
    kind: str          # file | text | url
    sha: str           # sha256 содержимого: дедупликация и контроль свежести
    path: str          # относительный путь копии внутри кэша
    bytes: int
    added_ts: float
    expires_ts: float | None = None  # только для url (TTL)

    @property
    def stale(self) -> bool:
        """Просрочен ли кэш (для url с истёкшим TTL)."""
        return self.expires_ts is not None and time.time() > self.expires_ts


class CacheError(RuntimeError):
    """Источник недоступен: нет сети, нет fetcher'а, битый файл."""


class DocCache:
    """Файловый кэш документов с манифестом и дедупликацией по sha256."""

    def __init__(self, root: Path, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self._manifest_path = root / "manifest.json"
        self._records: dict[str, DocRecord] = {}
        if self._manifest_path.exists():
            raw = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            self._records = {r["source"]: DocRecord(**r) for r in raw.get("docs", [])}

    def _save(self) -> None:
        data = {"docs": [asdict(r) for r in self._records.values()]}
        self._manifest_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    @staticmethod
    def _sha(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def add_text(
        self,
        source: str,
        text: str,
        *,
        kind: str = "text",
        ttl_seconds: int | None = None,
    ) -> DocRecord:
        """Положить текст в кэш. Тот же sha — вернуть существующую запись."""
        sha = self._sha(text)
        existing = self._records.get(source)
        if existing is not None and existing.sha == sha:
            return existing  # дедупликация: контент не изменился
        filename = f"{sha[:12]}.md"
        (self.root / filename).write_text(text, encoding="utf-8")
        record = DocRecord(
            source=source,
            kind=kind,
            sha=sha,
            path=filename,
            bytes=len(text.encode("utf-8")),
            added_ts=time.time(),
            expires_ts=(time.time() + ttl_seconds) if ttl_seconds is not None else None,
        )
        self._records[source] = record
        self._save()
        return record

    def add_file(self, path: Path | str, *, source: str | None = None) -> DocRecord:
        """Закэшировать локальный файл (документация проекта из репозитория)."""
        file_path = Path(path)
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise CacheError(f"не удалось прочитать {file_path}: {exc}") from exc
        return self.add_text(source or str(file_path), text, kind="file")

    def add_url(
        self, url: str, *, fetcher: Callable[[str], str] | None = None
    ) -> DocRecord:
        """Скачать URL в кэш. Без fetcher'а — честная ошибка офлайна."""
        if fetcher is None:
            raise CacheError(
                f"офлайн: для {url} передайте fetcher (см. README лаборатории)"
            )
        try:
            text = fetcher(url)
        except Exception as exc:
            raise CacheError(f"не удалось скачать {url}: {exc}") from exc
        return self.add_text(url, text, kind="url", ttl_seconds=self.ttl_seconds)

    def refresh_file(self, path: Path | str, *, source: str | None = None) -> DocRecord | None:
        """Перечитать файл, если он изменился. None — источника не было в кэше."""
        key = source or str(path)
        if key not in self._records:
            return None
        return self.add_file(path, source=key)

    def list_docs(self) -> list[DocRecord]:
        return list(self._records.values())

    def doc_path(self, record: DocRecord) -> Path:
        return self.root / record.path

    def stale_sources(self) -> list[str]:
        """Источники с истёкшим TTL — кандидаты на повторное скачивание."""
        return [r.source for r in self._records.values() if r.stale]
