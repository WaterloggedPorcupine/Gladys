# ADR 0003: PostgreSQL documents plus content-addressed blobs

## Context

Gladys needs atomic, tenant-scoped lifecycle persistence, optimistic concurrency, indexed operational queries, durable audit events, and storage for potentially large protocol sources. Redis cannot be authoritative.

## Decision

Persist the schema 0.3 aggregate as JSONB in PostgreSQL while projecting query-critical columns into `runs`, append-only status rows into `run_status_changes`, and external identifiers into `run_external_refs`. Reserve `idempotency_keys` and a transactional `outbox` now for Phase 2. Every lookup includes `tenant_id`; saves compare the expected `version` and raise `ConcurrencyConflict` on mismatch.

Store protocol bytes through a SHA-256-addressed `BlobStore`. Phase 0 provides in-memory and filesystem adapters; JSON documents contain hashes only. Contract suites exercise both repository and blob ports, including the real PostgreSQL adapter through Testcontainers.

## Consequences

Common queries avoid JSON scans, the full aggregate remains evolvable, sources are deduplicated, and concurrent reviewers cannot overwrite one another. Writes require explicit projections and transaction care. Filesystem storage is suitable for one-node development, not distributed production.

## Alternatives considered

- SQLite was rejected to avoid dialect drift.
- Storing protocol text in JSONB was rejected because source belongs in blob storage.
- Fully normalized aggregate tables were rejected because schema evolution would require much more mapping and migration work.
- S3 is deferred until deployment requirements justify it; the port prevents coupling.
