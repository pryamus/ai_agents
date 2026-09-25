# Отчёт по Stateless

## Методика и ограничения

Проверен текущий `HEAD` `588f1a1` от 2026-04-04. Рабочее дерево чистое, изменений не вносил.

Сборку и тесты не запускал: даже `dotnet build/test` может создавать `bin/obj`, что нарушило бы требование «только чтение». Выводы основаны на статическом анализе исходников, тестов, solution, CI и примеров.

В tracked-файлах найдено:

- 60 production C#-файлов;
- 30 test C#-файлов;
- 412 атрибутов `[Fact]`/`[Theory]` до раскрытия `[InlineData]`;
- 19 тестов с `async void`;
- отсутствуют coverage-collector, benchmark-проект, `global.json`, lock-файл и API compatibility baseline.

## Краткий вывод

Функциональная база и количество сценариев хорошие: покрыты состояния, иерархия, guards, reentry, initial transitions, параметризованные и динамические триггеры, sync/async actions, события и графы.

Главные слабые места:

1. **Sync/async execution path недостаточно последователен.** Есть fire-and-forget ветка для async dynamic selector, неоднозначное смешивание sync/async handlers и потеря unmet guards в async unhandled-trigger path.
2. **Observability ограничена состоянием и двумя событиями.** Нет структурированного результата `Fire`, correlation/transition ID, rejected-trigger событий, метрик длительности и безопасной диагностики без вызова guards.
3. **Тесты асинхронности ненадёжны:** `async void`, неawait-вызовы, `Task.Delay` вместо детерминированных barriers.
4. **Graph/reflection API полезен, но теряет информацию и зависит от `ToString()` состояний.** Возможны коллизии имён, потеря destinations динамических переходов и отсутствие action metadata в Mermaid.
5. **Версионная матрица не согласована:** библиотека и examples ориентированы на `net10.0`, а тестовый проект проверяет только `net462;net8.0;net9.0`.
6. **Coverage и производительность количественно не измеряются.**

---

# 1. Архитектура и покрытие сценариев

| Сценарий | Фактическое покрытие | Оценка |
|---|---|---|
| Базовые переходы, value/reference states | Базовые сценарии есть в `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/StateMachineFixture.cs:22-52` | Высокое |
| Внешнее хранение состояния | Проверяются accessor/mutator и количество вызовов mutator: `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/StateMachineFixture.cs:63-84` | Среднее; нет persistence round-trip и fault cases |
| Иерархические состояния | Entry/exit ordering, superstate/substate, reentry: `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/StateRepresentationFixture.cs:120-273` | Высокое |
| Initial transitions | Вложенные initial transitions, порядок entry и transition events: `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/InitialTransitionFixture.cs:10-337` | Высокое для sync, среднее для async |
| Guards и приоритет superstate/substate | Sync и async варианты, включая multi-layer ancestry: `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/TransitionTests.cs:47-139`, `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/AsyncTransitionTests.cs:8-100` | Высокое |
| Guards с параметрами | 1–3 параметра, missing/extra/incorrect types: `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/StateMachineFixture.cs:771-1040` | Высокое для основных случаев |
| Reentry, dynamic transitions | Много sync/async сценариев в `Dynamic*Fixture.cs`; reentry и dynamic destination проверяются | Высокое happy-path покрытие |
| Internal/ignored transitions | Отдельные fixtures, включая async internal actions: `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/InternalTransitionFixture.cs:15-305`, `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/InternalTransitionAsyncFixture.cs:9-283` | Среднее/высокое |
| Activation/deactivation | Sync и async варианты, иерархия и idempotency: `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/ActiveStatesFixture.cs:9-188`, `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/AsyncActionsFixture.cs:342-393` | Среднее |
| Firing modes | Immediate и Queued, sync и async: `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/FiringModesFixture.cs:15-116`, `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/AsyncFiringModesFixture.cs:16-158` | Среднее; нет overflow, cancellation и failure-after-queue |
| События переходов | Регистрация, unregistration, sync/async callbacks: `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/OnTransitionedEventTests.cs:52-182` | Среднее; нет fault isolation и reentrancy |
| Reflection | Обширные проверки metadata и async trigger fix: `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/ReflectionFixture.cs:100-1037`, `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/GetInfoFixture.cs:9-58` | Среднее/высокое |
| DOT/Mermaid graph | Много exact-output тестов: `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/DotGraphFixture.cs:120-731`, `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/MermaidGraphFixture.cs:8-388` | Среднее; нет adversarial cases |
| Faults, cancellation, concurrency | Практически отсутствуют | Низкое |
| Производительность | Benchmark-тестов и метрик нет | Не измерено |
| Примеры как интеграционный smoke test | Только compile через solution | Низкое |

