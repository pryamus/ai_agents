"""Симуляция инцидента: агент пытается выйти за полномочия (тема 2.10).

Сценарий прогоняет 10 попыток через RBAC-движок, каждую пишет в аудит-журнал
и сверяет факт с ожиданием. Успех = все запреты сработали, все разрешения
не пострадали (least-privilege без ложных срабатываний).

Запуск:  python incident.py [--log logs/audit.jsonl]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))

from audit import AuditLog
from rbac import check, policy_selfcheck

# (actor, role, action, resource, expect_allow, комментарий)
SCENARIO: list[tuple] = [
    ("migrator", "coder", "edit", "lab_2_5_loop/agent.py", True, "свой код править можно"),
    ("migrator", "coder", "read", ".env", False, "секрет закрыт"),
    ("migrator", "coder", "shell", "git push origin main", False, "push — не агенту"),
    ("reviewer", "reader", "edit", "lab_2_3_agents_md/validate.py", False, "ревьюер read-only"),
    ("reviewer", "reader", "read", "lab_2_3_agents_md/validate.py", True, "чтение разрешено"),
    ("operator-1", "operator", "shell", "python -m pytest -q", True, "проверка разрешена"),
    ("operator-1", "operator", "shell", "rm -rf /tmp/cache", False, "разрушительная команда"),
    ("admin-1", "admin", "read", "deploy/token.txt", False, "секреты закрыты даже админу"),
    ("admin-1", "admin", "shell", "git push origin main", False, "main — только через PR"),
    ("unknown-bot", "ghost", "read", "app.py", False, "неизвестная роль"),
]


@dataclass
class IncidentReport:
    matched: int
    total: int
    mismatches: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.matched == self.total


def run_incident(log: AuditLog) -> IncidentReport:
    """Прогнать сценарий, записать аудит, сверить ожидания."""
    report = IncidentReport(matched=0, total=len(SCENARIO))
    for actor, role, action, resource, expect_allow, _note in SCENARIO:
        decision = check(role, action, resource)
        log.append(
            actor=actor, role=role, action=action, resource=resource,
            decision="allow" if decision.allowed else "deny",
            rule_id=decision.rule_id, reason=decision.reason,
        )
        if decision.allowed == expect_allow:
            report.matched += 1
        else:
            report.mismatches.append(
                f"{actor} {action} {resource}: ожидалось "
                f"{'allow' if expect_allow else 'deny'}, получено "
                f"{'allow' if decision.allowed else 'deny'}"
            )
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Симуляция инцидента RBAC (2.10)")
    parser.add_argument("--log", type=Path, default=LAB / "logs" / "audit.jsonl")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.log.parent.mkdir(parents=True, exist_ok=True)

    problems = policy_selfcheck()
    print(f"[policy] самопроверка: {problems or 'нарушений нет'}")

    log = AuditLog(args.log)
    report = run_incident(log)
    print(f"\n[incident] попыток: {report.total}, по ожиданиям: {report.matched}")
    for bad in report.mismatches:
        print(f"  РАСХОЖДЕНИЕ: {bad}")

    summary = log.summarize()
    print(f"\n[audit] allow={summary['allowed']} deny={summary['denied']}")
    for line in summary["denied_details"]:
        print(f"  DENY {line}")
    ok, bad_seq = log.verify()
    print(f"[audit] цепочка цела: {ok}" + ("" if ok else f" (разрыв на seq={bad_seq})"))
    print(f"[audit] журнал: {args.log}")
    print("\nИТОГ:", "все запреты сработали, разрешения не пострадали"
          if report.ok and ok else "ЕСТЬ ПРОБЛЕМЫ")
    return 0 if report.ok and ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
