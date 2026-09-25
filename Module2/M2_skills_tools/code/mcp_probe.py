"""Проверка MCP-сервера лаборатории: подключиться, вывести инструменты, вызвать grep.

Запуск (после `uvicorn mcp_server:app --port 8000`):

    python mcp_probe.py

Студент должен увидеть: список из трёх инструментов и результат вызова
grep_search по sample_project — значит opencode увидит те же инструменты
после `opencode mcp add labtools --url http://localhost:8000/mcp`.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))

MCP_URL = "http://127.0.0.1:8000/mcp"


async def main() -> int:
    # mcp SDK 2.x: клиентские классы остались в mcp.client.*
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    try:
        # v2 SDK: клиент отдаёт кортеж (read_stream, write_stream)
        async with streamable_http_client(MCP_URL) as (read, write), \
                ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"инструменты на сервере: {[t.name for t in tools.tools]}")

            result = await session.call_tool(
                "grep_search",
                {"pattern": "TODO", "path": "lab_2_6_tools/sample_project"},
            )
            text = "".join(
                c.text for c in result.content if hasattr(c, "text")
            )
            print(f"grep_search(TODO -> sample_project):\n{text}")
            err = "ошибка" if getattr(result, "isError", False) else "ok"
            print(f"статус вызова: {err}")
            return 0 if err == "ok" and "TODO" in text else 1
    except Exception as exc:  # noqa: BLE001 — демонстрационный probe
        def walk(err: BaseException, depth: int = 0) -> None:
            """ExceptionGroup может прятать причину на несколько уровней вглубь."""
            print("  " * depth + f"{type(err).__name__}: {err}", file=sys.stderr)
            for sub in getattr(err, "exceptions", ()) or ():
                walk(sub, depth + 1)

        print("MCP handshake не прошёл:", file=sys.stderr)
        walk(exc)
        print("поднимите: uvicorn mcp_server:app --port 8000", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