## Сильные стороны

- Хорошо проверяются порядок `OnExit → OnTransitioned → OnEntry → OnTransitionCompleted`: `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/StateMachineFixture.cs:538-565`.
- Есть regression coverage для сложной иерархии и приоритета ближайшего открытого ancestor transition.
- Есть отдельные проверки sync/async action execution и запрет вызова async action из sync `Fire`.
- В `StateMachine<TState,TTrigger>` явно разделены состояние, конфигурация, очередь и callbacks: `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs:25-45`.
- В проект включены SourceLink, deterministic build, signing, license и package README: `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Stateless.csproj:13-30`, `:41-50`.

---

# 2. Наиболее существенные архитектурные риски

## 2.1. Async dynamic selector запускается через fire-and-forget из sync `Fire`

`DynamicTriggerBehaviourAsync` наследует `TriggerBehaviour`, а не `TriggerBehaviourAsync`, и добавляется в sync-коллекцию поведений:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateConfiguration.Async.cs:1419-1432`
- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/DynamicTriggerBehaviour.Async.cs:8-24`

Sync `Fire` находит этот handler и запускает `ContinueWith` без ожидания и без обработки исключений:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs:392-434`
- конкретно `ContinueWith`: `:424-433`

Следствия:

- `Fire()` может вернуться до фактического перехода;
- исключение selector-а может превратиться в unobserved task exception;
- порядок `Fire → State` не определён для этого API;
- поведение не зафиксировано в тестах: async dynamic проверяется практически только через `FireAsync`, например `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/DynamicAsyncTriggerBehaviourAsyncFixture.cs:9-18`.

**Рекомендация:** определить один контракт:

- либо запрещать async dynamic selector для sync `Fire` с понятным исключением;
- либо явно поддерживать sync bridge с блокировкой и синхронизацией контекста;
- `ContinueWith` удалить, использовать awaited path и гарантированно наблюдать исключения.

## 2.2. Смешивание sync и async handlers не имеет однозначной семантики

`TryFindLocalHandlerAsync` отдельно вычисляет sync и async результаты, а затем возвращает:

```text
handleResultSync ?? handleResultAsync
```

См. `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateRepresentation.Async.cs:204-235`.

Проблемы:

- sync и async candidates не проверяются на взаимную исключительность вместе;
- если sync candidate найден, но его guard закрыт, он может замаскировать валидный async candidate;
- если оба кандидата валидны, async-кандидат silently игнорируется;
- `GetPermittedTriggersAsync` может вернуть дубликаты для одного trigger.

Использование результата в `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.Async.cs:215-225` не исправляет эту проблему.

**Рекомендация:** объединить sync/async кандидатов в один алгоритм выбора, явно определить приоритет и добавить таблицу тестов:

- sync-only;
- async-only;
- sync valid + async closed;
- sync closed + async valid;
- оба valid;
- оба closed;
- async behavior в superstate и sync behavior в substate.

## 2.3. Async unhandled-trigger path теряет unmet guards

Sync path передаёт описания guards:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs:403-407`

Async path вычисляет `foundHandler.UnmetGuardConditions`, но передаёт `null`:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.Async.cs:215-220`

Это означает, что:

- custom `OnUnhandledTriggerAsync((state, trigger, guards) => ...)` не получает причину;
- default exception не содержит guard descriptions;
- sync и async диагностика различаются.

Тест async unhandled-trigger проверяет только факт вызова callback, но не содержимое `guards`: `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/AsyncActionsFixture.cs:302-316`.

**Рекомендация:** передавать `foundHandler?.UnmetGuardConditions` и добавить тесты для sync/async custom handlers и default exception message.

## 2.4. `PermitDynamicIfAsync` имеет async selector, но sync guard

API использует `Func<Task<TState>>` для destination selector, но guard остаётся `Func<bool>`:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateConfiguration.Async.cs:603-635`
- parameterized overloads: `:697-709`

