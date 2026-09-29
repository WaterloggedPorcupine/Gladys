# ADR 0003: PostgreSQL documents plus content-addressed blobs

## Context

Gladys needs atomic, tenant-scoped lifecycle persistence, optimistic concurrency, indexed operational queries, durable audit events, and storage for potentially large protocol sources. Redis cannot be authoritative.

## Decision

**Documents plus projections.** Persist the schema 0.4 aggregate as JSONB in `runs.document`, and project query-critical data into:

- columns on `runs` (tenant, status, requester, lab profile, current protocol hash, timestamps, `version`)
- append-only rows in `run_status_changes`
- external identifiers in `run_external_refs`

`idempotency_keys` and a transactional `outbox` are reserved now for Phase 2. Every lookup includes `tenant_id`.

**Optimistic concurrency.** A save runs `UPDATE ... WHERE version = :expected` and raises `ConcurrencyConflict` if no row matched. A duplicate `add` raises `RunAlreadyExists`, detected with `INSERT ... ON CONFLICT DO NOTHING` plus a rowcount check, so no adapter leaks a driver exception. Run IDs are globally unique, matching the `runs.id` primary key.

**Status history by sequence number.** Each `run_status_changes` row stores `seq`, its index in the run's history, with a unique `(run_id, seq)` constraint. A save inserts only changes whose `seq` is greater than the stored maximum, and skips the insert when there are none. Inferring new rows by counting existing ones broke when a save had no new transition: SQLAlchemy turned the empty parameter list into one all-NULL row. It would also be fragile under any future history repair. `get_status_history` exposes the audit rows so the contract suite can prove they equal the domain history.

**External refs.** Every save projects all of the run's refs with `ON CONFLICT DO NOTHING` on `uq_run_external_refs_lookup`, so refs added after creation are indexed. `find_by_external_ref(tenant_id, system, kind, ext_id)` answers questions like "which runs tested idea X".

**Indexes.**

- `runs(tenant_id, status, created_at)` for listing
- `runs(tenant_id, current_protocol_sha256)` for "every run of this exact protocol"
- a partial `outbox(created_at) WHERE published_at IS NULL` for the Phase 2 relay

**Migrations.** Alembic owns the schema. `migrations/env.py` reads the database URL from `gladys.config.Settings` (`GLADYS_DATABASE__URL`), never from `alembic.ini`. The integration suite builds its schema with `alembic upgrade head`, checks that `compare_metadata` reports no differences from the SQLAlchemy models, and checks that `downgrade base` → `upgrade head` works.

**Tenant-scoped blobs.** Protocol bytes go through a SHA-256-addressed `BlobStore` whose methods take the tenant: `put(tenant_id, content)`, `get(tenant_id, sha256)` and `exists(tenant_id, sha256)`. Tenant IDs must fully match `[A-Za-z0-9_-]{1,64}`, so none can escape a storage root or key prefix. The filesystem adapter lays blobs out as `root/<tenant_id>/<aa>/<rest>`. It writes each blob to a uuid-named temp file and then does an atomic `os.replace`, so concurrent writes of the same content can't share a temp file. JSON documents contain hashes only.

**Packaging.** SQLAlchemy, asyncpg and Alembic are in a `postgres` extra, not the core install. Contract suites run the same tests against the in-memory fakes and the real adapters (PostgreSQL through Testcontainers). CI fails, rather than skips, when Docker is missing.

## Consequences

Common queries avoid JSON scans, the full aggregate remains evolvable, sources are deduplicated per tenant, and concurrent reviewers can't overwrite one another. The trade-offs are that writes need explicit projections and transaction care, and each projection is one more thing the contract suite must cover. Identical protocols uploaded by two tenants are stored twice, which is the price of isolation. Filesystem storage suits one-node development, not distributed production.

## Alternatives considered

- **SQLite.** Rejected to avoid dialect drift.
- **Protocol text in JSONB.** Rejected because source belongs in blob storage.
- **Fully normalized aggregate tables.** Rejected because schema evolution would need much more mapping and migration work.
- **Global, cross-tenant blob deduplication.** Rejected because one tenant could learn whether another holds a given protocol by probing its hash.
- **Counting existing status rows to find new ones.** Rejected for the reasons above; `seq` makes position explicit and lets the database enforce uniqueness.
- **S3.** Deferred until deployment requirements justify it; the port prevents coupling.
