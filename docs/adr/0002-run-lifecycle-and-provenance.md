# ADR 0002: Run lifecycle and protocol provenance

## Context

A generated protocol is untrusted, human approval must bind to exact bytes, and every lifecycle and revision event must remain reviewable. Generation can also require clarification or fail before a draft exists.

The first Phase 0 version (schema 0.3) exposed the aggregate's collections as public lists and cleared validation results whenever a new revision arrived. A review found that this let callers rewrite the audit trail, lost evidence, and allowed revisions on runs that were already running or finished. This ADR records the corrected design (schema 0.4).

## Decision

**Lifecycle.** Runs start at `REQUESTED` and follow only the roadmap transition graph. `NEEDS_CLARIFICATION` can only be reached through `ask_clarification`, which records the questions and makes the transition as one step. Answers are accepted only while the run is `NEEDS_CLARIFICATION`, and each question can be answered only once.

**Append-only aggregate.** History, protocol revisions, validations, external refs, consumables and clarifications are private lists, exposed as read-only tuples. They change only through aggregate methods (`transition`, `add_protocol_revision`, `record_validation`, `add_external_ref`, `record_consumable`, `ask_clarification`, `answer_clarification`), each of which enforces its own rule. `from_dict` rehydrates stored documents directly, because the rules applied when the document was written.

**Protocol revisions.** Protocols are append-only `ProtocolRevision` values identified by SHA-256. Each revision also carries the deck layout and parameters it was written for (frozen copies), because those describe one specific protocol, not the run. Agent revisions carry `GenerationInfo`. Human editing is derived by comparing the latest source hash with the latest agent-generated hash. Revisions are allowed only in `GENERATING`, `DRAFT` and `APPROVED`. Anywhere else raises `ProtocolLocked`, so the recorded protocol can't drift from what the robot ran.

**Validations are bound to a hash.** Each `ValidationResult` records the `protocol_sha256` it checked. `record_validation` accepts only results for the current revision, and only in `GENERATING` or `DRAFT`. `validated` considers only results for the current revision's hash: at least one ran, and none failed with `error` severity. A new revision therefore makes the run unvalidated without deleting anything, and old results remain as history.

**Approval binding.** Transitions to `APPROVED` store the approved hash. `RUNNING` rechecks that it equals the current hash. Editing an approved run appends a revision and a `DRAFT` transition. `approval` returns the approval in force: the latest one, unless the run later returned to `DRAFT` or `GENERATING`. `approvals` returns every approval ever given, for audit.

All domain datetimes must be timezone-aware. Schema upgrades are a chain of pure functions: 0.2 → 0.3 → 0.4. `upgrade_v03_to_v04` attaches the top-level deck, parameters and validations to the latest revision. In 0.3 they always described the current protocol, because validations were cleared on each revision. If there is no revision to attach them to, the upgrade refuses rather than silently dropping evidence.

## Consequences

Approval can't silently drift from executable content, withdrawn approvals stop counting but stay auditable, and validation evidence is never lost. Callers can't bypass the rules by mutating lists. The trade-off is that every new kind of change needs an aggregate method. Validation workers must send the hash they checked, and a result that arrives after a newer revision is rejected (`ValidationRejected`), so the worker must re-validate. Source bytes are stored separately, in a `BlobStore`.

## Alternatives considered

- **Mutating a single protocol field.** Rejected because it loses provenance.
- **Clearing validations on each revision.** This was the 0.3 behavior. Rejected because it deletes evidence and breaks the append-only rule. Binding results to a hash gives the same approval gate while keeping history.
- **Deck and parameters on the run.** Rejected because they would describe whichever protocol happens to be current, which becomes wrong once the protocol is revised.
- **Returning a frozen copy of the whole aggregate on every change.** Rejected as heavier than private lists behind tuple properties, and unidiomatic next to the dataclass entities used elsewhere.
- **Treating AST validation as authorization.** Rejected because it is not a security boundary.
- **Resetting history after edits.** Rejected because the audit trail is append-only.
