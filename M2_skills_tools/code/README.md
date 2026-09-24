# Лабораторная 2.6 — Skills и Tools

**Цель:** зарегистрировать инструменты (`git diff`, `grep`, `linter`) с
описанием для LLM и валидацией аргументов, вызвать их из агента; понять
разницу skill ↔ tool; опционально — открыть инструменты через MCP.

## Структура

```
lab_2_6_tools/
├── tool_registry.py     # @tool: JSON Schema из сигнатуры, валидация, таймаут,
│                        # обрезка вывода, защита путей (ToolRegistry = ToolHost)
├── tool_impls.py        # grep_search, git_diff, ruff_lint + default_registry()
├── run_tools_agent.py   # агент (цикл из 2.5) вызывает инструменты: grep -> ruff -> итог
├── sample_project/      # учебный код: есть TODO и F401 для детерминированного демо
├── mcp_server.py        # БОНУС: те же инструменты как MCP-сервер (FastAPI)
├── .opencode/skills/codebase-audit/SKILL.md   # SKILL: процедура аудита
└── tests/test_tools.py
```

## Шаги практики

1. **Посмотреть, что «видит» LLM, и прогнать агента:**

   ```bash
   cd code/lab_2_6_tools
   python run_tools_agent.py --show-schema
   ```

   В выводе: JSON Schema каждого инструмента (сборка из аннотаций и
   docstring), затем события `tool_call`/`tool_result` с `took_ms` и итоговый
   ответ. Демо офлайн (ScriptedLLM); `--live` включает реальный API.

2. **Тесты** (схема, валидация, таймаут, path traversal, git/ruff/grep, e2e):

   ```bash
   python -m pytest -q
   ```

3. **MCP-сервер (бонус) и подключение к opencode:**
   ```bash
   uv add "mcp[cli]"
   ```

   ```bash
   uvicorn mcp_server:app --port 8000                       # терминал 1
   opencode mcp add labtools --url http://localhost:8000/mcp  # терминал 2 (из каталога лаборатории)
   opencode mcp list                                         # labtools: connected
   opencode run "найди TODO в sample_project с labtools_grep_search"
   opencode mcp remove labtools                              # после практики
   ```

   Инструменты у opencode получают имена `<сервер>_<инструмент>`.

4. **Skill:** файл `.opencode/skills/codebase-audit/SKILL.md` — процедура
   аудита. Проверка: `opencode run "используй скилл codebase-audit для
   sample_project"` — модель подгружает инструкцию по `skill` tool, а схемы
   инструментов уже в промпте от рантайма.

5. **(Самостоятельно) Добавить инструмент** `file_stats(path)` — число строк
   и символов в файлах; сравнить: как быстро LLM (в --live) начинает его
   вызывать при удачном/неудачном описании.

## Контрольные вопросы

1. Чем ToolError(invalid_args) отличается от ToolError(timeout) для политики
   ретраев?
2. Почему «найдено 3 замечания линтера» — это успешный результат, а не
   исключение?
3. Что произойдёт при вызове `grep_search` с `path="../.."` и почему?
4. Как MCP отличается от локального реестра и когда какое подключение выбрать?
5. Skills vs Tools: что из следующего — скилл: «формат ответа ревью»,
   `git diff`, «сначала grep, потом linter»?
