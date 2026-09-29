import json
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from gladys.domain.records import (
    ALLOWED_TRANSITIONS,
    Clarification,
    Consumable,
    ExternalRef,
    GenerationInfo,
    InvalidTransition,
    LabwarePlacement,
    ProtocolChangedSinceApproval,
    ProtocolLocked,
    ProtocolRevision,
    Request,
    RunRecord,
    RunStatus,
    StatusChange,
    ValidationResult,
    ValidationSeverity,
    ValidationSource,
    upgrade_v02_to_v03,
)

T0 = datetime(2026, 9, 28, 9, tzinfo=UTC)


def revision(source: str = "source", *, author: str = "agent") -> ProtocolRevision:
    generation = GenerationInfo("model", "high", "v1", "0.1", "trace", "")
    generation = GenerationInfo(
        "model",
        "high",
        "v1",
        "0.1",
        "trace",
        ProtocolRevision.from_source(source, "human", "x").source_sha256,
        T0,
    )
    return ProtocolRevision.from_source(
        source, author, "generation", T0, generation=generation if author == "agent" else None
    )


def record() -> RunRecord:
    return RunRecord(Request("transfer", "scientist", T0), "tenant", "lab")


def draft() -> RunRecord:
    run = record()
    run.transition(RunStatus.GENERATING, "worker", at=T0)
    run.add_protocol_revision(revision())
    run.validations.append(ValidationResult("simulation", True))
    run.transition(RunStatus.DRAFT, "agent", at=T0)
    return run


def test_new_record_starts_requested_and_round_trips() -> None:
    run = record()
    assert run.status is RunStatus.REQUESTED
    assert RunRecord.from_json(run.to_json()) == run
    assert json.loads(run.to_json())["schema_version"] == "0.3"


def test_complete_lifecycle_and_approval_binding() -> None:
    run = draft()
    approval = run.transition(RunStatus.APPROVED, "reviewer", at=T0)
    assert approval.protocol_sha256 == run.protocol.source_sha256
    run.transition(RunStatus.RUNNING, "operator", at=T0 + timedelta(minutes=1))
    run.transition(RunStatus.COMPLETED, "operator", at=T0 + timedelta(minutes=2))
    assert run.turnaround_time == timedelta(minutes=2)


def test_changed_hash_cannot_run_even_if_aggregate_was_tampered() -> None:
    run = draft()
    run.transition(RunStatus.APPROVED, "reviewer", at=T0)
    run.protocol_revisions.append(revision("changed", author="human"))
    with pytest.raises(ProtocolChangedSinceApproval):
        run.transition(RunStatus.RUNNING, "operator", at=T0)


def test_edit_after_approval_returns_to_draft_and_preserves_approval() -> None:
    run = draft()
    old_approval = run.transition(RunStatus.APPROVED, "reviewer", at=T0)
    run.add_protocol_revision(revision("edited", author="human"))
    assert run.status is RunStatus.DRAFT
    assert not run.validations
    assert old_approval in run.history
    assert run.history[-1].note == "protocol changed after approval"


def test_approval_requires_protocol_and_error_free_validation() -> None:
    run = record()
    run.transition(RunStatus.GENERATING, "worker", at=T0)
    run.transition(RunStatus.DRAFT, "agent", at=T0)
    with pytest.raises(InvalidTransition, match="no protocol"):
        run.transition(RunStatus.APPROVED, "reviewer", at=T0)
    run.add_protocol_revision(revision())
    run.validations.append(ValidationResult("warning", False, severity=ValidationSeverity.WARNING))
    run.transition(RunStatus.APPROVED, "reviewer", at=T0)


def test_error_validation_blocks_approval() -> None:
    run = draft()
    run.validations.append(ValidationResult("bad", False, "unsafe"))
    with pytest.raises(InvalidTransition, match="validation"):
        run.transition(RunStatus.APPROVED, "reviewer", at=T0)


def test_value_objects_and_full_record_round_trip() -> None:
    run = draft()
    run.deck.append(LabwarePlacement("1", "plate", "source", "inventory"))
    run.consumables.append(Consumable("tips", 12, "tips", "lot"))
    run.external_refs.append(ExternalRef("lims", "idea", "42"))
    run.clarifications.append(Clarification("volume?", T0, "10 uL", "scientist", T0))
    run.validations.append(
        ValidationResult("review", False, "consider this", ValidationSeverity.INFO, ValidationSource.AI_REVIEW)
    )
    restored = RunRecord.from_dict(run.to_dict())
    assert restored == run
    assert restored.protocol is not None
    assert restored.protocol.generation is not None
    assert restored.protocol.generation.to_dict()["model"] == "model"


def test_human_edit_detection_uses_latest_agent_hash() -> None:
    run = record()
    assert not run.human_edited
    run.transition(RunStatus.GENERATING, "worker", at=T0)
    run.add_protocol_revision(revision("generated"))
    assert not run.human_edited
    run.add_protocol_revision(revision("edited", author="human"))
    assert run.human_edited