В то же время `PermitIfAsync` принимает `Func<Task<bool>>`:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateConfiguration.Async.cs:1073-1080`

Тесты dynamic async используют sync guards:

- `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/DynamicAsyncTriggerBehaviourAsyncFixture.cs:68-89`

Это либо функциональное ограничение, либо незадокументированная асимметрия API.

**Рекомендация:** добавить overload с `Func<Task<bool>>`/`Func<TArgs,Task<bool>>` либо явно документировать, что async dynamic guard не поддерживается. Reflection должен сохранять timing guard-а отдельно от timing selector-а.

## 2.5. Queue и владение state machine не определены достаточно строго

В README явно сказано, что state machine нельзя использовать конкурентно:

- `/home/user/ai_course/ai_agents/Module4/stateless/README.md:328-345`

При этом:

- `_firing` — обычный `bool`, не `volatile` и не защищён lock-ом: `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs:37-45`;
- очередь не ограничена по размеру;
- нет `CancellationToken`;
- при исключении во время обработки queued events могут остаться в очереди;
- при nested async `FireAsync` вызов возвращается сразу после enqueue, не дожидаясь выполнения queued trigger: `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.Async.cs:177-201`.

Особенно проблематичен `AlarmExample`: timer callback вызывает `Fire` из timer thread:

- создание таймеров: `/home/user/ai_course/ai_agents/Module4/stateless/example/AlarmExample/Alarm.cs:90-97`;
- callback: `:143-146`.

Пользовательский ввод при этом может вызывать `Fire` из другого потока.

**Рекомендация:** выбрать и зафиксировать одну модель:

- single-threaded actor/serialized access + запрет конкурентного доступа;
- либо lock/actor-обёртка и thread-safe очередь.

Отдельно нужно определить контракт nested async fire, backpressure, cancellation и поведение очереди после ошибки.

---

# 3. Observability и diagnostics

## Что уже хорошо

- `OnTransitioned` и `OnTransitionCompleted` дают разные точки наблюдения и проверяются на порядок.
- `OnUnhandledTrigger` позволяет перехватить отказ.
- `GetInfo()` и graph дают статическую конфигурацию.
- `Transition` содержит source, destination, trigger и parameters: `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Transition.cs:25-68`.
- `InvocationInfo` различает sync/async timing: `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Reflection/InvocationInfo.cs:17-24`, `:76-79`.

## Слабые места

### Нет структурированного результата `Fire`

Нет объекта, который различал бы:

- transition accepted;
- ignored;
- rejected because trigger отсутствует;
- rejected because guard closed;
- failed action;
- queued/reentrant event.

`GetDetailedPermittedTriggers` возвращает только trigger и параметры, но не причины недоступности:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs:141-145`
- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/TriggerDetails.cs:15-36`

### `ToString()` может вызвать guards и уйти в thread pool

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs:722-732`

Непосредственный вызов:

```text
Task.Run(... GetPermittedTriggersAsync() ... GetAwaiter().GetResult()
```

Это:

- лишний thread hop;
- потеря исходного `SynchronizationContext`;
- вызов user guards из, казалось бы, диагностического API;
- риск исключения из `ToString()`;
- guards, которые случайно имеют side effects, будут выполняться чаще.

### Transition payload мутабелен

`Transition` сохраняет исходный массив без копирования:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Transition.cs:34-40`
- массив также напрямую хранится в очереди: `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs:358-362`.

Один callback/action может изменить `Parameters`, и следующий callback увидит изменённые данные.

### Reflection metadata ограничена

`InvocationInfo` хранит только method name, description и timing:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Reflection/InvocationInfo.cs:27-79`

Нет:

- declaring type;
- assembly/source location;
- delegate target;
- trigger/state type identity;
- machine instance name;
- correlation ID;
- времени начала/окончания.

Для lambdas описание часто заменяется на общий `"Function"`: `:54-73`.

### `StateMachineInfo.InitialState` частично инициализирован

