# Phase 0: foundations

## What this builds

This change establishes Gladys's production-shaped foundation without beginning LLM generation. The existing `RunRecord` has evolved into schema 0.3 under the pure domain package. It now models the complete pre-run lifecycle, binds approval to a protocol SHA-256, keeps append-only protocol revisions and status history, records model provenance and clarification Q&A, rejects naive datetimes, and upgrades stored schema 0.2 documents on read.

Application-owned ports define run persistence, blob storage, clocks, and IDs. In-memory adapters make their contracts fast to test. The PostgreSQL adapter persists tenant-scoped JSONB aggregates with indexed projections and optimistic concurrency; its Alembic baseline also creates append-only audit, external-reference, idempotency, and outbox tables. Protocol source bytes are stored separately through content-addressed in-memory or filesystem blob adapters.

The repository now uses uv/Python 3.12 with a committed lockfile, Ruff, strict mypy, import-linter, pre-commit, coverage gates, four CI jobs, nested validated settings, structured JSON logging with correlation IDs, and isolated Prometheus registries. README setup and Windows-friendly uv equivalents accompany the Make targets.

## Why these choices

- A pure domain and inward-facing ports keep safety rules testable without a database, API, LLM, or robot SDK.
- Hash-bound approval makes review meaningful: an operator can only start the bytes a human approved.
- Append-only revisions/history preserve evidence instead of overwriting it; derived `human_edited` state cannot become stale.
- JSONB keeps the aggregate evolvable, while projected columns and side tables support operational queries and audit requirements.
- PostgreSQL-only integration tests prevent the false confidence of a different local SQL dialect.
- Content-addressed blobs keep source out of run documents, deduplicate identical bytes, and leave an S3 migration behind one port.
- Optimistic concurrency makes conflicting updates explicit instead of silently losing a reviewer or operator action.

## Verification

- `make check`
- `make test-integration`
- Domain record coverage: 100%; overall coverage exceeds the required 85% threshold.

## Open questions

- Schema 0.2 had no tenant or lab-profile identifiers. The upgrader conservatively assigns both to `"default"`; a production migration may need deployment-specific mappings before importing historical data.
- The filesystem blob adapter assumes one durable local volume. The S3 adapter remains intentionally deferred until deployment requirements are known.
- Phase 0 reserves the outbox and idempotency schema, but their service behavior remains Phase 2 scope.