def test_agent_revision_requires_generation_info() -> None:
    with pytest.raises(ValueError, match="generation info"):
        ProtocolRevision("hash", "agent", T0, "generation")


def test_unstarted_and_unended_timestamps_are_none() -> None:
    run = record()
    assert run.started_at is None
    assert run.ended_at is None
    assert run.turnaround_time is None


def test_status_change_and_unanswered_clarification_serialization() -> None:
    change = StatusChange(RunStatus.REQUESTED, RunStatus.GENERATING, "worker", T0)
    clarification = Clarification("which plate?", T0)
    assert StatusChange.from_dict(change.to_dict()) == change
    assert Clarification.from_dict(clarification.to_dict()) == clarification


@pytest.mark.parametrize(
    "constructor",
    [
        lambda: Request("x", "y", datetime(2026, 1, 1)),
        lambda: GenerationInfo("m", "e", "p", "g", "t", "h", datetime(2026, 1, 1)),
        lambda: ProtocolRevision("h", "human", datetime(2026, 1, 1), "edit"),
    ],
)
def test_naive_datetimes_rejected(constructor: object) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        constructor()  # type: ignore[operator]


def test_upgrade_02_is_pure_and_loadable() -> None:
    old = {
        "schema_version": "0.2",
        "run_id": "r",
        "request": {"text": "x", "requested_by": "u", "submitted_at": T0.isoformat()},
        "protocol": None,
        "validations": [],
        "history": [],
    }
    upgraded = upgrade_v02_to_v03(old)
    assert old["schema_version"] == "0.2"
    assert upgraded["schema_version"] == "0.3"
    assert RunRecord.from_dict(old).status is RunStatus.DRAFT


def test_upgrade_02_protocol_and_approval_are_preserved() -> None:
    source_hash = "a" * 64
    old = {
        "schema_version": "0.2",
        "run_id": "r",
        "request": {"text": "x", "requested_by": "u", "submitted_at": T0.isoformat()},
        "protocol": {
            "source_sha256": source_hash,
            "generated_sha256": source_hash,
            "generated_by": "legacy-model",
            "generated_at": T0.isoformat(),
            "platform": "opentrons",
            "version": "1",
        },
        "validations": [{"check": "sim", "passed": True}],
        "history": [{"from": "draft", "to": "approved", "actor": "reviewer", "at": T0.isoformat(), "note": "ok"}],
    }
    run = RunRecord.from_dict(old)
    assert run.protocol is not None
    assert run.approval is not None
    assert run.approval.protocol_sha256 == source_hash


def test_unknown_schema_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        RunRecord.from_dict({"schema_version": "9"})


@given(st.lists(st.sampled_from(list(RunStatus)), max_size=30))
def test_random_transition_sequences_preserve_history(states: list[RunStatus]) -> None:
    run = record()
    for state in states:
        before = tuple(run.history)
        if state in ALLOWED_TRANSITIONS[run.status]:
            if state is RunStatus.APPROVED and (run.protocol is None or not run.validated):
                continue
            run.transition(state, "actor", at=T0)
            assert run.history[:-1] == list(before)
            assert run.history[-1].from_status == (before[-1].to_status if before else RunStatus.REQUESTED)
        else:
            with pytest.raises(InvalidTransition):
                run.transition(state, "actor", at=T0)
            assert tuple(run.history) == before


@given(st.text(max_size=100), st.text(min_size=1, max_size=20), st.text(min_size=1, max_size=20))
def test_arbitrary_minimal_records_round_trip(text: str, tenant: str, profile: str) -> None:
    run = RunRecord(Request(text, "user", T0), tenant, profile)
    assert RunRecord.from_dict(run.to_dict()) == run


def running() -> RunRecord:
    run = draft()
    run.transition(RunStatus.APPROVED, "reviewer", at=T0)
    run.transition(RunStatus.RUNNING, "operator", at=T0)
    return run


@pytest.mark.parametrize(
    "prepare",
    [
        record,
        running,
        lambda: _finish(RunStatus.COMPLETED),
        lambda: _finish(RunStatus.FAILED),
        lambda: _abort_draft(),
    ],
)
def test_protocol_is_locked_outside_generating_draft_and_approved(prepare: object) -> None:
    run = prepare()  # type: ignore[operator]
    before = (run.status, run.protocol_revisions[:])
    with pytest.raises(ProtocolLocked):
        run.add_protocol_revision(revision("late edit", author="human"))
    assert (run.status, run.protocol_revisions[:]) == before


def _finish(status: RunStatus) -> RunRecord:
    run = running()
    run.transition(status, "operator", at=T0)
    return run


def _abort_draft() -> RunRecord:
    run = draft()
    run.transition(RunStatus.ABORTED, "scientist", at=T0)
    return run
