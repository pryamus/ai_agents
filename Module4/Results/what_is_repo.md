## Краткий вывод

Это upstream-проект [`dotnet-state-machine/stateless`](https://github.com/dotnet-state-machine/stateless) — C#/.NET-библиотека и NuGet-пакет `Stateless` для создания конечных автоматов и небольшого workflow прямо в коде. Это не веб-сервис и не самостоятельное приложение: основная поставка — библиотека, а запускаются отдельные примеры.

Назначение подтверждается README: «Create state machines and lightweight state machine-based workflows directly in .NET code» ([`/home/user/ai_course/ai_agents/Module4/stateless/README.md:3-4`](/home/user/ai_course/ai_agents/Module4/stateless/README.md:3)).

Версия библиотеки — `5.20.1`; лицензия Apache 2.0 ([`/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Stateless.csproj:7-23`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Stateless.csproj:7), [`/home/user/ai_course/ai_agents/Module4/stateless/LICENSE:1-3`](/home/user/ai_course/ai_agents/Module4/stateless/LICENSE:1)).

## Назначение и возможности

Основной API — универсальный `StateMachine<TState, TTrigger>`:

- настройка переходов через fluent-методы `Configure(...).Permit(...)`, `PermitIf(...)`, `Ignore(...)`;
- иерархические состояния через `SubstateOf(...)`;
- entry/exit/activation/deactivation actions;
- guard-условия для условных переходов;
- внутренние переходы, re-entry и динамически вычисляемое состояние назначения;
- типизированные параметры триггеров через `SetTriggerParameters<TArg...>`;
- `Fire()` и `FireAsync()`, включая асинхронные guards/actions;
- события перехода и завершения перехода, включая отписку;
- внешнее хранение текущего состояния через `Func<TState>`/`Action<TState>`.

Это видно в API ядра ([`/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs:25-35`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs:25), [`:47-91`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs:47), [`:203-236`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs:203)) и конфигураторе состояний ([`/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateConfiguration.cs:42-72`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateConfiguration.cs:42), [`:1117-1157`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateConfiguration.cs:1117), [`:1812-1823`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateConfiguration.cs:1812)).

Название `Stateless` означает, что библиотека не обязана сама хранить состояние: его можно передать внешнему хранилищу/ORM-свойству через accessor и mutator. При этом сама машина хранит конфигурацию состояний и поведение.

## Структура и основные компоненты

- [`/home/user/ai_course/ai_agents/Module4/stateless/Stateless.sln:14-39`](/home/user/ai_course/ai_agents/Module4/stateless/Stateless.sln:14) — корневое решение с библиотекой, тестами и пятью примерами.
- [`/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/) — исходники библиотеки:
  - [`StateMachine.cs`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs) и [`StateMachine.Async.cs`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.Async.cs) — синхронный и асинхронный циклы обработки триггеров;
  - [`StateConfiguration.cs`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateConfiguration.cs) и async-часть — fluent-конфигурация состояний;
  - [`StateRepresentation.cs`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateRepresentation.cs) и async-часть — хранение поведения состояний, иерархия, entry/exit actions, поиск handlers;
  - классы `TriggerBehaviour*`, `TransitioningTriggerBehaviour`, `InternalTriggerBehaviour`, `DynamicTriggerBehaviour`, `ReentryTriggerBehaviour`, `TransitionGuard*` — переходы, guards и параметры;
  - [`ParameterConversion.cs`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/ParameterConversion.cs) и [`TriggerWithParameters.cs`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/TriggerWithParameters.cs) — проверка и распаковка аргументов триггеров.
- [`/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/) — построение графов:
  - [`StateGraph.cs:39-98`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/StateGraph.cs:39);
  - [`UmlDotGraph.cs:8-20`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/UmlDotGraph.cs:8) — DOT;
  - [`MermaidGraph.cs:9-24`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Graph/MermaidGraph.cs:9) — Mermaid.
- [`/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Reflection/`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Reflection/) — модель introspection-данных: `StateMachineInfo`, `StateInfo`, описания переходов и actions. `GetInfo()` формирует эту модель ([`/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs:155-184`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/StateMachine.cs:155)).
- [`/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/`](/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/) — xUnit-тесты для синхронной/асинхронной логики, guards, иерархий, параметров, reflection и генерации графов.
- [`/home/user/ai_course/ai_agents/Module4/stateless/example/`](/home/user/ai_course/ai_agents/Module4/stateless/example/) — примеры:
  - `TelephoneCallExample` — телефонный звонок, параметризованные триггеры, внутренние действия и DOT-граф ([`PhoneCall.cs:42-72`](/home/user/ai_course/ai_agents/Module4/stateless/example/TelephoneCallExample/PhoneCall.cs:42));
  - `OnOffExample` — интерактивный переключатель ([`Program.cs:24-65`](/home/user/ai_course/ai_agents/Module4/stateless/example/OnOffExample/Program.cs:24));
  - `JsonExample` — сериализация состояния через Newtonsoft.Json ([`Member.cs:21-80`](/home/user/ai_course/ai_agents/Module4/stateless/example/JsonExample/Member.cs:21));
  - `BugTrackerExample` — workflow бага с re-entry и параметрами ([`Bug.cs:29-69`](/home/user/ai_course/ai_agents/Module4/stateless/example/BugTrackerExample/Bug.cs:29));
  - `AlarmExample` — интерактивная сигнализация с временными состояниями и таймерами ([`Alarm.cs:86-140`](/home/user/ai_course/ai_agents/Module4/stateless/example/AlarmExample/Alarm.cs:86)).

## Manifests и зависимости

- [`/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Stateless.csproj:7-23,45-50`](/home/user/ai_course/ai_agents/Module4/stateless/src/Stateless/Stateless.csproj:7) — targets: `netstandard2.0`, `net462`, `net8.0`, `net9.0`, `net10.0`; единственная внешняя зависимость — `Microsoft.SourceLink.GitHub 1.1.1`.
- [`/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/Stateless.Tests.csproj:6,22-31`](/home/user/ai_course/ai_agents/Module4/stateless/test/Stateless.Tests/Stateless.Tests.csproj:6) — targets `net462`, `net8.0`, `net9.0`; зависимости `Microsoft.NET.Test.Sdk`, xUnit и runner/analyzers.
- Все примеры настроены на `net10.0`; [`/home/user/ai_course/ai_agents/Module4/stateless/example/JsonExample/JsonExample.csproj:4-14`](/home/user/ai_course/ai_agents/Module4/stateless/example/JsonExample/JsonExample.csproj:4) дополнительно использует `Newtonsoft.Json 13.0.1`.
- `package.json`, `pyproject.toml`, `requirements.txt`, `Dockerfile`, `Makefile`, `global.json` и центрального package-lock-файла в репозитории нет; dependency management основан на `.csproj`.
- CI описан в [`/home/user/ai_course/ai_agents/Module4/stateless/.github/workflows/BuildAndTestOnPullRequests.yml:9-44`](/home/user/ai_course/ai_agents/Module4/stateless/.github/workflows/BuildAndTestOnPullRequests.yml:9): Windows runner, SDK .NET 8/9/10, restore/build/test, затем упаковка и публикация NuGet.

## Запуск

Из корня репозитория:

```bash
dotnet restore /home/user/ai_course/ai_agents/Module4/stateless/Stateless.sln
dotnet build /home/user/ai_course/ai_agents/Module4/stateless/Stateless.sln --configuration Release --no-restore
dotnet test /home/user/ai_course/ai_agents/Module4/stateless/Stateless.sln --no-restore --no-build --configuration Release
```

Примеры запускаются отдельно, например:

```bash
dotnet run --project /home/user/ai_course/ai_agents/Module4/stateless/example/OnOffExample/OnOffExample.csproj
dotnet run --project /home/user/ai_course/ai_agents/Module4/stateless/example/AlarmExample/AlarmExample.csproj
dotnet run --project /home/user/ai_course/ai_agents/Module4/stateless/example/TelephoneCallExample/TelephoneCallExample.csproj
```

`OnOffExample` ожидает клавишу пробела для переключения, `AlarmExample` — текстовые команды, а `TelephoneCallExample` выполняет сценарий и затем ожидает нажатия клавиши.

В текущем окружении команда `dotnet` не установлена (`dotnet: command not found`), поэтому фактическую сборку/запуск я не проверял. Рабочее дерево не изменено; `git status` остаётся чистым.