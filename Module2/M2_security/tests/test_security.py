"""Тесты RBAC и аудита (тема 2.10): матрица прав, цепочка, инцидент.

Запуск: python -m pytest lab_2_10_security -q  (из каталога code/)
"""

from __future__ import annotations

import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))

from audit import AuditLog
from incident import main as incident_main
from incident import run_incident
from rbac import Rule, check, policy_selfcheck


def test_reader_is_read_only():
    assert check("reader", "read", "docs/guide.md").allowed
    assert check("reader", "read", "src/app.py").allowed
    assert not check("reader", "edit", "src/app.py").allowed
    assert not check("reader", "shell", "python -m pytest -q").allowed


def test_coder_denied_secrets_and_fixtures():
    assert check("coder", "edit", "src/app.py").allowed
    assert not check("coder", "read", ".env").allowed
    assert not check("coder", "read", "deploy/.env").allowed  # basename-матчинг
    assert not check("coder", "read", "api_token.txt").allowed
    assert not check("coder", "edit", "fixtures/bad-mode.md").allowed
    assert not check("coder", "shell", "git push origin main").allowed


def test_operator_allowed_checks_denied_destroy():
    assert check("operator", "shell", "python -m pytest -q").allowed
    assert check("operator", "shell", "ruff check .").allowed
    assert check("operator", "shell", "git diff --stat").allowed
    assert not check("operator", "shell", "rm -rf /tmp/x").allowed
    assert not check("operator", "shell", "git push origin dev").allowed


def test_admin_powerful_but_bounded():
    assert check("admin", "edit", "infra/deploy.sh").allowed
    assert check("admin", "shell", "python -m pytest -q").allowed
    assert not check("admin", "read", "deploy/token.txt").allowed
    assert not check("admin", "shell", "git push origin main").allowed
    assert not check("ghost", "read", "app.py").allowed  # неизвестная роль


def test_selfcheck_flags_broad_policy():
    assert policy_selfcheck() == []  # встроенная политика чистая
    bad = {
        "god": (Rule("god.all", "allow", ("*",), ("*",), "всё можно"),),
    }
    assert policy_selfcheck(bad)  # слишком широкий allow найден


def test_audit_chain_and_tamper_detection(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    log.append(actor="a", role="coder", action="edit", resource="x.py",
               decision="allow", rule_id="coder.edit-code", reason="")
    log.append(actor="b", role="reader", action="edit", resource="x.py",
               decision="deny", rule_id="reader.no-edit", reason="")
    ok, bad = AuditLog(path).verify()  # перечитать с диска
    assert ok and bad is None

    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace('"allow"', '"deny"')  # подмена первой записи
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, bad = AuditLog(path).verify()
    assert not ok and bad == 0


def test_audit_summary(tmp_path: Path):
    log = AuditLog(tmp_path / "a.jsonl")
    log.append(actor="m", role="coder", action="read", resource=".env",
               decision="deny", rule_id="coder.no-secrets", reason="")
    log.append(actor="m", role="coder", action="edit", resource="x.py",
               decision="allow", rule_id="coder.edit-code", reason="")
    summary = log.summarize()
    assert summary["allowed"] == 1 and summary["denied"] == 1
    assert summary["denied_by_actor"] == {"m": 1}
    assert len(summary["denied_details"]) == 1


def test_incident_matches_expectations(tmp_path: Path):
    report = run_incident(AuditLog(tmp_path / "audit.jsonl"))
    assert report.ok and report.matched == report.total == 10
    assert incident_main(["--log", str(tmp_path / "audit2.jsonl")]) == 0
