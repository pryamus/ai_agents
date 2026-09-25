# Архитектурный обзор библиотеки Stateless

**Репозиторий:** `/home/user/ai_course/ai_agents/Module4/stateless` (ветка `dev`, v5.20.1, коммит `588f1a1`)
**Объём:** ~8 570 строк C# в `src/Stateless`, 412 тестов в `test/Stateless.Tests`
**Целевые фреймворки:** `netstandard2.0; net462; net8.0; net9.0; net10.0` (`src/Stateless/Stateless.csproj:7`)

---

## 1. Сводка

Stateless — зрелая, хорошо покрытая тестами библиотека с **сильной концептуальной моделью** (состояния, триггеры, guard-условия, иерархия, reentry, initial transition) и **осознанно минимальным публичным API** в смысле «без магии». Но реализация несёт на себе **системный долг**: тотальное дублирование sync/async, отсутствие потокобезопасности, протекающие границы между `Reflection`/`Graph` и внутренним ядром, и несколько подтверждённых расхождений в поведении sync- и async-путей.

| Область | Оценка |
|---|---|
| Разделение ответственности | Хорошее на уровне слоёв, среднее на уровне классов |
| Модель состояний/переходов | Сильная; ~5 известных семантических асимметрий |
| Sync/async дублирование | Главный долг (~2/3 кода) |
| Extensibility | Очень ограниченная (закрытые иерархии поведений) |
| Thread-safety | Отсутствует, задокументировано, но не защищено |
| Coupling | Высокий к `object[]`, `Dictionary`, `TState.Equals` |
| Публичный API | 143 метода конфигурации; есть async-пробелы и несогласованности |

---

## 2. Разделение ответственности

### Слои (это сильная сторона)

```
StateMachine<TState,TTrigger>              — оркестратор, очередь, текущее состояние
  └─ StateConfiguration                    — fluent-builder (только запись в конфигурацию)
  └─ StateRepresentation                   — узел иерархии состояний, enter/exit/поиск хендлера
       └─ TriggerBehaviour*                — стратегии переходов
       └─ Entry/Exit/Activate/Deactivate…  — стратегии действий
  ├─ Stateless.Reflection.*                — read-only проекция конфигурации
  └─ Stateless.Graph.*                     — визуализация поверх Reflection
```

Плюсы:
- `Graph`/`Reflection` не имеют обратной зависимости от рантайма — `StateMachineInfo`/`StateInfo` (`src/Stateless/Reflection/StateMachineInfo.cs:10`, `src/Stateless/Reflection/StateInfo.cs:10`) работают только с `InvocationInfo`/`TriggerInfo`, т.е. это чистые DTO. Это позволяет строить графы/сериализацию независимо от исполнения. Архитектурно это лучшее решение в проекте.
- Инкапсуляция внутренних типов в Reflection-слое выдержана: `StateInfo.CreateStateInfo` и `AddRelationships` — `internal static` и принимают `internal` вложенный `StateRepresentation` (`src/Stateless/Reflection/StateInfo.cs:12, 38`).
- Стратегическое поведение действий вынесено в отдельные иерархии классов вместо `switch` по флагам: `EntryActionBehavior.Sync/SyncFrom<T>/Async/AsyncFrom<T>` (`src/Stateless/EntryActionBehaviour.cs:8-113`). Паттерн «двух исполнений в одном классе» здесь удачный: `SyncFrom<TTrigger>` наследует `Sync`, а не дублирует.

### Проблемы

**2.1. `StateMachine` — «бог-класс» с 4 разными ответственностями.** `src/Stateless/StateMachine.cs:25-35` держит: хранилище состояния (accessor/mutator), реестр конфигураций, очередь триггеров, и подписки на события. `Configure()` (`src/Stateless/StateMachine.cs:203-206`) отдаёт `StateConfiguration`, который **держит ссылку на машину** (`src/Stateless/StateConfiguration.cs:14, 33`) и **публично её экспортирует** (`State`/`Machine`, `src/Stateless/StateConfiguration.cs:28, 33`). Builder может фактически вызвать `Machine.Fire(...)` — бессмысленная циклическая связность.

**2.2. `StateRepresentation` отвечает и за конфигурацию, и за рантайм.** `src/Stateless/StateRepresentation.cs:14-18` — хранилища поведений; `src/Stateless/StateRepresentation.cs:120-143` — мутаторы конфигурации (`AddTriggerBehaviour`); `src/Stateless/StateRepresentation.cs:173-255` — исполнение. Мутаторы `public` внутри `internal`-класса, т.е. изоляции на уровне типов нет.

**2.3. `GetInfo()` — смешение чтения и синтеза.** `src/Stateless/StateMachine.cs:158-184`: метод достраивает «недостижимые» состояния (строки 169-176), создавая фиктивные `StateRepresentation` с пустыми коллекциями. В результате `GetInfo().InitialState` (строка 160) — это **другой объект**, чем `GetInfo().States` с тем же `UnderlyingState`; и у него `Transitions` == `null` (см. `src/Stateless/Reflection/StateInfo.cs:166-173`, где `null` — это неявный признак «связи не выставлены»). Сравнение по ссылке у пользователей не работает, а NRE при обращении к `InitialState.Transitions` — неочевидная ловушка.