`StateInfo.Transitions` возвращает `null`, пока `AddRelationships` не вызван:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Reflection/StateInfo.cs:163-172`

Это закреплено тестом:

- `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/StateInfoTests.cs:8-24`

Публичный контракт `StateMachineInfo.InitialState` поэтому не является полноценным snapshot-объектом.

**Рекомендация:** добавить optional diagnostics sink без обязательной зависимости на logging framework:

- `FireStarted`;
- `FireCompleted`;
- `FireRejected`;
- `GuardEvaluated`;
- `ActionStarted/Completed/Failed`;
- `TransitionId`, `MachineId`, timestamp, duration, correlation/causation ID.

При этом `ToString()` должен быть чистым и не вызывать guards.

---

# 4. Graph и reflection

## Сильные стороны

- Есть отдельные representation и rendering layers.
- `StateGraph` отделяет построение графа от форматирования: `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/StateGraph.cs:15-55`.
- Есть exact-output тесты для guards, reentry, internal transitions, dynamic transitions и substates.
- В текущем `HEAD` отдельно добавлено reflection-представление async fixed transitions: `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Reflection/StateInfo.cs:82-95`.

## Проблемы

### Состояния идентифицируются по `ToString()`

`StateGraph.States` — `Dictionary<string, State>`:

- объявление: `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/StateGraph.cs:17-27`;
- добавление single states: `:208-215`;
- добавление superstates: `:222-229`.

Два разных state value с одинаковым `ToString()` могут перезаписать друг друга. Это особенно проблемно, поскольку библиотека заявляет поддержку generic states:

- `/home/user/ai_course/ai_agents/Module4/stateless/README.md:28-45`.

Аналогичная проблема есть в Mermaid alias map:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/MermaidGraphStyle.cs:144-178`.

### Dynamic possible destinations могут потеряться

`GetInfo()` добавляет reachable states только из destination fixed/reentry behaviors:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs:162-178`

`DynamicStateInfos` хранит destination как строку:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Reflection/DynamicTransitionInfo.cs:31-55`, `:67-90`

Graph ищет эти states только в уже построенном словаре:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/StateGraph.cs:169-189`

Если caller не сконфигурирует possible destination states отдельно, рёбра dynamic transition будут потеряны.

### Mermaid не показывает entry/exit actions

В `State` есть отдельные списки actions:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/State.cs:37-65`

DOT их выводит:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/UmlDotGraphStyle.cs:32-80`

Mermaid `FormatOneCluster` их не использует, а `FormatOneState` возвращает пустую строку:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/MermaidGraphStyle.cs:32-62`

Это ухудшает диагностическую ценность Mermaid по сравнению с DOT.

### Слабая escaping-стратегия

DOT escaping покрывает только `\` и `"`:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/UmlDotGraphStyle.cs:144-152`

