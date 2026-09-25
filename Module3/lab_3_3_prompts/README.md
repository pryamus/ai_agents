# Лабораторная 3.3 — Шаблоны промптов и их линт

**Цель:** промпт как код: библиотека шаблонов (генерация, рефакторинг,
объяснение) со строгим контрактом переменных, few-shot и бюджетом; линтер
ловит структурные дефекты до отправки модели.

## Структура

```text
lab_3_3_prompts/
├── templates.py  # TEMPLATES + render(): строгая подстановка, бюджет
├── lint.py       # lint_prompt(): no-role/no-format/vague-verb/over-budget
├── render.py     # CLI: --template + --set VAR=... (@файл) + --lint
└── tests/test_prompts.py
```

## Шаги практики

1. **Рендер + линт:**

   ```powershell
   cd code\lab_3_3_prompts
   python render.py --template codegen --set func_name=parity --set spec="чётность числа" --lint
   python render.py --template explain --set audience=студент --set source="@sample_project\orders.py" --lint
   ```

2. **Границы контракта:**

   ```powershell
   python render.py --template codegen --set func_name=f
   # ошибка контракта: нет переменной 'spec'
   ```

3. **Тесты:**

   ```powershell
   python -m pytest -q
   ```

4. **(Самостоятельно)** Добавьте шаблон `testgen` (генерация тестов:
   переменные `module`, `focus`; ограничение «только pytest-стиль»).
   Добейтесь чистого линта и покройте тестами контракт.

## Ключевые решения

- **Строгий рендер:** лишняя переменная и незакрытый плейсхолдер — ошибки,
  а не молчаливый мусор: опечатка в имени видна сразу.
- **Бюджет до отправки:** превышение `max_tokens` останавливает рендер —
  дешевле, чем обрезанный ответ модели.
- **Линтер советует:** эвристики (`vague-verb`) помечены как эвристики;
  жёстко валят только `no-role` и `over-budget`.
