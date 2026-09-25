"""MCP-сервер: открыть те же инструменты opencode через Streamable HTTP (бонус 2.6).

opencode подключает внешние инструменты по MCP (Model Context Protocol) —
стандартный способ «дать агенту новые tools» без модификации рантайма:

    uvicorn mcp_server:app --port 8000            # поднять сервер
    opencode mcp add labtools --url http://localhost:8000/mcp   # подключить
    opencode run --agent build "найди TODO через labtools_grep_search"

Инструменты — те же функции и тот же ToolRegistry, что и в цикле агента:
схему для MCP берём из сигнатуры, а каждый вызов проходит через реестр
(валидация, таймаут, защита путей действуют и через протокол).
"""

from __future__ import annotations

import functools
import inspect
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))
_CODE_ROOT = LAB.parent
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))

from mcp.server.mcpserver import MCPServer
from tool_impls import default_registry, git_diff, grep_search, ruff_lint
from tool_registry import ToolError  # реестр сам добавляет lab_2_5 в sys.path

# Тот же реестр — источник описаний И единая точка валидации для MCP-вызовов
_registry = default_registry(root=_CODE_ROOT)
_DESCRIPTIONS = {s["name"]: s["description"] for s in _registry.schema_list()}


def _via_registry(name: str, fn):
    """Обёртка для MCP: схема берётся из сигнатуры (functools.wraps),
    но вызов идёт через ToolRegistry.dispatch — валидация аргументов, таймаут
    и привязка путей к корню действуют и через протокол, а не только внутри
    цикла агента.
    """
    signature = inspect.signature(fn)

    @functools.wraps(fn)
    def wrapper(*args: object, **kwargs: object) -> str:
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        try:
            return _registry.dispatch(name, dict(bound.arguments))
        except ToolError as exc:
            # Ошибка инструмента — данные для модели: отдаём код и причину текстом
            return f"ИНСТРУМЕНТ НЕ ВЫПОЛНЕН [{exc.code}]: {exc}"

    return wrapper


server = MCPServer(name="lab26-tools",
                   description="Инструменты лаборатории 2.6: grep, git diff, ruff")

server.tool(name="grep_search", description=_DESCRIPTIONS["grep_search"])(
    _via_registry("grep_search", grep_search))
server.tool(name="git_diff", description=_DESCRIPTIONS["git_diff"])(
    _via_registry("git_diff", git_diff))
server.tool(name="ruff_lint", description=_DESCRIPTIONS["ruff_lint"])(
    _via_registry("ruff_lint", ruff_lint))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # session_manager должен жить вместе с приложением (Streamable HTTP)
    async with server.session_manager.run():
        yield


app = FastAPI(title="lab 2.6 MCP tools", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "tools": ["grep_search", "git_diff", "ruff_lint"]}


# child-app сам содержит маршрут /mcp -> монтируем в корень, чтобы итоговый
# путь был http://host:8000/mcp (health регистрируем ДО mount, иначе его
# перехватит catch-all Mount)
app.mount("/", server.streamable_http_app())