Mermaid удаляет whitespace, `:` и `-`, но не определяет полноценную стратегию для кавычек, переводов строк и управляющих символов:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/MermaidGraphStyle.cs:151-163`

Тесты покрывают пробелы и DOT-кавычки, но не newline, Unicode, null, duplicate `ToString()` и сложные alias collisions.

### Reflection snapshot не иммутабелен

`StateInfo.States`, `FixedTransitions`, `DynamicTransitions` и списки actions доступны как `IEnumerable`, но underlying collections остаются изменяемыми:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Reflection/StateInfo.cs:128-188`
- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Reflection/StateMachineInfo.cs:12-40`

Для диагностического snapshot API стоит возвращать read-only collections или immutable DTO.

**Рекомендация:** ввести стабильный typed `StateId`/node ID, не зависящий от `ToString()`, валидировать collisions и включить possible dynamic states в `StateMachineInfo`. Добавить parity-тесты DOT/Mermaid для действий, async metadata, null, newline и одинаковых display names.

---

# 5. Производительность

## Что сделано разумно

- `StringBuilder` используется в graph rendering: `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/StateGraph.cs:62-98`.
- Для списка переходов заранее задана capacity: `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/GraphStyleBase.cs:70-72`.
- `TaskResult.Done` кэшируется: `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/TaskResult.cs:5-14`.

## Потенциальные hot spots

1. **Legacy sync bridge создаёт thread hop и блокировку.**

   - `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs:126-145`
   - `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs:726-732`

2. **Каждый поиск handler-а создаёт временные массивы/list-ы.**

   - `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateRepresentation.cs:61-82`
   - `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateRepresentation.cs:85-117`

3. **Иерархические операции рекурсивны и не кэшируются.**

   - `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateRepresentation.cs:296-310`
   - `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateRepresentation.cs:173-217`

4. **Async permitted triggers делают повторные обходы и union.**

   - `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateRepresentation.Async.cs:145-184`

5. **Graph Mermaid делает линейный поиск state name на каждый label.**

   - `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/MermaidGraphStyle.cs:175-178`

6. **Sync internal action при `FireAsync` offload-ится через `Task.Run`.**

   - `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.Async.cs:305-318`

7. **Нет benchmark baseline.** Нельзя определить, являются ли эти затраты существенными для типичного `Fire`, `GetInfo` или graph generation.

**Рекомендация:** добавить BenchmarkDotNet-сценарии для:

- sync/async `Fire`;
- 1/3/10 уровней иерархии;
- 1/10/100 guards;
- queued/reentrant firing;
- `GetPermittedTriggersAsync`;
- `GetInfo` и DOT/Mermaid rendering;
- числа аллокаций на transition.

После этого оптимизировать только подтверждённые bottlenecks, а не заранее усложнять API.

---

# 6. Качество тестируемости и самих тестов

## Основные проблемы

### `async void`

19 тестов имеют `async void`, например:

- `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/DynamicAsyncTriggerBehaviourFixture.cs:10-165`;
- `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/InitialTransitionFixture.cs:69-163`;
- `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/AsyncActionsFixture.cs:395-493`;
- `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/AsyncFiringModesFixture.cs:161-203`;
- `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/StateMachineFixture.cs:1055-1064`.

xUnit не всегда ожидает завершение такого метода так же надёжно, как `Task`. Assertions и exceptions после первого `await` могут выполняться после завершения теста.

### Fire-and-forget в тестах

Есть вызовы `FireAsync` без `await`, например:

- `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/AsyncActionsFixture.cs:12-21`;
- `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/AsyncActionsFixture.cs:497-516`;
- `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/AsyncFiringModesFixture.cs:27-37`, `:60-71`.

### `Task.Delay` как синхронизация

Используются фиксированные задержки:

- `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/DynamicAsyncTriggerBehaviourAsyncFixture.cs:9-155`;
- `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/AsyncFiringModesFixture.cs:161-200`.

Это увеличивает время suite и создаёт потенциальную flakiness. Лучше использовать `TaskCompletionSource`, `ManualResetEventSlim` или контролируемый scheduler.

### Нет fault/cancellation coverage

Нет систематических тестов на:

- исключение в guard;
- исключение в entry/exit/internal action;
- faulted `Task`;
- cancellation;
- переход после частично выполненного callback;
- сохранение queue после исключения;
- `FireAsync` из нескольких параллельных callers;
- invalid `FiringMode`;
- reparenting state;
- duplicate `SubstateOf`;
- null state/trigger values.

### Fragile internals testing

`OnTransitionedEventTests` получает private fields через reflection и relies on field order:

- `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/OnTransitionedEventTests.cs:44-50`

`GlobalSuppressions.cs` отключает часть xUnit analyzer diagnostics:

- `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/GlobalSuppressions.cs:6-12`

### Нет coverage enforcement

Test project содержит только xUnit/test SDK packages:

- `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/Stateless.Tests.csproj:22-31`

В CI нет `--collect`, coverage report или threshold:

- `/home/user/ai_course/ai_agents/Module4/stateless/.github/workflows/BuildAndTestOnPullRequests.yml:23-30`

**Рекомендация:**

- заменить все `async void` на `async Task`;
- await-ить каждый `FireAsync`;
- заменить `Task.Delay` на детерминированные barriers;
- добавить `XPlat Code Coverage` и минимальные branch thresholds;
- добавить отдельные negative/fault/cancellation tests;
- ввести reusable test helpers для spy actions, faulting guards и controllable async scheduler;
- добавить property-based/fuzz tests для generic state/trigger names и payload validation.

---

# 7. Solution, CI и поддержка версий

## Solution

Основной `/home/user/ai_course/ai_agents/Module4/stateless/Stateless.sln` включает library, tests и все пять examples:

- `/home/user/ai_course/ai_agents/Module4/stateless/Stateless.sln:27-39`

Это даёт compile-time проверку examples, но смешивает core library, tests и интерактивные приложения.

Есть второй solution:

- `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/Stateless.Tests.sln:6-7`

Он содержит только test project и может использоваться разработчиком отдельно. Два solution с разными GUID и разным возрастом увеличивают риск запуска не того набора проектов.

Рекомендация:

- оставить core/test solution;
- вынести examples в отдельный `examples.sln` или условный solution filter;
- явно документировать, какой solution является canonical.

## Target frameworks

Library:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Stateless.csproj:7`
- `netstandard2.0;net462;net8.0;net9.0;net10.0`

