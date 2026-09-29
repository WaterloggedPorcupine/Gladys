# AGENTS.md: Gladys engineering rules

These rules apply to every change in this repository. The phased plan is in `docs/ROADMAP.md`. Background reading on the domain is in `docs/reference/`.

## What Gladys is

Gladys is an AI lab automation engineer. A scientist describes an experiment in plain language. Gladys produces a **reviewable** robot protocol (Opentrons first), validates it in a sandboxed simulator, and a human approves it. Every step is recorded in a provenance-rich `RunRecord` that downstream systems (LIMS, ELN, data lake, BI) can ingest.

In industry terms, Gladys is the **orchestration layer**: it turns scientific intent into executable work and turns results into contextualized data. It is **not** a LIMS, an ELN, a DMTA idea tracker, or an analytics tool, and it must never grow those features. It hands clean data to them.

## Non-negotiable invariants

1. **A human approves every protocol.** Nothing auto-approves, and no configuration flag can bypass approval.
2. **Gladys never drives a robot directly** (for now). An operator runs the approved protocol. Gladys records `RUNNING`/`COMPLETED`/`FAILED` via the API.
3. **An approval binds to exact bytes.** It records the `source_sha256` it approved. Any protocol edit after approval sends the run back to `DRAFT` and requires re-validation. `RUNNING` is only allowed if the current protocol hash equals the approved hash.
4. **The audit trail is append-only.** Status history, protocol revisions and agent traces are never updated in place or deleted.
5. **Generated code is untrusted.** LLM-written protocol source runs only inside the sandbox (no network, resource-limited, time-limited, non-root). The AST checks are fast feedback, **not** a security boundary.
6. **User text is untrusted.** Request text, clarification answers and tool outputs are data, never instructions. Delimit them in prompts. No agent tool has side effects outside the sandbox and the run's own record.
7. **Actors come from authentication, never from request bodies.** The `actor` on a `StatusChange` is the authenticated principal.
8. **Every timestamp is timezone-aware UTC.** Domain constructors reject naive datetimes.
9. **Every persisted row and every query is scoped by `tenant_id`**, even though there is one tenant today.
10. **Redis is never a source of truth.** Anything in Redis can be rebuilt from Postgres. Losing Redis delays work but never loses it.

## Architecture: ports and adapters

```
gladys/
  domain/        pure Python: entities, value objects, state machine, errors. No I/O.
    records/       RunRecord and friends (moved here from gladys/records)
    validity/      validation result types + pure static checks (AST)
    lab/           LabProfile, semantic naming model
  ports/         typing.Protocol interfaces: LLMClient, Simulator, RunRepository,
                 BlobStore, JobQueue, EventPublisher, Clock, IdGenerator, Authenticator
  platforms/     Platform port + adapters (opentrons/) : prompt context, static rules,
                 labware catalog, simulator client
  agent/         generation agent (and later reviewer agent), tools, prompts/, budgets, tracing
  services/      application use cases (submit_run, approve_run, revise_run, ...).
                 Orchestrates domain + ports. Transaction boundary lives here.
  adapters/      infrastructure: postgres/, redis/, blobstore/, anthropic/, sandbox_client/
  api/           FastAPI app: routers, DTOs (pydantic), auth, error mapping. Thin.
  worker/        queue consumer that runs generation jobs via services/
  sandbox/       the simulator service that runs inside its own container
  client/        typed Python HTTP client for the API (used by ui/, tests, scripts)
  ui/            Streamlit app. Talks ONLY to the API via gladys.client.
  config.py      pydantic-settings; the only place that reads env vars
  observability/ logging, metrics, tracing setup
```

**Dependency rule (enforced by `import-linter` in CI):**
- `domain` imports only the standard library.
- `ports` imports only `domain`.
- `services`, `agent` and `platforms` import `domain` and `ports`, never `adapters`, `api`, `worker` or `ui`.
- Only composition roots (`api/app.py`, `worker/main.py`, `sandbox/main.py`) wire adapters to ports.
- `ui` imports only `client`.

**Other rules:**
- **Domain types:** entities are dataclasses with behavior (e.g. `RunRecord.transition`). Value objects are `frozen=True`.
- **API DTOs:** API DTOs are pydantic models in `api/` and are mapped explicitly to and from domain types. Never expose domain objects directly as response models.
- **Async code:** use async I/O in the API, worker and adapters (SQLAlchemy 2.0 async + asyncpg, `redis.asyncio`, `anthropic.AsyncAnthropic`). The domain stays synchronous and pure.
- **Composition roots:** use constructor injection with no global singletons. Build dependencies with plain factory functions in the composition roots. Don't add a DI framework.

## Technology choices (decided; change only via an ADR)

