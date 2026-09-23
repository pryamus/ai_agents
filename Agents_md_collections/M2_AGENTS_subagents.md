# AGENTS.md

Инструкции для агентов (opencode и субагентов) в репозитории `ai_agents`.

## Стек и окружение

| Компонент | Значение |
|---|---|
| Python | 3.12 (системный `/usr/bin/python3`) |
| Проект (Module2) | `Module2/async_tickets_project` |
| venv | `Module2/async_tickets_project/.venv` |
| PostgreSQL | `postgresql+psycopg://userdb:userdb@127.0.0.1:5432/exampledb` |
| Redis | `redis://127.0.0.1:6379/0` (локальный; тесты работают и без него) |
| Тестовая БД | aiosqlite во временной папре (fixture в `tests/conftest.py`) |

**Ограничения окружения:**
- `uv` и `ruff` сейчас **не установлены** (`command not found`). Сначала установить:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # или: pipx install uv / pip install uv ruff
  ```
- Нет sudo/root. Redis/доп. сервисы — только в `/tmp/opencode/` или user-space.
- `Module2/opencode.json` содержит мёртвый провайдер `example` → `http://localhost:8080` (не запущен). **Не использовать** модель `example/GigaChat-2`.
- Рабочие модели субагентов: `opencode/mimo-v2.6-flash-free`, `opencode/big-pickle`.

## Структура (Module2)

```
Module2/
  .opencode/agents/     # определения субагентов (*.md)
  async_tickets_project/
    app/
      main.py           # app, lifespan, limiter, FastAPICache
      routers/tickets.py
      services/tickets.py
      database.py, models.py, schemas.py, crud.py
    tests/              # pytest + aiosqlite, limiter отключён в client
    requirements.txt, requirements-dev.txt, pytest.ini
  recommendations.md    # список задач (не все выполнены)
  subagent_promts.md    # исходные промпты для @rate_limiter и т.д.
```

## Команды (предпочтительные: uv + ruff)

Выполнять из корня проекта, где есть `pyproject.toml`/`uv.lock` (создать при первой миграции на uv) или из `async_tickets_project`.

### Первичная настройка (переход на uv)
```bash
cd Module2/async_tickets_project
uv venv
uv pip install -r requirements-dev.txt
# зафиксировать:
uv pip freeze > requirements.lock.txt   # или перейти на pyproject.toml + uv.lock
```

### Зависимости
```bash
uv pip install -r requirements.txt
uv pip install -r requirements-dev.txt
uv pip install <пакет>
```

### Тесты
```bash
cd Module2/async_tickets_project
uv run pytest -q
# или без uv (фолбэк, пока uv не установлен):
.venv/bin/pytest -q
```

### Линт / формат
```bash
# после установки ruff (uv tool install ruff или uv add --dev ruff)
uv run ruff check .
uv run ruff check --fix .
uv run ruff format .
# фолбэк, если ruff уже в PATH:
ruff check Module2/async_tickets_project/app tests
```

### Запуск приложения
```bash
cd Module2/async_tickets_project
uv run uvicorn app.main:app --reload
# фолбэк: .venv/bin/uvicorn app.main:app --reload
```

### Проверка Redis/PostgreSQL (диагностика)
```bash
# Redis (пример user-space; путь может отличаться)
redis-cli ping          # или путь к redis-cli в /tmp/opencode/...
# PostgreSQL
pg_isready -h 127.0.0.1 -p 5432
```

**Не использовать:** `python -m pip install` как основной путь (переход на uv); `pip install` в системный Python без venv.

## Субагенты

Определения: `Module2/.opencode/agents/*.md`. Вызов через `task(subagent_type: "<name>")` или `@name`.

### Правила вызова
1. Перед вызовом читать `*.md`: **имена tools** должны быть каноничными opencode: `read`, `write`, `edit`, `bash`, `glob`, `grep`. Запрещены `read_file`, `write_file`, `patch_file`, `run_command`.
2. **Не добавлять** `task` / `todowrite` в tools субагента — в metadata сессии они `deny` (дефолт mode=subagent).
3. В prompt субагента явно перечислить **только целевые файлы**; запретить обход `.venv`, несуществующих `app/core`, `app/db`.
4. Запретить повторный обход дерева: сначала `grep`/`read` по списку, потом `edit`.
5. Не использовать мёртвые модели (`example/*`).
6. После правок субагент обязан: `uv run pytest -q` (или `.venv/bin/pytest -q`) и краткий отчёт.

### Субагенты
| Имя | Назначение | Модель |
|---|---|---|
| `rate_limiter` | slowapi + Redis, fallback при падении Redis | `opencode/big-pickle` |
| `service_architect` | вынос CRUD из роутеров в `app/services/` | `opencode/big-pickle` |
| `cache_manager` | fastapi-cache2, инвалидация списка | `opencode/mimo-v2.6-flash-free` |

### Известные ошибки субагентов
| Симптом | Причина | Фикс |
|---|---|---|
| `Task cancelled` / `AbortError` | Модель `example/GigaChat-2` недоступна; либо отмена в UI | Другая модель; не отменять mid-stream |
| Цикл чтения одних и тех же каталогов | Нет `glob`/`grep` в tools; vague prompt; чтение несуществующих путей | Правильные имена tools + белый список файлов в prompt |
| `read_file` не работает | Неверные имена tools во frontmatter | Переименовать в `read`/`write`/`edit`/`bash` |
| ECONNREFUSED :8080 | Провайдер `example` | Удалить/не использовать из `Module2/opencode.json` |

## Ограничения проекта (актуально)

- `recommendations.md`: п.1 (async) — сделано; п.2 (PostgreSQL) — сделано; п.3 (rate limit) — сделано; п.4 (service layer) — сделано; п.5 (кэш) — сделано; **п.6–8 (метрики, масштабирование, конкурентная запись) — не сделаны**.
- Rate limits: 60/min все, 5/min POST /tickets; `FallbackLimiter` + `swallow_errors`.
- Кэш: `GET /tickets` через fastapi-cache2, TTL 30s, ключ `tickets:list:skip=:limit=`, инвалидация в `TicketService` после create/update/delete.
- В `routers/tickets.py` порядок декораторов: `@router` → `@limiter.limit` → `@cache` (внутри limiter).
- `list_tickets` возвращает `model_dump()` (не ORM) — иначе JsonCoder fastapi-cache2 падает.

## Git

- Коммиты короткие, на английском: `Add ...`, `Fix ...`.
- Включать `Module2/recommendations.md` при релевантных изменениях.
- **Не коммитить:** `example.db`, `Module2/opencode.json` (если только не нужен осознанно), `Module2_ultra/`, `.opencode/node_modules/`, `.venv/`, `uv.lock` при желании пользователя.
- stage только осознанные файлы: `git add <paths>`.

## Чек-лист перед коммитом

1. `uv run ruff check Module2/async_tickets_project/app tests` (или `ruff check ...`)
2. `uv run pytest -q` (или `.venv/bin/pytest -q`) → все зелёные
3. `git status` / `git diff` — нет мусора
4. Коммит одной темой