Tests:

- `/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/Stateless.Tests.csproj:5-6`
- `net462;net8.0;net9.0`

Examples:

- `net10.0`, например `/home/user/ai_course/ai_agents/Module4/stateless/example/BugTrackerExample/BugTrackerExample.csproj:3-5`;
- аналогично `JsonExample`, `OnOffExample`, `TelephoneCallExample`, `AlarmExample`.

Проблемы:

- `net10.0` есть у library/examples, но нет в test matrix;
- `netstandard2.0` только компилируется как multi-target library, но не проверяется отдельным consumer project;
- `net462` проверяется только в Windows CI;
- Linux/macOS runtime compatibility не проверяется;
- пользователь с .NET 8/9 SDK не сможет собрать examples/solution, хотя core library заявляет эти TFMs.

README утверждает:

- `/home/user/ai_course/ai_agents/Module4/stateless/README.md:361-364`

Что Visual Studio 2017 или новее достаточна, но `net10.0` требует более современного SDK/VS. Это стоит уточнить.

## CI

Workflow:

- `/home/user/ai_course/ai_agents/Module4/stateless/.github/workflows/BuildAndTestOnPullRequests.yml:1-44`

Сильные стороны:

- restore/build/test;
- установка .NET 8/9/10;
- pack/publish только для upstream `dev/master`.

Проблемы:

1. Только `windows-latest`: `:11`.
2. Нет `net10.0` test target.
3. Нет Linux/macOS matrix.
4. `pack` выполняется только после push в `dev/master`, не на каждом PR: `:32-44`.
5. Нет package install smoke test и проверки содержимого `.nupkg`.
6. Нет API compatibility/package validation.
7. Нет timeout, concurrency, explicit permissions, test result artifacts.
8. Actions используют tags `@v5`, а не immutable SHA: `:13-16`.
9. Нет отдельной проверки examples как запускаемых приложений.
10. Нет dependency/security scan.

Рекомендация:

- добавить `net10.0` в tests;
- добавить compile-only `netstandard2.0` consumer;
- matrix для `net8/net9/net10` на Linux и Windows, `net462` отдельно на Windows;
- выполнять `dotnet pack` на PR;
- устанавливать собранный пакет в маленький consumer project;
- включить `EnablePackageValidation`/API compatibility baseline;
- добавить `global.json`, lock-файл и `timeout-minutes`;
- публиковать TRX/coverage artifacts;
- закрепить GitHub Actions по SHA.

## Release metadata

