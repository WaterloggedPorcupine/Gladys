# ADR 0002: Run lifecycle and protocol provenance

## Context

A generated protocol is untrusted, human approval must bind to exact bytes, and every lifecycle and revision event must remain reviewable. Generation can also require clarification or fail before a draft exists.

## Decision

Schema 0.3 starts runs at `REQUESTED`, explicitly represents generation outcomes, and permits only the roadmap transition graph. Protocols are append-only `ProtocolRevision` values identified by SHA-256. Agent revisions carry `GenerationInfo`; human editing is derived by comparing the latest source hash with the latest agent-generated hash. Approval history stores the approved hash. Starting a run rechecks it, while editing an approved run appends a `DRAFT` transition and clears validation.

All domain datetimes must be timezone-aware. Schema upgrades are pure chained functions; 0.2 documents are upgraded on read.

## Consequences

Approval cannot silently drift from executable content, old approvals remain auditable, and retries/clarifications are first-class. Callers must append revisions through aggregate behavior and store source bytes separately.

## Alternatives considered

- Mutating a single protocol field was rejected because it loses provenance.
- Treating AST validation as authorization was rejected because it is not a security boundary.
- Resetting history after edits was rejected because the audit trail is append-only.
