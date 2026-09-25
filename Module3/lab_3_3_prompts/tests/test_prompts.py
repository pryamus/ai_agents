"""Тесты шаблонов промптов (тема 3.3).

Запуск: python -m pytest lab_3_3_prompts -q  (из каталога code/)
"""

from __future__ import annotations

import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))

from lint import lint_prompt
from render import main as render_main
from templates import PromptError, RenderedPrompt, render


def test_codegen_renders_all_parts():
    rendered = render("codegen", func_name="parity", spec="чётность числа")
    assert "parity" in rendered.user and "чётность" in rendered.user
    assert "аннотации типов" in rendered.user  # ограничения подставились
    assert "Пример:" in rendered.user or "пример" in rendered.user.casefold()
    assert rendered.tokens_approx > 0


def test_missing_and_extra_variables_rejected():
    try:
        render("codegen", func_name="f")
    except PromptError as exc:
        assert "spec" in str(exc)
    else:
        raise AssertionError("нет переменной — должна быть ошибка")
    try:
        render("codegen", func_name="f", spec="s", hacked="1")
    except PromptError as exc:
        assert "hacked" in str(exc)
    else:
        raise AssertionError("лишняя переменная — должна быть ошибка")


def test_unknown_template():
    try:
        render("nope", x="1")
    except PromptError as exc:
        assert "codegen" in str(exc)  # подсказка доступных
    else:
        raise AssertionError("нет шаблона — должна быть ошибка")


def test_budget_enforced():
    try:
        render("explain", audience="школьник", source="x = 1\n" * 5000)
    except PromptError as exc:
        assert "бюджет" in str(exc)
    else:
        raise AssertionError("переполнение бюджета — должна быть ошибка")


def test_lint_catches_missing_role_and_format():
    bad = RenderedPrompt(system="  ", user="сделай что-нибудь", tokens_approx=10)
    codes = {f.code for f in lint_prompt(bad)}
    assert {"no-role", "no-format"} <= codes


def test_lint_catches_vague_verb_and_budget():
    rendered = render("explain", audience="студент", source="x = 1")
    assert lint_prompt(rendered) == []  # хороший шаблон — чистый
    over = RenderedPrompt(system="роль", user="ответь списком", tokens_approx=99999)
    assert "over-budget" in {f.code for f in lint_prompt(over, max_tokens=100)}


def test_cli_roundtrip_and_errors(tmp_path: Path, capsys):
    assert render_main(["--template", "codegen", "--set", "func_name=f",
                        "--set", "spec=s", "--lint"]) == 0
    assert "`f`" in capsys.readouterr().out  # подставилось имя, а не пример
    assert render_main(["--template", "codegen", "--set", "func_name=f"]) == 2
    assert render_main(["--template", "codegen", "--set", "oops"]) == 2
    src = tmp_path / "s.py"
    src.write_text("x = 1\n", encoding="utf-8")
    assert render_main(["--template", "explain", "--set", "audience=все",
                        "--set", f"source=@{src}", "--lint"]) == 0
