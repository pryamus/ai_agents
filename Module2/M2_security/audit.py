"""Аудит действий агентов: JSONL-журнал с хэш-цепочкой (тема 2.10).

Каждая запись связывается с предыдущей через sha256: удаление или правка
строки в середине журнала ломает цепочку — `verify()` находит место разрыва.
Это tamper-evident (следы видны), а не tamper-proof (подделать нельзя):
защита от «тихого» редактирования, а не от взлома хранилища.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AuditRecord:
    seq: int
    ts: float
    actor: str
    role: str
    action: str
    resource: str
    decision: str          # allow | deny
    rule_id: str | None
    reason: str
    prev: str              # хэш предыдущей записи (GENESIS у первой)
    hash: str              # хэш этой записи

    @staticmethod
    def digest(seq: int, ts: float, actor: str, role: str, action: str,
               resource: str, decision: str, rule_id: str | None,
               reason: str, prev: str) -> str:
        body = json.dumps(
            [seq, ts, actor, role, action, resource, decision, rule_id, reason, prev],
            ensure_ascii=False,
        )
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.records: list[AuditRecord] = []
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.records.append(AuditRecord(**json.loads(line)))

    def append(self, *, actor: str, role: str, action: str, resource: str,
               decision: str, rule_id: str | None, reason: str) -> AuditRecord:
        prev = self.records[-1].hash if self.records else "GENESIS"
        record = AuditRecord(
            seq=len(self.records),
            ts=time.time(),
            actor=actor,
            role=role,
            action=action,
            resource=resource,
            decision=decision,
            rule_id=rule_id,
            reason=reason,
            prev=prev,
            hash="",
        )
        record.hash = AuditRecord.digest(
            record.seq, record.ts, actor, role, action, resource,
            decision, rule_id, reason, prev,
        )
        self.records.append(record)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        return record

    def verify(self) -> tuple[bool, int | None]:
        """Проверить цепочку. Возвращает (ok, seq первой битой записи)."""
        prev = "GENESIS"
        for record in self.records:
            if record.prev != prev:
                return False, record.seq
            expected = AuditRecord.digest(
                record.seq, record.ts, record.actor, record.role, record.action,
                record.resource, record.decision, record.rule_id, record.reason,
                record.prev,
            )
            if record.hash != expected:
                return False, record.seq
            prev = record.hash
        return True, None

    def summarize(self) -> dict:
        """Сводка для разбора инцидента: кто, что и по какому правилу отклонено."""
        allowed = sum(1 for r in self.records if r.decision == "allow")
        denied = [r for r in self.records if r.decision == "deny"]
        by_actor: dict[str, int] = {}
        for record in denied:
            by_actor[record.actor] = by_actor.get(record.actor, 0) + 1
        return {
            "allowed": allowed,
            "denied": len(denied),
            "denied_by_actor": by_actor,
            "denied_details": [
                f"{r.actor} [{r.role}] {r.action} {r.resource} ({r.rule_id})"
                for r in denied
            ],
        }