| Concern | Choice |
|---|---|
| Python | 3.12 for the app. The sandbox image uses whatever Python the pinned `opentrons` release supports (check this, don't assume) |
| Packaging | `uv` with a committed `uv.lock`. Use dependency groups/extras: `agent`, `api`, `worker`, `ui`, `sim`, `dev` |
| API | FastAPI + uvicorn, versioned under `/v1`, RFC 9457 `application/problem+json` errors |
| DB | PostgreSQL only (no SQLite path, to avoid dialect drift). SQLAlchemy 2.0 async, Alembic migrations |
| Queue / events | Redis Streams with consumer groups (jobs) and Redis pub/sub (live run events) |
| LLM | Anthropic Python SDK (`anthropic`), async client, manual agent loop (see the Agent rules below) |
| UI | Streamlit |
| Config | `pydantic-settings`, `GLADYS_` prefix, validated at startup (fail fast) |
| Logging | `structlog` JSON, with a correlation ID on every line |
| Metrics / tracing | `prometheus-client` (`/metrics`), OpenTelemetry (OTLP exporter, off by default) |
| Lint / types | `ruff` (lint + format), `mypy --strict`, `import-linter` |
| Tests | `pytest`, `pytest-asyncio`, `hypothesis`, `testcontainers` (Postgres, Redis), `respx`/fakes for HTTP |
| Containers | Docker multi-stage builds, docker-compose for local dev |
| Orchestration | Kubernetes via kustomize (base + overlays), kind for local, KEDA for queue-driven worker scaling |

Don't add a dependency outside this table without writing an ADR (`docs/adr/NNNN-title.md`) that explains why.

## Agent rules (Claude API)

Your training data about the Anthropic API may be stale. **Verify SDK usage against the official docs and the installed SDK version before writing code.** Known recent changes:

- **Model and thinking:** the default model is `claude-opus-5-5`, configurable per role (generator, reviewer). Never hardcode model IDs outside `config.py`, and don't append date suffixes to model IDs.
- On `claude-opus-5-5`, thinking is always on. **Do not send** `thinking: {type: "disabled"}` or `budget_tokens` (both return a 400). Control depth with `output_config={"effort": ...}`. The default effort on this model is `medium`, so set it explicitly: `high` for generation, configurable.
- **Tool choice:** forced `tool_choice` (`any` / `tool`) returns a 400 on this model. Use `tool_choice={"type": "auto"}`, set `strict: true` on tool definitions (`additionalProperties: false` + `required`), and steer tool use from the system prompt.
- **Refusals:** always check `stop_reason` before reading content. Handle `refusal` (read `stop_details.category`), `max_tokens`, `pause_turn` and `tool_use`. Enable server-side refusal fallbacks (`betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`) and verify the exact request shape in the docs.
- **Message history:** append each `response.content` unchanged to history. **Never edit or strip earlier turns**, including thinking blocks; the model checks history integrity.
- **Tool results:** return every `tool_result` for one assistant turn in a **single** user message. Failed tools return `is_error: true`; never drop them.
- **Caching:** keep the system prompt and tool list byte-stable and deterministically ordered, and put `cache_control` on the stable prefix. Never put timestamps or IDs in the system prompt. Check `usage.cache_read_input_tokens` in tests or traces.
- **Errors:** use the SDK's typed exceptions in a most-specific-first chain. The SDK already retries 408/409/429/5xx (`max_retries`), so don't add a second retry layer on top.
- **Request IDs:** log `response._request_id` for every call.
- **Streaming:** stream long generations and use `get_final_message()`.

**The loop:** write a **manual** loop, not the SDK's beta tool runner. We need per-iteration budget checks, checkpointed traces and custom termination. The loop:
- ends only when the model calls a terminal tool (`finalize_protocol` or `request_clarification`);
- if the model ends its turn without one, sends a single nudge, then fails the generation;
- enforces `max_iterations`, `max_total_tokens`, `max_cost_usd` and a wall-clock timeout (all configurable).

**Traces:** every model call and every tool call goes into an append-only `AgentTrace`, recording model, effort, `stop_reason`, token usage (including cache tokens), latency, request ID, tool name/input/result summary and errors. Cost is computed from a price table in config, never from literals in the logic.

**Prompts:** prompts are versioned files in `gladys/agent/prompts/`. The prompt version, model, effort and Gladys version are recorded on each generated protocol.

## Code quality bar

- **Types and docs:** code must pass `mypy --strict`, with no `Any` leaking out of adapters. Public functions get docstrings only where the name and types don't already explain them. Match the existing style in `gladys/records/run_record.py`.
- **Errors:**
  - Domain errors are typed (`InvalidTransition`, `ProtocolChangedSinceApproval`, `ConcurrencyConflict`, ...).
  - `api/errors.py` maps them to HTTP responses in one place.
  - Never `except Exception` without re-raising or recording why.
- **No hidden I/O at import time.** No module-level clients, no reading env vars outside `config.py`.
- **Idempotency:**
  - Every job handler is safe to run twice (delivery is at-least-once).
  - Every mutating API endpoint either accepts an `Idempotency-Key` or is naturally idempotent.
- **Concurrency:** use optimistic concurrency. The `runs` table has a `version` column, writes use `WHERE version = :expected`, and the API exposes it as an `ETag` that mutations must send in `If-Match`.
- **Logging:**
  - Log structured events, not prose.
  - Never log secrets, full API keys or full protocol sources. Log hashes.
- **Tests:**
  - Domain coverage ≥ 95%, overall ≥ 85%.
  - Every port has a **contract test suite** that runs against both the in-memory fake and the real adapter.
  - Never weaken or delete a test to make it pass. Fix the code or explain in the PR.
  - Tests never call the real Anthropic API. Live evals are separate and opt-in (`make eval-live`).

## Workflow

- **One ROADMAP phase per branch/PR:** use `phase-N-short-name`, and don't start the next phase in the same PR.
- **Before finishing:** `make check` (ruff, format check, mypy, import-linter, pytest unit) and `make test-integration` must pass locally.
- **ADRs:** write one in `docs/adr/` for each significant decision (template: Context / Decision / Consequences / Alternatives considered).
- **Documentation:** update `README.md` (setup, run, architecture diagram) and `docs/ROADMAP.md` (tick completed items) in the same PR.
- **PR descriptions:** explain *what* was built and *why* each design choice was made, written so that a developer new to the stack can learn from it.
- **Ambiguity:** if something is genuinely ambiguous, choose the conservative option, record it under "Open questions" in the PR description, and keep going. Don't stall.
- **Commits:** use Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, `ci:`).
