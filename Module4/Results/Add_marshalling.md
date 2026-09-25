Если под **marshalling** ты имеешь в виду сериализацию и сохранение состояния, то в самом `Stateless` этого нет: есть только `Func<TState>/Action<TState>` и отдельный JSON-пример.

Ближайшие:
- [Workflow Core](https://github.com/danielgerlag/workflow-core) — pluggable persistence, SQL/Mongo/Redis и сериализация workflow.
- [Elsa](https://github.com/elsa-workflows/elsa-core) — workflow persistence с EF Core/Mongo/Dapper.
- [Orleans](https://github.com/dotnet/orleans) — сериализация и durable state grains.
- [MassTransit](https://github.com/MassTransit/MassTransit) — serializers и persistence для сообщений/saga.

Для `Stateless` ближе всего Workflow Core; Orleans полезен как образец надёжной распределённой persistence.