Assembly version остаётся `4.0.0.0`:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Properties/AssemblyInfo.cs:5-6`

Package version — `5.20.1`:

- `/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Stateless.csproj:10-12`

Это может быть намеренной бинарной совместимостью, но policy и связь package/runtime version не описаны. `SECURITY.md` содержит только общую инструкцию и не указывает поддерживаемые версии:

- `/home/user/ai_course/ai_agents/Module4/stateless/SECURITY.md:1-5`

---

# 8. Examples

Examples демонстрируют важные архитектурные сценарии:

- parameterized triggers, hierarchy, reentry, graph:  
  `/home/user/ai_course/ai_agents/Module4/stateless/example/BugTrackerExample/Bug.cs:29-52`, `:96-99`;
- JSON round-trip состояния:  
  `/home/user/ai_course/ai_agents/Module4/stateless/example/JsonExample/Member.cs:21-41`, `:72-80`;
- event registration/unregistration:  
  `/home/user/ai_course/ai_agents/Module4/stateless/example/OnOffExample/Program.cs:41-65`;
- external state storage, hierarchy, internal transitions, graph:  
  `/home/user/ai_course/ai_agents/Module4/stateless/example/TelephoneCallExample/PhoneCall.cs:42-71`, `:145-147`;
- timers и временные состояния:  
  `/home/user/ai_course/ai_agents/Module4/stateless/example/AlarmExample/Alarm.cs:90-159`.

Но:

- все examples ориентированы на `net10.0`;
- CI только компилирует их, но не запускает;
- programs интерактивные и используют `Console.ReadKey`/`ReadLine`, например `/home/user/ai_course/ai_agents/Module4/stateless/example/OnOffExample/Program.cs:31-66`;
- нет golden/smoke tests для example output;
- `JsonExample` сериализует публичное свойство `State`, но не проверяет полноценный внешний accessor/mutator lifecycle;
- `AlarmExample` использует реальные timers вместо injectable clock/scheduler и потенциально нарушает single-threaded contract.

**Рекомендация:** добавить неинтерактивный `--smoke` режим, fake time provider для alarm, тесты round-trip и отдельный CI job для compile/run smoke tests.

---

# Приоритетный план улучшений

## P0 — до следующего релиза

1. **Устранить fire-and-forget и определить sync/async contract.**
   - Проверить `PermitDynamicAsync` + sync `Fire`.
   - Удалить необработанный `ContinueWith`.
   - Добавить тесты на faulted selector и на `Fire` после async dynamic configuration.

2. **Унифицировать выбор sync/async handlers.**
   - Явно определить приоритет.
   - Проверять mutual exclusivity across sync/async candidates.
   - Не позволять unmet sync handler маскировать valid async handler.

3. **Сохранять unmet guards в async unhandled path.**
   - Передавать `UnmetGuardConditions` вместо `null`.
   - Добавить проверки default exception и custom async callback.

4. **Зафиксировать concurrency/queue semantics.**
   - Либо документировать и enforce single-threaded access, либо сделать state machine thread-safe.
   - Определить nested `FireAsync`, queue capacity, cancellation и cleanup после exceptions.

## P1 — качество эксплуатации

5. **Добавить structured diagnostics/result API.**
   - `FireResult` или аналогичный outcome.
   - rejected/ignored/accepted/failed states.
   - machine ID, transition ID, duration, guard/action status.
   - Не вызывать guards из `ToString()`.

6. **Усилить graph/reflection model.**
   - Typed stable IDs вместо `ToString()`.
   - Включить possible dynamic destinations в snapshot.
   - Сделать snapshot read-only.
   - Унифицировать DOT/Mermaid action output.
   - Добавить collision/null/newline/async metadata tests.

7. **Переработать async test discipline.**
   - Устранить 19 `async void`.
   - Устранить unawaited `FireAsync`.
   - Заменить `Task.Delay` на controllable barriers.
   - Добавить coverage collection и threshold.

8. **Расширить version/CI matrix.**
   - `net10.0` tests.
   - netstandard consumer compile.
   - Linux + Windows.
   - Pack на PR.
   - Package install smoke test.
   - API compatibility validation.

## P2 — maintainability и performance

9. **Добавить benchmark suite** и измерить sync/async fire, guards, hierarchy, queue, `GetInfo`, graph generation.

10. **Сделать примеры тестируемыми.**
    - `TimeProvider`/scheduler abstraction.
    - Неинтерактивный режим.
    - Отдельный smoke test project.

11. **Упростить и стабилизировать API.**
    - Синхронная и async реализации сейчас сильно дублируются.
    - `StateConfiguration.cs` и `StateConfiguration.Async.cs` имеют большие overload-матрицы.
    - Стоит рассмотреть общие внутренние abstractions, сохранив binary/source compatibility.

12. **Обновить документацию.**
    - Уточнить поддерживаемую матрицу TFM.
    - Описать single-threaded/queue semantics.
    - Описать async dynamic guard limitations.
    - Исправить malformed async unregister examples в `/home/user/ai_course/ai_agents/Module4/stateless/README.md:249-270`.
    - Добавить supported versions в `SECURITY.md`.

Итог: функционально Stateless покрыт существенно лучше, чем типичный небольшой state-machine library, но текущая уверенность в async, diagnostics, concurrency и multi-target/package regressions ограничена отсутствием coverage, fault tests, runtime matrix и benchmark-данных.