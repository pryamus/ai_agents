"""Тесты связки IDE+агент+инструменты (тема 3.2).

Запуск: python -m pytest lab_3_2_ide -q  (из каталога code/)
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))

from doctor import check_binary, run_doctor
from doctor import main as doctor_main
from ide import main as ide_main
from ide import render_vscode, validate_vscode


def test_doctor_structure_and_required_flags():
    checks = run_doctor()
    by_name = {c.name: c for c in checks}
    assert {"python", "pytest", "ruff", "git", "opencode"} <= set(by_name)
    assert by_name["python"].ok  # тесты идут на рабочем интерпретаторе
    assert by_name["pytest"].ok and by_name["pytest"].required
    assert not by_name["node"].required  # опциональный не роняет итог


def test_missing_binary_reports_hint(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    check = check_binary("ruff", ("--version",), "pip install ruff")
    assert not check.ok and "pip install ruff" in check.hint


def test_doctor_exit_codes(tmp_path: Path, capsys):
    assert doctor_main(["--json"]) in (0, 1)  # зависит от окружения, но не падает
    out = capsys.readouterr().out
    assert json.loads(out)  # валидный JSON со списком проверок
    assert doctor_main(["--md-out", str(tmp_path / "doc.md")]) in (0, 1)
    assert (tmp_path / "doc.md").read_text(encoding="utf-8").startswith("# Doctor")


def test_render_creates_three_valid_jsons(tmp_path: Path):
    paths = render_vscode(tmp_path)
    assert set(paths) == {"settings.json", "tasks.json", "extensions.json"}
    for path in paths.values():
        assert json.loads(path.read_text(encoding="utf-8"))  # парсится
    assert validate_vscode(tmp_path) == []


def test_check_catches_broken_and_missing(tmp_path: Path):
    assert "settings.json" in validate_vscode(tmp_path)[0]  # пустой каталог
    render_vscode(tmp_path)
    (tmp_path / ".vscode" / "tasks.json").write_text("{битый", encoding="utf-8")
    problems = validate_vscode(tmp_path)
    assert any("битый JSON" in p for p in problems)


def test_check_requires_pytest_and_ruff_tasks(tmp_path: Path):
    render_vscode(tmp_path)
    tasks_path = tmp_path / ".vscode" / "tasks.json"
    data = json.loads(tasks_path.read_text(encoding="utf-8"))
    data["tasks"] = [t for t in data["tasks"] if t["label"] != "ruff"]
    tasks_path.write_text(json.dumps(data), encoding="utf-8")
    assert any("ruff" in p for p in validate_vscode(tmp_path))


def test_ide_cli_roundtrip(tmp_path: Path):
    assert ide_main(["init", "--dir", str(tmp_path)]) == 0
    assert ide_main(["check", "--dir", str(tmp_path)]) == 0
    assert ide_main(["check", "--dir", str(tmp_path / "empty")]) == 1
