"""RBAC для агентов: роли, deny-override, самопроверка политики (тема 2.10).

Модель та же, что у permissions в opencode (тема 2.3), но переносимая:
роль — именованный набор правил {effect, actions, resources}.

- Ресурсы матчится glob'ами (`fnmatch`) по нормализованному пути ИЛИ
  по basename — `*.env` ловит и `.env`, и `deploy/.env`.
- Порядок решения: сначала ищется совпавший **deny** (deny-override),
  потом совпавший **allow**, иначе — default deny.
- `policy_selfcheck()` ищет слишком широкие allow'ы: политика должна сама
  доказывать, что в ней нет `allow` на `shell: *` или чтение секретов.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Literal

Effect = Literal["allow", "deny"]


@dataclass(frozen=True)
class Rule:
    id: str
    effect: Effect
    actions: tuple[str, ...]      # glob'ы действий: read, edit, shell, ...
    resources: tuple[str, ...]    # glob'ы ресурсов: пути или команды
    reason: str = ""


@dataclass(frozen=True)
class Decision:
    allowed: bool
    rule_id: str | None
    reason: str


SECRET_PROBES = (".env", "prod.env", "api_token.txt", "secrets.yaml", "deploy/.env")


def _norm(resource: str) -> str:
    return resource.replace("\\", "/")


def _matches(patterns: tuple[str, ...], value: str) -> bool:
    """Совпадение с полным значением или с basename (для `*.env` в подкаталогах)."""
    text = _norm(value)
    base = text.rsplit("/", 1)[-1]
    return any(
        fnmatch.fnmatchcase(text, pattern) or fnmatch.fnmatchcase(base, pattern)
        for pattern in patterns
    )


def _rule_matches(rule: Rule, action: str, resource: str) -> bool:
    return _matches(rule.actions, action) and _matches(rule.resources, resource)


def _read_set(*exts: str) -> tuple[str, ...]:
    return tuple(f"*{ext}" for ext in exts)


_CODE_EXTS = _read_set(".py", ".md", ".txt", ".json", ".jsonc", ".yaml", ".yml", ".toml")
_SECRET_GLOBS = ("*.env", "*.env.*", "*token*", "*secret*", "*passwd*")


def _deny_secrets(prefix: str) -> Rule:
    return Rule(f"{prefix}.no-secrets", "deny", ("read",), _SECRET_GLOBS,
                "секреты не читает никто, включая админа")


ROLES: dict[str, tuple[Rule, ...]] = {
    "reader": (
        Rule("reader.read-docs", "allow", ("read",), _CODE_EXTS, "чтение кода и доков"),
        _deny_secrets("reader"),
        Rule("reader.no-edit", "deny", ("edit",), ("*",), "ревьюер только читает"),
        Rule("reader.no-shell", "deny", ("shell",), ("*",), "команды запрещены"),
    ),
    "coder": (
        Rule("coder.read-docs", "allow", ("read",), _CODE_EXTS, "чтение кода и доков"),
        _deny_secrets("coder"),
        Rule("coder.edit-code", "allow", ("edit",), _CODE_EXTS, "правка кода и доков"),
        Rule("coder.no-fixtures", "deny", ("edit",), ("fixtures/**",),
             "фикстуры правит только человек"),
        Rule("coder.no-push", "deny", ("shell",), ("git push*",),
             "push — отдельное решение человека"),
        Rule("coder.no-destroy", "deny", ("shell",), ("rm -rf*", "*sudo*"),
             "разрушительные команды запрещены"),
    ),
    "operator": (
        Rule("operator.read-docs", "allow", ("read",), _CODE_EXTS, "чтение кода и доков"),
        _deny_secrets("operator"),
        Rule("operator.edit-code", "allow", ("edit",), _CODE_EXTS, "правка кода и доков"),
        Rule("operator.no-fixtures", "deny", ("edit",), ("fixtures/**",),
             "фикстуры правит только человек"),
        Rule("operator.run-checks", "allow", ("shell",),
             ("python -m pytest*", "python validate.py", "ruff*",
              "git status*", "git diff*", "git log*"),
             "точечные разрешения на проверки"),
        Rule("operator.no-push", "deny", ("shell",), ("git push*",),
             "push — отдельное решение человека"),
        Rule("operator.no-destroy", "deny", ("shell",), ("rm -rf*", "*sudo*"),
             "разрушительные команды запрещены"),
    ),
    "admin": (
        Rule("admin.all", "allow", ("*",), ("*",), "полный доступ"),
        _deny_secrets("admin"),
        Rule("admin.no-push-main", "deny", ("shell",), ("git push*main*",),
             "push в main закрыт даже админу — только через PR"),
    ),
}


def check(role: str, action: str, resource: str,
          *, roles: dict[str, tuple[Rule, ...]] = ROLES) -> Decision:
    """Проверить действие. Неизвестная роль и отсутствие правил — запрет."""
    rules = roles.get(role)
    if rules is None:
        return Decision(False, None, f"неизвестная роль {role!r}")
    for rule in rules:
        if rule.effect == "deny" and _rule_matches(rule, action, resource):
            return Decision(False, rule.id, rule.reason)
    for rule in rules:
        if rule.effect == "allow" and _rule_matches(rule, action, resource):
            return Decision(True, rule.id, rule.reason)
    return Decision(False, None, "default deny: правило не найдено")


def policy_selfcheck(
    roles: dict[str, tuple[Rule, ...]] = ROLES,
) -> list[str]:
    """Самопроверка политики: вернуть список нарушений least-privilege.

    Принцип: широкий allow сам по себе не нарушение — нарушение это allow
    без компенсирующих deny. Поэтому `admin.all` (allow * при трёх deny)
    чист, а `god.all` без единого deny — нет. Секреты проверяются с учётом
    deny-override: allow на чтение засчитывается, только если ни один deny
    его не перекрывает.
    """
    problems: list[str] = []
    for role_name, rules in roles.items():
        allows = [r for r in rules if r.effect == "allow"]
        denies = [r for r in rules if r.effect == "deny"]
        for rule in allows:
            if "*" in rule.actions and "*" in rule.resources:
                if not denies:
                    problems.append(
                        f"{role_name}/{rule.id}: широкий allow без компенсирующих deny"
                    )
                continue
            for probe in SECRET_PROBES:
                if _rule_matches(rule, "read", probe) and not any(
                    _rule_matches(deny, "read", probe) for deny in denies
                ):
                    problems.append(
                        f"{role_name}/{rule.id}: allow читает секрет {probe!r}"
                    )
                    break
    return problems
