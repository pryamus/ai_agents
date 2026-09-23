# ai_agents

## Tickets project

Проект с поддержкой тикетов находится в каталоге `Module1/Case1_CRUDs/tickets_project`.

### Запуск проекта

1. Перейдите в каталог проекта:
   ```bash
   cd Module1/Case1_CRUDs/tickets_project
   ```
2. Активируйте виртуальное окружение:
   ```bash
   . .venv/bin/activate
   ```
3. Установите зависимости:
   ```bash
   python -m pip install -r requirements.txt
   ```
   Если нужно установить dev-зависимости, включая pytest:
   ```bash
   python -m pip install -r requirements-dev.txt
   ```
4. Запустите приложение:
   ```bash
   uvicorn app.main:app --reload
   ```
5. Откройте API документацию:
   - Swagger: http://127.0.0.1:8000/docs
   - ReDoc: http://127.0.0.1:8000/redoc

### Запуск тестов

```bash
cd Module1/Case1_CRUDs/tickets_project
. .venv/bin/activate
pytest tests/ -q
```

Или через модуль Python:

```bash
cd Module1/Case1_CRUDs/tickets_project
. .venv/bin/activate
python -m pytest tests/ -q
```

### Важное замечание

Проект по умолчанию использует SQLite локально (`sqlite:///./support.db`), поэтому не требуется отдельный сервер PostgreSQL для локального запуска и тестирования.
