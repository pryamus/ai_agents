# Лабораторная 2.10 — Безопасность: RBAC, аудит, инцидент

**Цель:** настроить RBAC для агентов (роли reader/coder/operator/admin),
вести tamper-evident аудит и разобрать симуляцию инцидента по журналу.

## Структура

```text
lab_2_10_security/
├── rbac.py      # роли, deny-override, basename-матчинг секретов, policy_selfcheck
├── audit.py     # AuditLog: JSONL + sha256-цепочка, verify, summarize
├── incident.py  # 10 попыток выхода за полномочия -> сверка с ожиданиями
└── tests/test_security.py
```

## Шаги практики

1. **Симуляция инцидента:**

   ```powershell
   cd code\lab_2_10_security
   python incident.py
   ```

   Ожидаемо: самопроверка чистая, `по ожиданиям: 10/10`, 6 DENY с
   правилами, цепочка цела, exit 0. Журнал — в `logs/audit.jsonl`.

2. **Проверка цепочки и разбор:**

   ```powershell
   python -c "from audit import AuditLog; print(AuditLog('logs/audit.jsonl').verify())"
   python -c "from audit import AuditLog; [print(x) for x in AuditLog('logs/audit.jsonl').summarize()['denied_details']]"
   ```

3. **Тесты:**

   ```powershell
   python -m pytest -q
   ```

4. **(Самостоятельно)** Добавьте роль `auditor` (только чтение кода и
   журналов, без shell) и расширьте секреты маской `*.pem`; убедитесь,
   что `policy_selfcheck` по-прежнему пуст, а инцидент проходит.

## Ключевые решения

- **Deny-override + default deny:** запрет всегда сильнее разрешения,
  отсутствие правила = запрет. Та же семантика, что permissions в 2.3.
- **Секреты закрыты всем:** правило `no-secrets` есть даже у `admin` —
  least-privilege не делает исключений для «своих».
- **Tamper-evident, не tamper-proof:** цепочка показывает факт правки,
  но не мешает взлому хранилища — для критичных систем журнал уезжает
  в append-only хранилище (WORM/SIEM).
- **Инцидент как тест:** ожидания зафиксированы кодом — регрессия политики
  (случайно открытый доступ) роняет `run_incident`, а не «кажется ок».
