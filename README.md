# Gladys

Gladys is an AI lab automation engineer: a scientist describes an experiment, Gladys produces a reviewable robot protocol, validates it in a sandbox, and a human approves the exact protocol bytes. Gladys is an orchestration layer, not a LIMS or ELN.

Phase 0 supplies the production-shaped foundation: a pure schema 0.4 domain with an append-only run aggregate, ports and adapters, content-addressed protocol storage, async PostgreSQL persistence, validated configuration, JSON logging, metrics helpers, and enforced architecture boundaries. It does not call an LLM or control a robot.

## Architecture

```text
scientific intent
      |
      v
 services / agent / platforms  --->  domain + ports
      |                                  ^
      v                                  |
 API / worker composition roots ---> adapters (Postgres, tenant-scoped blob stores)
      |
      v
 client ---> UI
```

`gladys.domain` is pure Python. `gladys.ports` defines interfaces owned by the application. Infrastructure implements those interfaces under `gladys.adapters`. Composition roots will wire them in later phases. Import-linter checks these boundaries in CI.

## Setup

Install [uv](https://docs.astral.sh/uv/), then:

```powershell
Copy-Item .env.example .env
uv sync --locked
```

The application requires Python 3.12; uv installs it when needed.

`uv sync` installs the `dev` dependency group, which includes every adapter's libraries. Deployable images install only what they need:

| Install | Contents |
|---|---|
| `gladys` (no extras) | `domain`, `ports`, `config`, `observability`: pydantic, pydantic-settings, structlog, prometheus-client |
| `gladys[postgres]` | adds SQLAlchemy (async), asyncpg and Alembic |
| `agent`, `api`, `worker`, `ui`, `sim` | placeholders, filled in by the phase that first needs them |

CI's `core-install` job checks that the no-extras install imports cleanly without any database library. Configuration uses `GLADYS_` variables and `__` for nested values, such as `GLADYS_DATABASE__URL`.

## Development commands

GNU Make is convenient on Unix. The equivalent plain uv commands work in PowerShell:

| Task | Make | Plain uv equivalent |
|---|---|---|
| All local checks | `make check` | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy`; `uv run lint-imports`; `uv run pytest -m "not integration"` |
| Unit tests | `make test` | `uv run pytest -m "not integration"` |
| Integration tests | `make test-integration` | `$env:GLADYS_REQUIRE_INTEGRATION=1; uv run pytest -m integration --no-cov` |
| Format | `make fmt` | `uv run ruff check --fix .`; `uv run ruff format .` |
| Migrate | `make migrate` | `uv run alembic upgrade head` (uses `GLADYS_DATABASE__URL`) |
| Offline eval | `make eval` | Phase 1 placeholder |
| Live eval | `make eval-live` | Phase 1 placeholder |

Integration tests use Testcontainers and therefore require Docker. They start one PostgreSQL container per session, build the schema with `alembic upgrade head`, and check that the migrations match the SQLAlchemy models. With `GLADYS_REQUIRE_INTEGRATION=1` (set by `make test-integration` and CI), a missing Docker daemon fails the run instead of skipping it. Protocol source belongs in a tenant-scoped `BlobStore`; the run document persists hashes and provenance, never source text.