**2.4. Мёртвый код в продакшн-пути.** `GuardConditionsMet` не используется нигде в `src/Stateless` кроме объявлений (`src/Stateless/TransitionGuard.cs:99`, `src/Stateless/TriggerBehaviour.cs:43`, `src/Stateless/TriggerBehaviour.async.cs:44`) — весь рантайм использует только `UnmetGuardConditions`. При этом в них **разная обработка `null`-guard'а**: `src/Stateless/TransitionGuard.cs:101` проверяет `c.Guard == null`, а `src/Stateless/TransitionGuard.cs:111` — нет (хотя конструктор `src/Stateless/GuardCondition.cs:25` бросает на `null`, т.е. проверка в 101 — мёртвая). Также закомментированный код в `src/Stateless/StateConfiguration.cs:654-655` и дубли `</returns>` в `src/Stateless/StateConfiguration.Async.cs:1064, 1177-1178, 1226-1227`.

---

## 3. Модель состояний и переходов

### Сильные стороны

- **Иерархия состояний** реализована корректно: `Superstate`/`Substates` (`src/Stateless/StateRepresentation.cs:20-22`), рекурсивные `Enter`/`Exit` с корректной семантикой «выходим из поддерева только если уходим наружу» (`src/Stateless/StateRepresentation.cs:188-218`), проверка на реентерабельность состояния через `IsIncludedIn`/`Includes` (`src/Stateless/StateRepresentation.cs:296-311`).
- **Защита от циклов в иерархии** при конфигурации — `SubstateOf` проверяет и прямую, и вложенную циклическую конфигурацию **до** мутации графа (`src/Stateless/StateConfiguration.cs:1128-1158`). Это редкая и очень ценная вещь.
- **`InitialTransition` с валидацией цели** — проверка, что цель действительно подсостояние, отложена до момента входа и даёт внятное сообщение (`src/Stateless/StateMachine.cs:530-537`), плюс fail-fast на повторную настройку (`src/Stateless/StateConfiguration.cs:1819`).
- **Запрет «noop»-переходов**: `EnforceNotIdentityTransition` (`src/Stateless/StateConfiguration.cs:1769-1775`) заставляет явно выбирать между `Ignore`, `PermitReentry` и `InternalTransition`. Хороший дизайн.
- **Диагностика неоднозначности**: несколько переходов с одним триггером и пройденными guard'ами → `InvalidOperationException` с перечислением (`src/Stateless/StateRepresentation.cs:85-96`).
- **Агрегация unmet-guard описаний** для улучшения диагностики (`src/Stateless/StateRepresentation.cs:98-118`).

### Проблемы и риски

**3.1 [HIGH] `CanFire` не видит async-переходы.** `PermitIfAsync`/`PermitReentryIfAsync` кладут поведение в `TriggerBehavioursAsync` через `AddTriggerBehaviourAsync` (`src/Stateless/StateConfiguration.Async.cs:1409-1416`, `src/Stateless/StateRepresentation.Async.cs:135-143`), тогда как `CanFire` → `CanHandle` → `TryFindHandler` → `TryFindLocalHandler` смотрит **только** в синхронный `TriggerBehaviours` (`src/Stateless/StateRepresentation.cs:61-68`). Итог: `CanFire(trigger)` возвращает `false` для триггера, реально срабатывающего через `FireAsync`. При этом `GetPermittedTriggersAsync` этот триггер **уже включает** (`src/Stateless/StateRepresentation.Async.cs:174-175`), и устаревший `GetPermittedTriggers` тоже (`src/Stateless/StateMachine.cs:135`). То есть три публичных API дают три разных ответа об одном и том же. Публичного `CanFireAsync` не существует вовсе.

**3.2 [HIGH] `OnUnhandledTriggerAsync` теряет unmet-guard'ы.** `src/Stateless/StateMachine.Async.cs:219` передаёт литерал `null`:
```csharp
await _unhandledTriggerAction.ExecuteAsync(representativeState.UnderlyingState, trigger, null);
```
тогда как синхронный путь передаёт `result?.UnmetGuardConditions` (`src/Stateless/StateMachine.cs:406`). Из-за этого сообщение об ошибке теряет диагностическую часть (сравните `src/Stateless/StateMachine.cs:790-799` и `src/Stateless/StateMachine.Async.cs:219`). Тестов на это нет.

**3.3 [HIGH] `DynamicTriggerBehaviourAsync` в синхронном пути — fire-and-forget.** `src/Stateless/StateMachine.cs:424-435`:
```csharp
asyncHandler.GetDestinationState(source, args)
    .ContinueWith(t => { ... return HandleTransitioningTriggerAsync(...); });
```
Последствия: (а) `Fire()` возвращается **до** перехода — `machine.State` устарел; (б) исключения уходят в неотслеживаемую задачу; (в) в `FiringMode.Queued` цикл `src/Stateless/StateMachine.cs:374-378` к этому моменту уже завершён → run-to-completion нарушен; (г) `ContinueWith` выполняется на пуле потоков, ломая `RetainSynchronizationContext`.

Причина — архитектурная: `DynamicTriggerBehaviourAsync` наследует **`TriggerBehaviour`, а не `TriggerBehaviourAsync`** (`src/Stateless/DynamicTriggerBehaviour.Async.cs:8`), у него **синхронный** `TransitionGuard` (`src/Stateless/StateConfiguration.Async.cs:1419-1424`), и он кладётся в **синхронный** словарь `TriggerBehaviours` (`AddTriggerBehaviour`, а не `AddTriggerBehaviourAsync`). Из-за этого `TryFindHandlerAsync` (`src/Stateless/StateRepresentation.Async.cs:207`) видит его в синхронной ветке, а `ProcessHandler` (`src/Stateless/StateMachine.Async.cs:263-271`) обрабатывает отдельно.

**3.4 [MEDIUM] `ProcessHandler` перечитывает `State` после вычисления guard'ов.** `src/Stateless/StateMachine.Async.cs:239-240` повторно читает `State` и ищет representation, тогда как `InternalFireOneAsync` уже зафиксировал `source`/`representativeState` **до** асинхронного вычисления guard'ов (`src/Stateless/StateMachine.Async.cs:211-212`). Если async-guard имеет побочный эффект и сменил состояние, `source` в `ProcessHandler` и в вызывающем коде разойдутся. Синхронный путь такого расхождения не имеет.

