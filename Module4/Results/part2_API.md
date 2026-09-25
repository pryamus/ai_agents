Провёл только статический read-only анализ. Файлы не изменял; сборку и тесты не запускал, поскольку они создают `bin/obj`.

## Краткий вывод

Stateless — компактная и достаточно зрелая state-machine библиотека с хорошим fluent API, внешним хранением состояния, широкой поддержкой sync/async, иерархических состояний, параметризованных триггеров и introspection/graph export. Runtime-зависимостей нет.

Главные риски:

1. `Fire()` с асинхронным dynamic-transition запускает продолжение fire-and-forget.
2. Заявленная идемпотентность `Activate/Deactivate` не реализована.
3. Async-обработчики имеют непоследовательный приоритет и теряют unmet guard descriptions.
4. `RetainSynchronizationContext` реализован непоследовательно.
5. Экземпляр не thread-safe, причём некоторые «read»-операции изменяют внутреннюю конфигурацию.
6. Публичная introspection-модель допускает `null` там, где API выглядит как полноценная коллекция.
7. Публичные API плохо защищены от случайных breaking changes.

---

# 1. Публичный API

## Основной API

Ядро сосредоточено в `StateMachine<TState, TTrigger>`:

- конструкторы с internal/external state и `FiringMode`: [`StateMachine.cs:46-90`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L46-L90);
- `State`, `Configure`, `Fire/FireAsync`, `CanFire`, `IsInState`, activation: [`StateMachine.cs:111-121`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L111-L121), [`StateMachine.cs:197-329`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L197-L329);
- permitted triggers и подробная introspection: [`StateMachine.cs:123-158`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L123-L158);
- unhandled triggers, transition events, unregister: [`StateMachine.cs:550-570`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L550-L570), [`StateMachine.cs:802-859`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L802-L859);
- async API: [`StateMachine.Async.cs:16-148`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.Async.cs#L16-L148), [`StateMachine.Async.cs:406-475`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.Async.cs#L406-L475).

`StateConfiguration` предоставляет fluent-меты для:

- обычных, guarded, reentry, ignored, internal и dynamic transitions;
- `OnEntry/OnExit/OnActivate/OnDeactivate`, sync и async;
- `SubstateOf` и `InitialTransition`.

Пример основной поверхности: [`StateConfiguration.cs:35-73`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateConfiguration.cs#L35-L73), [`StateConfiguration.cs:1116-1188`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateConfiguration.cs#L1116-L1188), [`StateConfiguration.Async.cs:493-553`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateConfiguration.Async.cs#L493-L553).

## Параметризованные триггеры

`TriggerWithParameters` и типизированные варианты до трёх аргументов дают compile-time безопасные delegates:

- [`TriggerWithParameters.cs:11-47`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/TriggerWithParameters.cs#L11-L47);
- [`TriggerWithParameters.cs:50-99`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/TriggerWithParameters.cs#L50-L99).

Для произвольной арности существует не типизированный `SetTriggerParameters(TTrigger, params Type[])`: [`StateMachine.cs:238-250`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L238-L250).

## Introspection и graph API

Публично доступны:

- `StateMachineInfo`, `StateInfo`, `TransitionInfo`, `ActionInfo`, `InvocationInfo`;
- `StateGraph`, `GraphStyleBase`, DOT/Mermaid formatters;
- публичные mutable-модели `State`, `Transition`, `Decision`.

`GraphStyleBase` является реальной точкой расширения: [`GraphStyleBase.cs:11-26`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/GraphStyleBase.cs#L11-L26).

## Случайно публичный API

`StateMachineResources` сделан `public`, в отличие от остальных resource-классов, и предоставляет глобально изменяемый `Culture`:

- [`StateMachineResources.Designer.cs:25-59`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachineResources.Designer.cs#L25-L59);
- для сравнения, `StateConfigurationResources` и другие internal: [`StateConfigurationResources.Designer.cs:23-53`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateConfigurationResources.Designer.cs#L23-L53).

Это выглядит как случайная утечка generated API, а не осознанная часть библиотеки.

---

# 2. Generic design

## Сильные стороны

- Два type parameters без искусственных constraints позволяют использовать enum, string, числа и reference objects: [`StateMachine.cs:20-28`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L20-L28).
- Состояние можно либо хранить внутри машины, либо передать accessor/mutator: [`StateMachine.cs:46-90`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L46-L90).
- Типизированные `TriggerWithParameters<TArg...>` сохраняют тип до трёх аргументов.
- Sync/async API симметричны для guards, actions, entry/exit и dynamic transitions.

## Проблемы

### 1. Generic keys требуют неявных контрактов

Используются обычные `Dictionary<TState,...>` и `Dictionary<TTrigger,...>`: [`StateMachine.cs:27-28`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L27-L28).

Отсюда:

- `null` не поддерживается Dictionary, хотя документация говорит о состояниях «any .NET type»: [`README.md:28-36`](/home/user/ai_course/ai_agents/Module4/stateless/README.md#L28-L36);
- изменение hash/equality у mutable state или trigger делает состояние недоступным после `Configure`;
- иерархия отдельно полагается на `Equals`: [`StateConfiguration.cs:1128-1157`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateConfiguration.cs#L1128-L1157).

**Рекомендация:** явно определить null/equality semantics: либо отклонять `null` с понятным `ArgumentNullException`, либо полноценно поддержать его. Документировать требование стабильного `Equals/GetHashCode`; при необходимости добавить optional comparer.

### 2. После трёх аргументов generic safety теряется

Типизированные trigger-классы заканчиваются на arity 3: [`TriggerWithParameters.cs:54-99`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/TriggerWithParameters.cs#L54-L99). Произвольная арность доступна только через `Type[]/object[]`, что подтверждается тестом с пятью аргументами: [`AsyncActionsFixture.cs:609-631`](/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/AsyncActionsFixture.cs#L609-L631).

**Рекомендация:** либо добавить арность 4–5, либо ввести tuple/value-based trigger API. Текущий API следует оставить для совместимости.

### 3. Introspection теряет generic type information

`StateInfo.UnderlyingState` и `TriggerInfo.UnderlyingTrigger` имеют тип `object`: [`StateInfo.cs:128-136`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Reflection/StateInfo.cs#L128-L136), [`TriggerInfo.cs:13-23`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Reflection/TriggerInfo.cs#L13-L23).

Graph API дополнительно ключует состояния по `ToString()`: [`StateGraph.cs:19-27`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/StateGraph.cs#L19-L27), [`State.cs:51-55`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/State.cs#L51-L55).

Два разных значения с одинаковым `ToString()` могут перезаписать друг друга.

**Рекомендация:** добавить generic overlay `StateMachineInfo<TState,TTrigger>`, а для graph использовать object-based map и отдельно генерировать уникальные textual IDs.

### 4. Публичные конструкторы `TriggerWithParameters` допускают bypass validation

Конструкторы wrapper-типов публичны: [`TriggerWithParameters.cs:21-24`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/TriggerWithParameters.cs#L21-L24). Однако `Fire` проверяет аргументы только по глобальному словарю машины: [`StateMachine.cs:392-398`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L392-L398).

Wrapper, созданный вручную и не зарегистрированный через `SetTriggerParameters`, пройдёт без `ValidateParameters`.

**Рекомендация:** `Fire(TriggerWithParameters, ...)` должен всегда валидировать сам переданный wrapper.

---

# 3. Target frameworks и зависимости

## Сильные стороны

- Поддерживаются `netstandard2.0`, `net462`, `net8.0`, `net9.0`, `net10.0`: [`Stateless.csproj:3-12`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Stateless.csproj#L3-L12).
- Runtime-зависимостей нет.
- Единственный `PackageReference` — SourceLink с `PrivateAssets="All"`, то есть build-time dependency: [`Stateless.csproj:45-47`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Stateless.csproj#L45-L47).
- Включены strong naming, CLS compliance, XML docs, warnings-as-errors и symbols: [`Stateless.csproj:13-30`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Stateless.csproj#L13-L30).

`Newtonsoft.Json 13.0.1` используется только примером и не является зависимостью пакета: [`JsonExample.csproj:8-14`](/home/user/ai_course/ai_agents/Module4/stateless/example/JsonExample/JsonExample.csproj#L8-L14).

## Проблемы и рекомендации

- `net8.0`, `net9.0`, `net10.0` компилируются из одного исходника без видимого conditional compilation; константа `TASKS` объявлена, но не используется: [`Stateless.csproj:33-35`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Stateless.csproj#L33-L35). Следует документировать, почему нужны все три asset-файла; при отсутствии различий можно сократить число TFM.
- Тесты не запускаются на `net10.0`: [`Stateless.Tests.csproj:3-7`](/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/Stateless.Tests.csproj#L3-L7). Стоит добавить `net10.0`.
- Утверждение «Visual Studio 2017 or later» несовместимо с требованием SDK для `net10.0`: [`README.md:361-364`](/home/user/ai_course/ai_agents/Module4/stateless/README.md#L361-L364).
- Нет `global.json`, lock file и package validation. Это снижает воспроизводимость и затрудняет контроль совместимости пакета.

---

# 4. Thread safety и внешнее состояние

## Что сделано хорошо

- Ограничение явно документировано: машина не должна использоваться конкурентно: [`README.md:328-346`](/home/user/ai_course/ai_agents/Module4/stateless/README.md#L328-L346).
- `Queued` mode реализует reentrant run-to-completion через `_firing` и FIFO queue: [`StateMachine.cs:352-383`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L352-L383).
- Guards рекомендуется делать side-effect free: [`README.md:132-135`](/home/user/ai_course/ai_agents/Module4/stateless/README.md#L132-L135).

## Проблемы

### 1. Нет потокобезопасности и нет защиты от неверного использования

Все основные структуры — обычные `Dictionary`, `List`, `Queue`, а `_firing` — обычный `bool`: [`StateMachine.cs:27-44`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L27-L44).

Даже без явного запрета возможны:

- corruption/interleaving `Dictionary` и `Queue`;
- `InvalidOperationException` при изменении коллекции во время `foreach`;
- применение handler, выбранного для одного state, к уже изменённому state.

**Рекомендация:** сохранить текущий non-thread-safe контракт, но:

- перенести его в XML remarks класса и каждой изменяющей операции;
- запретить или диагностировать `Configure` после начала firing;
- рассмотреть отдельный `SynchronizedStateMachine` wrapper;
- добавить concurrent stress tests sync/async.

Автоматически добавлять обычный `lock` вокруг всего объекта не стоит: callbacks могут быть reentrant и async.

### 2. Read-like API изменяет внутреннее состояние

`CurrentRepresentation` вызывает `GetRepresentation`, а тот при отсутствии state добавляет его в `_stateConfiguration`: [`StateMachine.cs:147-153`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L147-L153), [`StateMachine.cs:186-195`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L186-L195).

Следовательно, `CanFire`, `IsInState` и permitted-trigger queries могут изменять конфигурацию и вызывать guards.

**Рекомендация:** read-only операции должны использовать `TryGetValue`; создание временного representation допустимо только без добавления в основной dictionary.

### 3. Внешнее состояние ограничено только значением state

Accessor/mutator — хороший extensibility point, но наружу не вынесены:

- graph configuration;
- callbacks;
- trigger parameter metadata;
- queued events;
- activation state;
- initial-transition metadata.

Поэтому persistence означает только сохранение `TState`, а не сериализацию машины. Следует явно документировать этот контракт и требования к accessor/mutator: синхронные, быстрые, не reentrant, стабильные.

---

# 5. Наиболее серьёзные проблемы реализации

## P0. Sync `Fire()` запускает async dynamic transition fire-and-forget

`DynamicTriggerBehaviourAsync` хранится среди sync behaviours, поэтому sync `Fire` может выбрать его и запустить `ContinueWith`, не ожидая результат:

[`StateMachine.cs:424-433`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L424-L433).

Последствия:

- `Fire()` возвращается до вычисления destination и входа в state;
- queued triggers могут быть обработаны раньше async transition;
- исключения destination selector/handlers могут стать unobserved;
- порядок transition callbacks больше не гарантирован.

**Рекомендация:** synchronous `Fire` должен немедленно выбрасывать `InvalidOperationException` для `DynamicTriggerBehaviourAsync`; для этой конфигурации требовать `FireAsync`. Добавить тест на synchronously valid `PermitDynamicAsync`.

## P0. `Activate/Deactivate` не идемпотентны

XML documentation утверждает идемпотентность: [`StateMachine.cs:309-329`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L309-L329).

Но `StateRepresentation.Activate/Deactivate` каждый раз заново выполняют actions, не имея active flag: [`StateRepresentation.cs:145-170`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateRepresentation.cs#L145-L170). Async-версия также не хранит состояние: [`StateRepresentation.Async.cs:47-72`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateRepresentation.Async.cs#L47-L72).

Тест с названием `WhenActivateIsIdempotent` вызывает `Activate()` только один раз и потому не проверяет идемпотентность: [`ActiveStatesFixture.cs:35-52`](/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/ActiveStatesFixture.cs#L35-L52).

**Рекомендация:** определить ожидаемую state-machine activation semantics и реализовать per-state activation state; либо убрать idempotence claim. Это behavioral change, поэтому для исправления нужен release plan.

## P0. Sync/async handlers имеют непоследовательный приоритет

Sync и async handlers хранятся в разных словарях: [`StateRepresentation.cs:14-18`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateRepresentation.cs#L14-L18), [`StateRepresentation.Async.cs:12-13`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateRepresentation.Async.cs#L12-L13).

`TryFindLocalHandlerAsync` выбирает sync result раньше async result и не проверяет, что оба одновременно допустимы: [`StateRepresentation.Async.cs:204-235`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateRepresentation.Async.cs#L204-L235).

В sync path несколько одновременно разрешённых переходов приводят к exception: [`StateRepresentation.cs:85-96`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateRepresentation.cs#L85-L96). В async path sync transition может молча победить async transition для того же trigger.

**Рекомендация:** объединять sync/async candidates и применять ту же mutual-exclusivity проверку. Если sync-wins намеренный, это нужно явно документировать и тестировать.

## P0. Async unhandled trigger теряет unmet guard descriptions

Sync path передаёт descriptions: [`StateMachine.cs:403-407`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L403-L407).

Async path всегда передаёт `null`: [`StateMachine.Async.cs:214-221`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.Async.cs#L214-L221).

**Рекомендация:** передавать `foundHandler?.UnmetGuardConditions`; добавить async-аналог `CanFireAsync`, возвращающий unmet guards.

## P1. `RetainSynchronizationContext` реализован частично

Часть кода использует `ConfigureAwait(RetainSynchronizationContext)`, но async guards и dynamic selector используют обычный `await`:

- [`TransitionGuard.async.cs:101-129`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/TransitionGuard.async.cs#L101-L129);
- [`DynamicTriggerBehaviour.Async.cs:21-24`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/DynamicTriggerBehaviour.Async.cs#L21-L24).

Дополнительно:

- `RetainSynchronizationContext` изменяем после создания, но `StateRepresentation` захватывает значение только в конструкторе: [`StateMachine.cs:93-96`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L93-L96), [`StateRepresentation.cs:11-29`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateRepresentation.cs#L11-L29);
- sync internal action использует `FromCurrentSynchronizationContext()`, который бросает exception при отсутствии current context: [`StateMachine.Async.cs:305-318`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.Async.cs#L305-L318).

**Рекомендация:** сделать настройку immutable, централизовать continuation policy и одинаково применять её к guards, selectors, actions, events и permitted-trigger queries.

---

# 6. Introspection и мутабельность публичных объектов

## P1. `InitialState` — неполный `StateInfo`

`GetInfo()` создаёт отдельный `StateInfo` для initial state, но не вызывает `AddRelationships`: [`StateMachine.cs:158-183`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L158-L183).

Поэтому `InitialState.Transitions`, `Substates`, `FixedTransitions` и другие relationship properties могут быть `null`: [`StateInfo.cs:128-183`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Reflection/StateInfo.cs#L128-L183).

Текущий тест даже фиксирует `Transitions == null`: [`StateInfoTests.cs:8-23`](/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/StateInfoTests.cs#L8-L23).

**Рекомендация:** повторно использовать `StateInfo` из `States` для `InitialState`; все коллекционные properties должны быть непустыми, желательно read-only.

## P1. Публичные структуры допускают скрытую мутацию

- `Transition.Parameters` возвращает исходный `object[]`: [`Transition.cs:34-39`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Transition.cs#L34-L39), [`Transition.cs:62-68`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Transition.cs#L62-L68).
- `TriggerWithParameters.ArgumentTypes` возвращает внутренний массив: [`TriggerWithParameters.cs:21-30`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/TriggerWithParameters.cs#L21-L30).
- `TransitionInfo.GuardConditionsMethodDescriptions` — публичное mutable field: [`TransitionInfo.cs:15-24`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Reflection/TransitionInfo.cs#L15-L24).
- Graph DTO публично содержат изменяемые lists и fields: [`Transition.cs:15-25`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/Transition.cs#L15-L25).

**Рекомендация:** defensive copies и snapshots. Для будущих API добавить `IReadOnlyList<T>`; существующие свойства оставить для binary compatibility.

## Глобальное состояние

`InvocationInfo.DefaultFunctionDescription` — изменяемое process-wide static property: [`InvocationInfo.cs:45-72`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Reflection/InvocationInfo.cs#L45-L72). В сочетании с публичным `StateMachineResources.Culture` это создаёт глобальное изменяемое состояние без thread-safety.

**Рекомендация:** добавить per-machine/per-info override; глобальные defaults оставить только как read-only defaults.

---

# 7. Naming и backward compatibility

## Сильные стороны

- Основные имена `Permit`, `PermitIf`, `PermitReentry`, `Ignore`, `InternalTransition` последовательны и выразительны.
- Старые permitted-trigger APIs сохранены и помечены obsolete: [`StateMachine.cs:123-136`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L123-L136).
- Assembly/package/product naming согласованы: [`Stateless.csproj:3-7`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Stateless.csproj#L3-L7).
- CHANGELOG достаточно подробно описывает migration-impact.

## Проблемы

- `InternalTransitionAsyncIf` имеет неестественный порядок слов и отличается от `PermitIfAsync`: [`StateConfiguration.Async.cs:19-25`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateConfiguration.Async.cs#L19-L25).
- `OnTransitionedAsyncUnregister` лучше читался бы как `UnregisterOnTransitionedAsync`: [`StateMachine.Async.cs:453-475`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.Async.cs#L453-L475).
- `UnregisterAllCallbacks` очищает только transition events, но не unhandled-trigger или configuration callbacks: [`StateMachine.cs:851-859`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs#L851-L859).
- `Stateless` концептуально неточно для default/internal-state и configuration-heavy реализации; README это признаёт: [`README.md:371-377`](/home/user/ai_course/ai_agents/Module4/stateless/README.md#L371-L377). Переименовывать пакет не следует, но описание можно уточнить.
- README всё ещё рекомендует obsolete `PermittedTriggers`: [`README.md:112-115`](/home/user/ai_course/ai_agents/Module4/stateless/README.md#L112-L115).

## Реальный compatibility risk

В `GraphStyleBase` в minor release 5.15.0 добавлен новый abstract method. Текущий API требует его реализации: [`GraphStyleBase.cs:21-26`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/GraphStyleBase.cs#L21-L26), а changelog прямо признаёт необходимость миграции: [`CHANGELOG.md:60-65`](/home/user/ai_course/ai_agents/Module4/stateless/CHANGELOG.md#L60-L65). Это source- и binary-breaking изменение для публичного extensibility point в minor версии.

Дополнительно пакет 5.20.1 имеет `AssemblyVersion 4.0.0.0`: [`Stateless.csproj:11-12`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Stateless.csproj#L11-L12), [`AssemblyInfo.cs:5-6`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Properties/AssemblyInfo.cs#L5-L6). Это может быть намеренной binary compatibility мерой, но смешивает 4.x и 5.x под одной assembly identity и скрывает behavioral boundary версии 5.

**Рекомендации:**

- добавить `PublicAPI.Shipped/Unshipped.txt`, API analyzer и package validation;
- сравнивать API текущей версии с последней стабильной через ApiCompat;
- новые abstract members заменять virtual methods с default implementation;
- исправления добавлять через новые API, старые оставлять obsolete минимум на один major;
- assembly identity и strategy пересмотреть только на majors, документировав binding implications.

---

# 8. Качество тестов

Есть 19 xUnit tests с `async void`, вместо `async Task`. Например:

- [`StateMachineFixture.cs:1054-1064`](/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/StateMachineFixture.cs#L1054-L1064);
- [`AsyncFiringModesFixture.cs:160-203`](/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/AsyncFiringModesFixture.cs#L160-L203);
- [`DynamicAsyncTriggerBehaviourFixture.cs:9-18`](/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/DynamicAsyncTriggerBehaviourFixture.cs#L9-L18).

Это ухудшает обнаружение ошибок и может пропускать незавершённые async tests.

Приоритетные тесты:

1. sync `Fire` с `PermitDynamicAsync`;
2. sync и async handlers одного trigger;
3. unmet guard descriptions в `FireAsync`;
4. два последовательных `Activate/Deactivate`;
5. `RetainSynchronizationContext` вокруг async guards и dynamic selector;
6. concurrent/reentrant sync+async calls;
7. mutable keys, `null` states и одинаковый `ToString()` в graph;
8. `InitialState.Transitions` никогда не `null`.

## Итоговый приоритет

**P0:** fire-and-forget async transition, activation semantics, async handler precedence/unmet guards, synchronization context.

**P1:** non-mutating query API, полноценный `InitialState`, defensive copies, global static state, generic null/key semantics.

**P2:** public API baseline, GraphStyle compatibility, TFM/test matrix, naming aliases и обновление документации.