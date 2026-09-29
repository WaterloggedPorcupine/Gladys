# ADR 0001: Ports-and-adapters package layout

## Context

Gladys must keep safety-critical lifecycle rules independent from web frameworks, databases, queues, robot platforms, and LLM vendors. It also needs replaceable infrastructure and fast domain tests.

## Decision

Use the package boundaries specified in `AGENTS.md`: pure types and behavior in `domain`, application-owned Protocol interfaces in `ports`, infrastructure in `adapters`, and wiring only in composition roots. Keep `gladys.records` and `gladys.validity` as compatibility re-exports while callers migrate. Enforce dependencies with import-linter.

## Consequences

The domain runs without third-party dependencies and infrastructure can be replaced through contract-tested ports. Mapping code is explicit. There are more packages and adapters cannot be imported directly by application logic.

## Alternatives considered

- A conventional layered application was rejected because infrastructure dependencies can leak inward.
- A DI framework was rejected because constructor injection and small composition functions are sufficient.
- Removing old import paths immediately was rejected because it would needlessly break schema 0.2 callers.