**3.5 [MEDIUM] `HandleReentryTrigger` семантически отличается от `HandleTransitioningTrigger`.** Синхронный reentry пишет `State` **после** входа (`src/Stateless/StateMachine.cs:492`), а transitioning — **до** (`src/Stateless/StateMachine.cs:499`). Компенсация для `FiringMode.Immediate` есть только в transitioning-пути (`src/Stateless/StateMachine.cs:521-527`); проверка «состояние изменилось во время входа» (`src/Stateless/StateMachine.cs:506-511`) в reentry-пути отсутствует. Итог: в `Immediate` триггер, fired из `OnEntry` при reentry, вычислится относительно устаревшего `State`.

**3.6 [MEDIUM] Guard'ы вычисляются многократно и на каждый чих.**
- `TryFindLocalHandler` вычисляет **все** guard'ы для всех поведений триггера через `Select` **до** фильтрации (`src/Stateless/StateRepresentation.cs:71-77`) — нет короткого замыкания.
- `CanFire` и `Fire` вызывают одно и то же вычисление заново (то есть «проверить, можно ли» + «выстрелить» = 2× вызов guard'ов).
- Для internal-переходов guard'ы вычисляются **третий** раз: `InternalAction` заново обходит иерархию и заново вызывает `TryFindLocalHandler` (`src/Stateless/StateRepresentation.cs:231-255`).
- `GetPermittedTriggersAsync` вычисляет все guard'ы во всех состояниях иерархии (`src/Stateless/StateRepresentation.Async.cs:164-185`).

Итого guard-функции де-факто обязаны быть чистыми, но это **нигде не задокументировано** в XML-доках, и `EnforceNotIdentityTransition`-подобной защиты нет.

**3.7 [LOW] Дубликаты конфигурации не отлавливаются.** `Configure(A).Permit(X, B)` дважды молча добавляет два поведения (`src/Stateless/StateRepresentation.cs:256-264`), и падает только в момент `Fire`/`CanFire` с `MultipleTransitionsPermitted` (`src/Stateless/StateRepresentation.cs:94-95`). Для `SetTriggerParameters` есть fail-fast (`src/Stateless/StateMachine.cs:781-785`), а для `Permit*` — нет. Асимметрия.

---

## 4. Sync/async дублирование

**Это доминирующий архитектурный долг проекта.**

### 4.1 Масштаб

| Пара | Sync | Async | Строк |
|---|---|---|---|
| Builder | `StateConfiguration.cs` (1827) | `StateConfiguration.Async.cs` (1437) | 3264 |
| Оркестратор | `StateMachine.cs` (861) | `StateMachine.Async.cs` (477) | 1338 |
| Узел состояния | `StateRepresentation.cs` (321) | `StateRepresentation.Async.cs` (238) | 559 |
| Guard | `TransitionGuard.cs` (116) | `TransitionGuard.async.cs` (132) | 248 |
| Поведение триггера | `TriggerBehaviour.cs` (57) | `TriggerBehaviour.async.cs` (53) | 110 |
| Переход | `Transitioning…cs` (17), `Reentry…cs` (19) | `.async.cs` (17, 19) | 72 |
| Динамический | `DynamicTriggerBehaviour.cs` (26) | `.Async.cs` (27) | 53 |

**Builder-слой один занимает ~38% кода библиотеки** и содержит **143 публичных метода конфигурации** (79 sync + 64 async), с полным зеркалированием:

```
PermitDynamicIf     ×17  ↔  PermitDynamicIfAsync     ×17
OnEntryFrom         ×9   ↔  OnEntryFromAsync         ×9   (и OnEntryFrom ×9 ↔ OnEntryAsync ×2)
PermitReentryIf     ×8   ↔  PermitReentryIfAsync     ×8
PermitIf            ×8   ↔  PermitIfAsync            ×8
InternalTransitionIf×8   ↔  InternalTransitionAsyncIf×9
IgnoreIf            ×8   ↔  — (нет async-эквивалента)
```

### 4.2 Проблемы

**4.2.1 [HIGH] Функциональные пробелы в async-зеркале.** Отсутствуют: `Ignore`/`IgnoreIf` с async-guard'ом, `SubstateOfAsync`, `PermitAsync`/`PermitReentry` (безусловные — тут разница безобидна), `InitialTransitionAsync`. Нельзя выразить «игнорировать триггер, если асинхронная проверка прошла» — а это вполне законный use case (rate-limiting, внешний сервис).

**4.2.2 [HIGH] Расхождения, порождённые дублированием.** Из-за того, что sync и async пути написаны отдельно, они разошлись как минимум в 6 местах:

| Аспект | Sync | Async | Последствие |
|---|---|---|---|
| unmet-guards в unhandled-обработчике | `StateMachine.cs:406` ✅ | `StateMachine.Async.cs:219` ❌ `null` | потеря диагностики |
| `source` фиксируется | `StateMachine.cs:400` до guard'ов | `StateMachine.Async.cs:239` после guard'ов | расхождение `source` |
| async dynamic-триггер | `StateMachine.cs:424-435` `ContinueWith` | `StateMachine.Async.cs:263-271` `await` | fire-and-forget vs корректно |
| unhandled-детект | `!TryFindHandler(...)` | `foundHandler == null \|\| Unmet.Any()` | разная логика |
| `DynamicTriggerBehaviourAsync` | лежит в sync-словаре | — | см. 3.3 |
| дубликат `FixedTransitionInfo.Create` | `FixedTransitionInfo.cs:11-21` | `:23-33` | копипаст |

**4.2.3 `TriggerBehaviourResult` — «суммирующий» тип с двумя слотами.** `src/Stateless/TriggerBehaviourResult.cs:9-21`: конструкторы для `TriggerBehaviour` и `TriggerBehaviourAsync`, но свойства `Handler` и `HandlerAsync` **независимы**. Вызывающий код обязан знать, какой слот заполнен (`src/Stateless/StateMachine.Async.cs:223-234` — ручная проверка с веткой на `InvalidOperationException`). Комбинаторный тип: любой новый вид поведения (например, «отложенный»/scheduled) потребует третьего слота и третьей ветки в `ProcessHandler`.

**4.2.4 `ConfigureAwait(bool)` размазан по 12 местам.** `src/Stateless/StateRepresentation.Async.cs:50, 52, 57, 60, 66, 72, 80, 85, 87, 95, 110, 116, 126, 132` + `src/Stateless/StateMachine.Async.cs:189, 194`. Каждое новое `await` легко забыть.

**4.2.5 Разное поведение при `ConfigureAwait` для `UnhandledTriggerAction.Sync`.** `src/Stateless/UnhandledTriggerAction.cs:28-32` — `ExecuteAsync` вызывает `Execute` и возвращает `TaskResult.Done` **без** `ConfigureAwait(RetainSynchronizationContext)`. Для остальных sync-действий контекст учитывается. Непоследовательно.

**4.2.6 `TaskScheduler.FromCurrentSynchronizationContext()` бросает без контекста.** `src/Stateless/StateMachine.Async.cs:313-315`:
```csharp
await Task.Factory.StartNew(() => itb.Execute(transition, args),
    CancellationToken.None, TaskCreationOptions.DenyChildAttach,
    TaskScheduler.FromCurrentSynchronizationContext());
```
`FromCurrentSynchronizationContext()` бросает `InvalidOperationException`, если `SynchronizationContext.Current == null` — то есть в консольном приложении, в xUnit без установленного контекста или на пуле потоков связка `RetainSynchronizationContext = true` + синхронный internal-transition + `FireAsync` упадёт. Все 15 тестов в `test/Stateless.Tests/SynchronizationContextFixture.cs` предварительно вызывают `SetSyncContext()`, поэтому баг не покрыт.

**4.2.7 `RetainSynchronizationContext` — «живое» поле и «снимок» одновременно.** Свойство публично и мутабельно (`src/Stateless/StateMachine.cs:96`) и читается «вживую» в `StateMachine.Async.cs`, **но** `GetRepresentation` (`src/Stateless/StateMachine.cs:186-195`) передаёт его текущее значение в конструктор `StateRepresentation`, который сохраняет его **навсегда** (`src/Stateless/StateRepresentation.cs:25-29, 12`). Практическое следствие: если задать флаг **после** конфигурации первых состояний, эти состояния сохранят старое значение, а новые — новое. Поведение будет зависеть от порядка конфигурации. Тест `test/Stateless.Tests/SynchronizationContextFixture.cs:17-23` задаёт флаг в инициализаторе **до** `Configure`, поэтому расхождение не замечают.

---

## 5. Extensibility

**5.1 [HIGH] Закрытые иерархии поведений.** `TriggerBehaviour` (`src/Stateless/TriggerBehaviour.cs:8`) и `TriggerBehaviourAsync` (`src/Stateless/TriggerBehaviour.async.cs:9`) — `internal abstract` внутри generic-класса. Набор поведений фиксирован: `Ignored`, `Transitioning`, `Reentry`, `Dynamic`, `Internal` (+ async-пары). Расширить извне нельзя: `AddTriggerBehaviour` (`src/Stateless/StateRepresentation.cs:256`) принимает конкретный `internal`-тип, а рантайм диспетчеризуется `switch` по типам в двух местах:
- `src/Stateless/StateMachine.cs:410-466` (sync, 7 ветвей)
- `src/Stateless/StateMachine.Async.cs:242-322` (async, 8 ветвей)

Добавление одного поведения = правка **обоих** switch'ей + обоих `TryFindHandler` + обоих `StateInfo.AddRelationships` (`src/Stateless/Reflection/StateInfo.cs:51-95`) + обоих `FixedTransitionInfo.Create` (`src/Stateless/Reflection/FixedTransitionInfo.cs:11-33`) + обоих `GetPermittedTriggers*`. Реализация «стратегии» есть (см. `InternalActionBehaviour` как отдельную иерархию — `src/Stateless/InternalActionBehaviour.cs`), но применяется она только к внутренним переходам; **сделать это единообразно для всех типов действий никто не сделал** — 6 почти одинаковых иерархий (`Entry`, `Exit`, `Activate`, `Deactivate`, `Internal`, `UnhandledTrigger`, 490 строк).

**5.2 `internal partial class StateRepresentation` внутри `public partial class StateMachine`** — приём с двумя целями: скрыть тип и получить доступ к `TState`/`TTrigger` без дублирования. Работает, но делает `StateMachine` «утечкой» внутренней структуры; вложенные `internal`-типы внутри публичного generic-класса — известный источник проблем с обрезкой типов (trimming/AOT), что важно для `net8.0+` (`src/Stateless/Stateless.csproj:7`).

**5.3 Точки расширения, которые есть и работают:**
- `GraphStyleBase` (`src/Stateless/Graph/GraphStyleBase.cs:11`) — абстрактный стиль с `virtual`-методами по умолчанию; расширяется без правок ядра. `FormatOneTransition` бросает с внятным текстом, если не переопределён (`:124-127`).
- `Reflection.DynamicStateInfos` с `Add`-перегрузками (`src/Stateless/Reflection/DynamicTransitionInfo.cs:34-55`) — приятный «syntax sugar» для метаданных динамических переходов.
- Внешнее хранение состояния через `Func<TState>`/`Action<TState>` (`src/Stateless/StateMachine.cs:69-76`) — полноценная интеграция с ORM/персистентностью без наследования.
- `InvocationInfo.DefaultFunctionDescription` (`src/Stateless/Reflection/InvocationInfo.cs:54`) — настраиваемое поведение метаданных.

---

## 6. Thread-safety / конкурентность

Документация честна: `README.md:345` — «remains single-threaded and may not be used *concurrently* by multiple threads». Но в коде нет **ни одной** защиты, и это создаёт ловушки, потому что некоторые «чтения» мутируют.

**6.1 [HIGH] «Чтение» мутирует внутреннее состояние.** `GetRepresentation` (`src/Stateless/StateMachine.cs:186-195`) лениво добавляет запись в обычный `Dictionary<TState, StateRepresentation>` (`src/Stateless/StateMachine.cs:27`). Его вызывают «чистые» методы:
- `CurrentRepresentation` (`src/Stateless/StateMachine.cs:147-153`) → используется в `IsInState` (`:580`), `CanFire` (`:597, :612, :629, :648, :665, :681, :699, :719`), `GetPermittedTriggersAsync` (`StateMachine.Async.cs:43`), `InternalFireOne` (`:401`), `Activate`/`Deactivate` (`:316, :327`).

Итог: `CanFire(trigger)` на ещё не сконфигурированном состоянии **добавляет** это состояние в реестр. Два наблюдаемых эффекта:
1. **Побочный эффект в интроспекции**: `GetInfo()` берёт `_stateConfiguration` как есть (`src/Stateless/StateMachine.cs:162`), поэтому «просто посмотрев» `CanFire`, вы добавляете состояние в `GetInfo().States`.
2. **Гонка**: два потока, вызывающие `CanFire` на одном новом состоянии, получат `Dictionary.Add` из двух потоков → порча структуры/бесконечный цикл внутри Dictionary. Никакой синхронизации нет.

**6.2 [HIGH] Очередь и `_firing` не защищены.** `_eventQueue` (`Queue<QueuedTrigger>`) и `bool _firing` (`src/Stateless/StateMachine.cs:43-44`) — обычные поля. `InternalFireQueued` (`src/Stateless/StateMachine.cs:358-384`) делает `Enqueue` + чтение/запись `_firing` без lock'а. Классические гонки: потеря триггера, двойной drain, «залипание» `_firing = true` при исключении в другом потоке.

**6.3 [HIGH] Async-очередь нарушает контракт `await FireAsync(...)`.** `src/Stateless/StateMachine.Async.cs:177-183`:
```csharp
if (_firing) { _eventQueue.Enqueue(...); return; }   // ← Task уже Completed
```
Если `_firing == true` (триггер уже обрабатывается **в этом же** logical flow, т.е. внутри `await` в async-entry/exit-действии), вызывающий `await machine.FireAsync(X)` **получает управление немедленно**, хотя `X` ещё не обработан. Это ломает и run-to-completion, и интуицию «после await состояние обновлено». В sync-версии поведение «правильнее» — вызов просто возвращается, и это ожидаемо для `Queued`. Для `Task`-based API это семантическая ловушка. В репозитории даже есть незавершённая ветка `origin/Fix-#294-Possible-threading-issue-in-FireAsync`, что подтверждает, что проблема признана.

**6.4 [MEDIUM] Нет защиты конфигурации от времени выполнения.** `Configure(...)` и все методы `StateConfiguration` — `public` и работают в любой момент. `foreach (var action in EntryActions)` (`src/Stateless/StateRepresentation.cs:222`), аналогично для `ExitActions` (`:228`), `TriggerBehaviours` (`:71`) — если в этот момент из другого потока (или из `OnEntry`) вызвать `Configure(...).OnEntry(...)`, получим `InvalidOperationException: Collection was modified` либо (что хуже) — частично применённую конфигурацию. `StateConfiguration` не имеет понятия «заморожен».

**6.5 [LOW] `_onTransitionedEvent` / `_onTransitionCompletedEvent` — частичная защита.** `Register`/`Unregister` на `Action` делегате атомарны на уровне multicast (`src/Stateless/OnTransitionedEvent.cs:32-50`), но `List<Func<Transition,Task>> _onTransitionedAsync` (`:12`) — обычный `List` без синхронизации (`:38-42, 52-55, 28`). Перечисление (`:28`) во время регистрации из другого потока → `InvalidOperationException`.

**6.6 Плюсы.** `TaskResult.Done` (`src/Stateless/TaskResult.cs:7-14`) — один предсозданный завершённый `Task`, а не `Task.CompletedTask`-эквивалент с аллокацией; «no-op» sync-действия в async-пути не создают задач. Проброс `RetainSynchronizationContext` (Orleans) продуман и покрыт 15 тестами — это редкая внимательность к деталям.

---

## 7. Coupling

**7.1 [MEDIUM] `object[] args` как сквозной контракт.** Внутренняя модель параметров — `object[]`, распаковывается через `ParameterConversion.Unpack<TArg>(args, index)` с рантайм-кастом и проверкой типов (`src/Stateless/ParameterConversion.cs:7-32`). Отсюда:
- `ParameterConversion.Unpack<TArg>` при `args.Length == 0` возвращает `default` (`src/Stateless/ParameterConversion.cs:29`) — то есть `CanFire(trigger)` для параметризованного триггера «молча» проверяет guard'ы с `default`-значениями. Это задокументировано в XML-doc'ах (`src/Stateless/StateMachine.cs:588-592, 655-659`), что хорошо, но сам дефект дизайна остаётся.
- Максимум 3 аргумента (`TriggerWithParameters<TArg0,TArg1,TArg2>`, `src/Stateless/TriggerWithParameters.cs:89`) — искусственное ограничение, тиражированное в 143 метода.
- `Transition.Parameters` — `public object[]` (`src/Stateless/Transition.cs:68`), утекает в пользовательские `OnEntry`/`OnExit`/`OnTransitioned`, где пользователь обязан знать позиционную схему.

**7.2 [MEDIUM] Зависимость от семантики `Equals`/`GetHashCode` типов пользователя.** `TState` используется как ключ `Dictionary` (`src/Stateless/StateMachine.cs:27`) и через `.Equals` в 20+ местах (`Transition.IsReentry` — `src/Stateless/Transition.cs:60`, `EnforceNotIdentityTransition` — `src/Stateless/StateConfiguration.cs:1771`, `HandleReentryTrigger` — `src/Stateless/StateMachine.cs:475, 331`, `Includes` — `src/Stateless/StateRepresentation.cs:298`). Плюс — `Transition.IsReentry` (`:60`) и `HandleReentryTrigger` (`:475`) — **два независимых вычисления одного и того же**. Для record-типов / структур без переопределённого `Equals` это тихая поломка. Нигде не задокументировано требование «`TState` должен иметь value-семантику равенства».

**7.3 [MEDIUM] `Graph` переиспользует `ToString()` как идентификатор узла.** `src/Stateless/Graph/State.cs:53-54` (`NodeName = StateName = stateInfo.UnderlyingState.ToString()`), `src/Stateless/Graph/StateGraph.cs:111, 140, 143, 212, 227, 236`. Два разных состояния с одинаковым `ToString()` молча склеятся. Для строковых/enum-состояний — нормально; для record-состояний или complex-типов — тихая порча графа. `MermaidGraphStyle` это отчасти лечит (`src/Stateless/Graph/MermaidGraphStyle.cs:144-173`), но `UmlDotGraph` — нет.

**7.4 [LOW] `MermaidGraphStyle` — мутирующий «стиль» с O(n²).** `GetPrefix()` (`src/Stateless/Graph/MermaidGraphStyle.cs:66-84`) — метод «Get», который **строит внутреннюю карту** как побочный эффект (строка 68), а `StateGraph.ToGraph` (`src/Stateless/Graph/StateGraph.cs:64`) **зависит** от этого побочного эффекта. Флаг `_stateMapInitialized` (`:17, 172`) делает повторный `ToGraph` на том же экземпляре стиля недетерминированным, а `GetSanitizedStateName` (`:175-178`) — линейный скан `_stateMap.FirstOrDefault(...)` на каждый вызов → O(n²) на графе среднего размера. Плюс `_graph`/`_direction` readonly, но `_stateMap` мутируемый → класс не thread-safe при расшаривании.

**7.5 [LOW] Публичное мутабельное поле.** `src/Stateless/Graph/Transition.cs:20` — `public List<ActionInfo> DestinationEntryActions = new List<ActionInfo>();` (поле, не свойство), мутируется из `StateGraph.ProcessOnEntryFrom` (`src/Stateless/Graph/StateGraph.cs:123, 157`).

**7.6 [LOW] `Reflection` дублирует логику распознавания поведений.** `src/Stateless/Reflection/StateInfo.cs:51-95` — две почти одинаковые ветки (sync/async) с 4 `is`-паттернами. `src/Stateless/Reflection/FixedTransitionInfo.Create` — два идентичных тела (`src/Stateless/Reflection/FixedTransitionInfo.cs:11-33`), различающихся только типом параметра. `ActionInfo.Create` (`:18-29`) — «instanceof-цепочка» по двум подклассам. Всё это хрупко: забыть ветку = тихая потеря данных в `GetInfo()`/графе. Именно так и сломалось недавно — коммит `974b848 fix(state-machine-info): include async triggers when getting state info` добавил недостающую async-ветку в `StateInfo.AddRelationships`.

**7.7 [LOW] Несогласованные метаданные `Timing`.** `PermitDynamicAsync` / `PermitDynamicIfAsync` создают `InvocationInfo` для селектора назначения **без** `Timing.Asynchronous` (`src/Stateless/StateConfiguration.Async.cs:548, 582, 1430`), тогда как все async-guard'ы, entry/exit/activate/deactivate — с ним (`src/Stateless/StateConfiguration.Async.cs:262, 277, 294, 311, 506, 521`). `InvocationInfo.IsAsync` (`src/Stateless/Reflection/InvocationInfo.cs:79`) для async-динамического селектора вернёт `false`.

---

## 8. Публичный API

**8.1 Плюсы:**
- Отличная XML-документация на уровне всего публичного API (`src/Stateless/Stateless.csproj:14`), `TreatWarningsAsErrors=true` (`:13`).
- Продуманный путь миграции: устаревшие `PermittedTriggers` / `GetPermittedTriggers` помечены `[Obsolete]` с указанием замены (`src/Stateless/StateMachine.cs:126, 132`) — вежливо, не ломает.
- `Transition` — иммутабельный value-объект с `IsReentry` (`src/Stateless/Transition.cs:25-68`); `InitialTransition` — тонкий наследник-маркер (`:8-20`), удачное решение.
- `InternalsVisibleTo` только для тестов, ключ задан (`src/Stateless/Properties/AssemblyInfo.cs:8-13`); `CLSCompliant(true)` (`:15`).
- Внешнее хранение состояния — полноценная опция, а не хак.

**8.2 Минусы:**
- **143 метода конфигурации** — поверхность, которую невозможно полностью выучить; `PermitDynamicIf` в 17 вариантах (`src/Stateless/StateConfiguration.cs:1308-1767`) легко перепутать, ошибку компилятор не поймает (все опциональные параметры в позиционных слотах, напр. `src/Stateless/StateConfiguration.cs:1355`).
- **Нет `CanFireAsync`** → см. 3.1.
- **Пробел `Ignore*Async`** → см. 4.2.1.
- **Нет способа снять/заменить поведение**; нет `Configure` → «заморозка».
- `ToString()` (`src/Stateless/StateMachine.cs:726-732`) делает `Task.Run(...).GetAwaiter().GetResult()` (строка 731) — **вызывает все guard-функции, включая async**, каждый раз, когда состояние пишется в лог. Побочный эффект в дебаг-выводе, плюс лишний thread-hop на каждый `ToString()`.
- `GetPermittedTriggers` (obsolete) — тоже `Task.Run(...).GetAwaiter().GetResult()` (`src/Stateless/StateMachine.cs:135`). `Task.Run` спасает от классического дедлока, но sync-over-async остаётся.
- `StateInfo.Transitions` возвращает `null` до вызова `AddRelationships` (`src/Stateless/Reflection/StateInfo.cs:166-173`) — nullable-контракт не отражён в типах (проект не использует `#nullable`).
- `StateConfiguration.Machine` (`src/Stateless/StateConfiguration.cs:33`) — утечка внутреннего API в builder.
- NuGet-метаданные: `AssemblyVersion` зафиксирован на `4.0.0.0` (`src/Stateless/Properties/AssemblyInfo.cs:6`) при `VersionPrefix` 5.20.1 — сбивает с толку при разрешении зависимостей.
- CI только на `windows-latest` (`.github/workflows/BuildAndTestOnPullRequests.yml:11`) при 5 целевых фреймворках, включая `net462` — Linux/`netstandard2.0`-специфичные регрессии не ловятся.
- Нулевые аннотации (`#nullable`) при `TreatWarningsAsErrors` — упущенная возможность сделать API контрактным.

---

## 9. Приоритизированные улучшения

### P0 — немедленно (исправляемо локально, ~1-2 дня)

| # | Что | Где |
|---|---|---|
| 1 | Передать unmet-guard'ы в async unhandled-обработчик: `foundHandler?.UnmetGuardConditions` вместо `null` + тест | `src/Stateless/StateMachine.Async.cs:219` |
| 2 | Убрать `ContinueWith` из sync-пути: сделать `DynamicTriggerBehaviourAsync` наследовать `TriggerBehaviourAsync` (с настоящим async-guard'ом) и `await`-ить; если sync-`Fire` не может его обработать — бросать синхронное `InvalidOperationException`, а не делать fire-and-forget | `src/Stateless/StateMachine.cs:424-435`, `src/Stateless/DynamicTriggerBehaviour.Async.cs:8`, `src/Stateless/StateConfiguration.Async.cs:1419-1424` |
| 3 | Добавить `CanFireAsync(...)` (в т.ч. overload `out unmetGuards`) и/или научить `CanFire` возвращать `true`, если триггер есть в `TriggerBehavioursAsync` | `src/Stateless/StateMachine.cs:595-720`, `src/Stateless/StateRepresentation.cs:48-59` |
| 4 | `RetainSynchronizationContext`: заменить `TaskScheduler.FromCurrentSynchronizationContext()` на безопасный фолбэк, и перестать «снимать» флаг в `StateRepresentation` (хранить ссылку на машину/делегат вместо `bool`-снимка) | `src/Stateless/StateMachine.Async.cs:313-315`, `src/Stateless/StateRepresentation.cs:12, 25-29` |
| 5 | `ProcessHandler`: использовать `source`/`representativeState`, уже вычисленные в `InternalFireOneAsync` (передать параметрами) | `src/Stateless/StateMachine.Async.cs:237-240` |

### P1 — ближайший релиз (1-2 недели)

| # | Что | Где |
|---|---|---|
| 6 | Убрать мутацию из «читающих» путей: `GetRepresentation` в режиме read-only (`TryGetValue`) для `CanFire`/`IsInState`/`GetPermittedTriggers*`; добавить отдельный `GetOrAddRepresentation` для `Configure`/`Fire` | `src/Stateless/StateMachine.cs:186-195` |
| 7 | Убрать `Task.Run` из `ToString()`; кэшировать или ограничить вычисление permitted-triggers (например, только sync-часть) | `src/Stateless/StateMachine.cs:726-732` |
| 8 | Добавить «заморозку» конфигурации: `Seal()`/автоматическая заморозка при первом `Fire`, чтобы `foreach` по коллекциям действий был безопасен | `src/Stateless/StateConfiguration.cs:18-23`, `src/Stateless/StateRepresentation.cs:222, 228` |
| 9 | Fail-fast на дубли: в `AddTriggerBehaviour`/`AddTriggerBehaviourAsync` проверять, не добавляется ли второй行为 с тем же триггером и пересекающимися guard'ами | `src/Stateless/StateRepresentation.cs:256-264`, `src/Stateless/StateRepresentation.Async.cs:135-143` |
| 10 | Выравнять `HandleReentryTrigger` и `HandleTransitioningTrigger`: общее состояние «когда писать `State`» + одинаковая пост-проверка | `src/Stateless/StateMachine.cs:469-514` |
| 11 | Короткое замыкание в `TryFindLocalHandler`/`TryFindLocalHandlerAsync`; не пере-вычислять guard'ы в `InternalAction` (передавать найденный `TriggerBehaviourResult` из вызывающего кода) | `src/Stateless/StateRepresentation.cs:61-83, 231-255`, `src/Stateless/StateRepresentation.Async.cs:204-235` |
| 12 | Задокументировать контракт чистоты guard'ов в XML-doc'ах `PermitIf*` / `CanFire` | `src/Stateless/StateConfiguration.cs:285-460` |

### P2 —中期 (1-2 месяца)

| # | Что |
|---|---|
| 13 | **Устранить дублирование действий**: ввести единый интерфейс `IExecutable<TContext> { void Execute(TContext); Task ExecuteAsync(TContext); }` и один generic-адаптер, вместо 6 иерархий (`EntryActionBehaviour.cs`, `ExitActionBehaviour.cs`, `ActivateActionBehaviour.cs`, `DeactivateActionBehaviour.cs`, `InternalTriggerBehaviour.cs`, `UnhandledTriggerAction.cs`). Синхронные подтипы реализуют только `ExecuteAsync => Execute(); return TaskResult.Done;` (уже есть рабочая схема в `src/Stateless/EntryActionBehaviour.cs:34-38`). Экономия ~250-300 строк и единая точка расширения. |
| 14 | **Разделить словари поведений на один** с тегом sync/async, либо ввести `TriggerBehaviourBase` как полноценный абстрактный класс с `ValueTask<ICollection<string>> UnmetGuardConditionsAsync(object[])` — устраняет двойную диспетчеризацию в `ProcessHandler` и `StateInfo.AddRelationships`. |
| 15 | **Разделить hot-path конфигурации и cold-path интроспекции**: `Reflection.StateInfo.AddRelationships` переписать в виде одного обхода с visitor'ом, вместо `is`-цепочек (`src/Stateless/Reflection/StateInfo.cs:51-95`); `FixedTransitionInfo.Create` — один общий метод. |
| 16 | **Явная модель очереди**: `SemaphoreSlim`/`Channel` + `TaskCompletionSource` на каждый запрос `FireAsync`, чтобы `await FireAsync` гарантировал завершения обработки даже при вложенных вызовах (`src/Stateless/StateMachine.Async.cs:177-201`). Это же даёт корректную thread-safety при `Interlocked`-семантике. |
| 17 | **`GetInfo()` без синтеза**: возвращать `StateInfo` для всех сконфигурированных состояний, а достижимость выражать через отдельный `IReadOnlyCollection<TState> UnconfiguredReachableStates`; `InitialState` брать из той же коллекции (устраняет расхождение идентичности, `src/Stateless/StateMachine.cs:160`). |
| 18 | `Graph`: ключевать состояния по `TState` (с `IEqualityComparer<TState>`), а не по `ToString()`; сделать `MermaidGraphStyle` stateless (иммутабельная карта, вычисляемая в конструкторе) — устраняет O(n²) и мутирующий `Get`. |

### P3 — долгосрочно

| # | Что |
|---|---|
| 19 | Опционально `#nullable enable` + `TreatWarningsAsErrors` (уже включён) → сделать nullable-контракт API явным (`StateInfo.Transitions` перестаёт быть `null`). |
| 20 | Ввести `IStateMachine` / `IStateMachineAsync` интерфейсы для сценариев с async-guard'ами (тесты через моки). |
| 21 | CI на `ubuntu-latest` + `macos-latest` (или хотя бы `windows` + `ubuntu`); покрытие `netstandard2.0` в smoke-тесте. |
| 22 | Обновить `AssemblyVersion` (`:6`) и комментарий «4.x series» — он устарел на мажорную версию. |
| 23 | Рассмотреть `record struct`/`readonly struct` для `Transition` и `InvocationInfo` (сейчас `class` с `private set` в `StateInfo`/`StateMachineInfo` — мутабельные DTO, `src/Stateless/Reflection/StateMachineInfo.cs:34, 40`). |

---

## 10. Что оставить как есть

- Иерархия состояний + проверки циклов в `SubstateOf` (`src/Stateless/StateConfiguration.cs:1128-1158`) — образцовая реализация.
- Стратегический подход к действиям (`Sync`/`Async`/`*From<T>` внутри одного класса) — правильная идея, просто не доведена до конца.
- Слой `Reflection` как чистый DTO-проект — правильное граничное решение.
- `GraphStyleBase` с `virtual`-методами по умолчанию — удачный extension point.
- `TaskResult.Done` и `ConfigureAwait(RetainSynchronizationContext)` сквозь весь async-код — хорошая инженерная культура, достойно сохранения при рефакторинге.
- Формализация неоднозначных конфигураций (`MultipleTransitionsPermitted`, `SelfTransitionsEitherIgnoredOrReentrant`) — отличная диагностика.

---

## 11. Итог

Библиотека решает свою задачу хорошо: концептуальная модель цельная, тестовое покрытие высокое (412 тестов), документация и примеры сильные. Основной технический долг — **не дизайн, а способ его выражения**: тотальное зеркалирование sync/async (~2/3 кода), из-за чего уже возникло 6+ поведенческих расхождений между путями, и отсутствие защиты от конкурентного/конфигурационного мутационного доступа, из-за чего «документированное» ограничение («single-threaded») на практике не проверяется и приводит к тихим, трудно-диагностируемым сбоям (`GetRepresentation` из `CanFire`, `ContinueWith` в sync-пути, `_firing` без синхронизации).

**Топ-3 действия с наибольшим отношением «эффект / усилие»:** (1) `StateMachine.Async.cs:219` — одна строка; (2) `StateMachine.cs:424-435` + `DynamicTriggerBehaviour.Async.cs:8` — устраняет fire-and-forget; (3) `GetRepresentation` в read-only режиме — устраняет неожиданную мутацию из «чистых» вызовов и делает документированный однопоточный контракт хотя бы наполовину проверяемым.