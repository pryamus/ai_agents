"""Тесты реестра инструментов и вызова их из агента (тема 2.6).

Запуск: python -m pytest lab_2_6_tools -q  (из каталога code/)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
_CODE_ROOT = LAB.parent
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))
_LAB_2_5 = _CODE_ROOT / "lab_2_5_loop"
if str(_LAB_2_5) not in sys.path:
    sys.path.insert(0, str(_LAB_2_5))  # AgentLoop/ToolError живут в лабораторной 2.5

from agent import AgentLoop, JsonlLogger, ToolError, build_system_prompt
from tool_impls import default_registry, git_diff, grep_search, ruff_lint
from tool_registry import build_args_model, tool

from shared.llm import ScriptedLLM

# ---------------------------------------------------------------------------
# Схема и валидация аргументов
# ---------------------------------------------------------------------------

def test_schema_built_from_signature():
    spec = default_registry().schema_list()
    by_name = {s["name"]: s for s in spec}
    assert set(by_name) == {"grep_search", "git_diff", "ruff_lint"}

    grep_schema = by_name["grep_search"]["params"]
    assert "pattern" in grep_schema["required"], "pattern обязателен — он без default"
    assert "path" not in grep_schema.get("required", []), "path имеет default"
    assert by_name["grep_search"]["description"], "описание обязательно для LLM"
    # типы взяты из аннотаций
    assert grep_schema["properties"]["use_regex"]["type"] == "boolean"
    assert grep_schema["properties"]["max_results"]["type"] == "integer"


def test_param_docs_parsed_from_docstring():
    model = build_args_model(grep_search)
    props = model.model_json_schema()["properties"]
    assert "что искать" in props["pattern"].get("description", "")


def test_dispatch_rejects_bad_args():
    registry = default_registry()
    with pytest.raises(ToolError) as exc:
        registry.dispatch("grep_search", {})          # нет обязательного pattern
    assert exc.value.code == "invalid_args"

    with pytest.raises(ToolError) as exc:
        registry.dispatch("grep_search",
                          {"pattern": "x", "hacked": True})  # extra="forbid"
    assert exc.value.code == "invalid_args"

    with pytest.raises(ToolError) as exc:
        registry.dispatch("no_such_tool", {})
    assert exc.value.code == "unknown_tool"


def test_custom_tool_timeout_is_retryable(tmp_path: Path):
    @tool(timeout=0.2)
    def slow() -> str:
        """Спит дольше таймаута."""
        import time

        time.sleep(1.0)
        return "никогда"

    from tool_registry import ToolRegistry

    registry = ToolRegistry()
    registry.register(slow)
    with pytest.raises(ToolError) as exc:
        registry.dispatch("slow", {})
    assert exc.value.code == "timeout" and exc.value.retryable


def test_path_traversal_blocked(tmp_path: Path):
    inner = tmp_path / "inner"
    inner.mkdir()
    registry = default_registry(root=inner)
    with pytest.raises(ToolError) as exc:
        registry.dispatch("grep_search", {"pattern": "x", "path": str(tmp_path)})
    assert exc.value.code == "permission"


# ---------------------------------------------------------------------------
# Реальные инструменты: grep, git, ruff
# ---------------------------------------------------------------------------

def test_grep_search_finds_and_limits(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1  # NOTE: first\ny = 2\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("NOTE: md тоже попадёт при include=*\n", encoding="utf-8")

    out = grep_search("NOTE", path=str(tmp_path))
    assert "a.py:1" in out and "b.md" not in out          # include="*.py" по умолчанию

    out_md = grep_search("NOTE", path=str(tmp_path), include="*.md")
    assert "b.md:1" in out_md

    out_re = grep_search(r"NOTE: \w+", path=str(tmp_path), use_regex=True)
    assert "NOTE: first" in out_re

    with pytest.raises(ToolError) as exc:
        grep_search("NOTE", path=str(tmp_path / "nope"))
    assert exc.value.code == "invalid_args"


def _init_repo(path: Path) -> None:
    """Инициализировать git-репозиторий с одним коммитом."""
    def git(*args: str) -> None:
        subprocess.run(
            ["git", *args], cwd=path, check=True, capture_output=True,
            encoding="utf-8", errors="replace",
        )

    (path / "app.py").write_text("value = 1\n", encoding="utf-8")
    git("init", "-q")
    git("add", ".")
    git("-c", "user.email=lab@example.com", "-c", "user.name=lab",
        "commit", "-q", "-m", "init")


def test_git_diff_unstaged_staged_and_empty(tmp_path: Path):
    _init_repo(tmp_path)

    # правка рабочего дерева -> unstaged diff
    (tmp_path / "app.py").write_text("value = 2\n", encoding="utf-8")
    out = git_diff(path=str(tmp_path))
    assert "-value = 1" in out and "+value = 2" in out

    # git add -> staged diff
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    staged = git_diff(path=str(tmp_path), staged=True)
    assert "+value = 2" in staged

    # рабочее дерево чистое -> пустой diff валидно сообщает об этом
    working = git_diff(path=str(tmp_path))
    assert "изменений нет" in working


def test_git_diff_non_repo_is_runtime_error(tmp_path: Path):
    with pytest.raises(ToolError) as exc:
        git_diff(path=str(tmp_path))
    assert exc.value.code == "runtime"  # не ретраится: причина детерминирована


def test_ruff_lint_reports_violations_and_clean_file(tmp_path: Path):
    bad = tmp_path / "bad.py"
    bad.write_text("import os  # unused -> F401\n", encoding="utf-8")
    out = ruff_lint(path=str(bad))
    assert out.startswith("Ruff: замечаний") and "F401" in out

    good = tmp_path / "good.py"
    good.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    assert ruff_lint(path=str(good)) == "Ruff: замечаний нет"


# ---------------------------------------------------------------------------
# Полный цикл: агент вызывает инструменты
# ---------------------------------------------------------------------------

def test_agent_uses_registry_end_to_end(tmp_path: Path):
    (tmp_path / "code.py").write_text("# TODO: дописать\n", encoding="utf-8")
    registry = default_registry(root=tmp_path)

    llm = ScriptedLLM(responses=[
        ('{"thought": "поищу", "action": "tool", "tool": "grep_search", '
         '"args": {"pattern": "TODO", "path": "."}}'),
        '{"thought": "готово", "action": "final", "answer": "найден TODO в code.py"}',
    ])
    logger = JsonlLogger()
    loop = AgentLoop(llm, registry, system_prompt=build_system_prompt(registry),
                     max_steps=5, logger=logger)
    result = loop.run("найди TODO")

    assert result.ok and "code.py" in result.answer
    tool_result = next(r for r in logger.records if r["event"] == "tool_result")
    assert tool_result["tool"] == "grep_search" and tool_result["took_ms"] >= 0


def test_system_prompt_mentions_all_tools():
    prompt = build_system_prompt(default_registry())
    for name in ("grep_search", "git_diff", "ruff_lint"):
        assert name in prompt
