# AGENTS.md

Course monorepo: three independent Python FastAPI projects. No root package, no CI, no pre-commit, no repo-wide lint/typecheck. Python 3.12; `uv` 0.12 at `~/.local/bin/uv`.

## Layout

| Path | What it is | Env tooling |
|---|---|---|
| `Module1/Case1_CRUDs/tickets_project` | Sync FastAPI tickets CRUD, SQLite (`support.db`), pip/venv | `.venv/` + `pytest.ini` |
| `Module1/Case1_CRUDs/async_tickets_project` | Async scaffold only (no venv, no tests) | `requirements.txt` |
| `Module2_agents_md` | In-memory cars API (`src/main.py` + `src/cars.json`) | uv project |
| `Module2_subagents/async_tickets_project` | Async tickets API: rate limit + Redis cache + service layer | uv project |
| `Module2_subagents/.opencode/agents/` | Subagent definitions (`rate_limiter`, `service_architect`, `cache_manager`) | — |

Run every command from its project directory (each has its own venv/lockfile).

## Commands (verified)

**Module1 sync tickets** — `cd Module1/Case1_CRUDs/tickets_project`
```bash
.venv/bin/pytest tests/ -q                          # 7 passed
.venv/bin/pytest tests/test_tickets.py::test_health_endpoint -q   # single test
.venv/bin/uvicorn app.main:app --reload             # port 8000
```
No Postgres needed (SQLite default). Reinstall: `python -m pip install -r requirements-dev.txt`.

**Module2 cars API** — `cd Module2_agents_md` (cwd **must** be this dir; `src/main.py` reads `Path("src/cars.json")` and imports `src.*`)
```bash
uv run python -c "from src.main import app"         # import check (no tests, no ruff here)
uv run uvicorn src.main:app --reload                # port 8000
```
State is in-memory only — create/delete do not write `cars.json`.

**Module2 async tickets** — `cd Module2_subagents/async_tickets_project`
```bash
uv run pytest -q                                    # 10 passed
uv run pytest tests/test_api.py::test_create_get_update_delete_flow -q   # single test
uv run ruff check app tests                         # only ruff config in repo (line-length 100, E/F/I/W/UP)
uv run ruff format --check app tests
uv run uvicorn app.main:app --reload
```
Tests need no services: aiosqlite in `tmp_path`, `limiter.enabled = False` in `tests/conftest.py`.

## Gotchas (would bite without warning)

- **Renamed dir broke venv shebangs.** `Module2` → `Module2_subagents` left `.venv/bin/{pytest,uvicorn,pip,...}` pointing at the old absolute path → `error: Failed to spawn: pytest`. If that appears: `uv pip install --reinstall pytest uvicorn` or use `uv run python -m pytest -q`.
- **Redis is not running** (6379 refused). App still works: `FallbackLimiter(swallow_errors=True)` and fastapi-cache2 log warnings and fall through; POST limit (5/min) and cache are effectively off. PostgreSQL **is** up: `postgresql+psycopg://userdb:userdb@127.0.0.1:5432/exampledb` (default `DATABASE_URL` in `app/database.py`).
- **Dead LLM provider**: `Module2_subagents/opencode.json` defines `example` → `http://localhost:8080` (never up). Never use `example/GigaChat-2`. Subagent models in use: `opencode/mimo-v2.6-flash-free`, `opencode/big-pickle`.
- **Subagent frontmatter tools must be exactly** `read`, `write`, `edit`, `bash`, `glob`, `grep` (not `read_file`/`run_command`). Do not add `task`/`todowrite` (denied for subagents).
- **`M2_AGENTS.md` is stale**: paths still say `Module2/...`, claims "uv/ruff not installed". Trust this file + code over it. Detailed subagent history lives there; reconcile paths when using it.
- **Decorator order in `app/routers/tickets.py`**: `@router` → `@limiter.limit` → `@cache` (cache inside limiter). `list_tickets` must return `model_dump(mode="json")` dicts — fastapi-cache2's JsonCoder cannot serialize ORM objects.
- **Service layer owns cache invalidation**: routers never call `crud` directly, only `TicketService` (`app/services/tickets.py`); `_invalidate_tickets_list_cache()` runs after create/update/delete.
- **`Module1/.../scaffold.py` and `async_scaffold.py`** regenerate whole project trees — do not run casually (overwrites).
- No typechecker (no mypy/pyright config) anywhere.

## Git

- Short English subjects: `Add ...`, `Fix ...`.
- Stage explicit paths only (`git add <paths>`); `git status` first.
- Tracked but churn-prone: `support.db`, `example.db` (data files) — avoid committing incidental changes.
- `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.opencode/node_modules/` are gitignored.

## Other instruction sources

- `Module1/M1_README.md` — Module1 run/test steps (still accurate).
- `Module2_subagents/M2_AGENTS.md` — subagent rules, known failure modes, recommendations status (paths stale).
- `Module2_subagents/subagent_promts.md` — original subagent prompt texts.
- `Module2_subagents/recommendations.md` — backlog: metrics, horizontal scaling, optimistic locking still unimplemented.
