import copy
import json
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from gladys.domain.records import (
    ALLOWED_TRANSITIONS,
    SCHEMA_VERSION,
    Clarification,
    ClarificationNotAllowed,
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
    ValidationRejected,
    ValidationResult,
    ValidationSeverity,
    ValidationSource,
    sha256_text,
    upgrade_v02_to_v03,
    upgrade_v03_to_v04,
)

T0 = datetime(2026, 9, 28, 9, tzinfo=UTC)


def revision(source: str = "source", *, author: str = "agent") -> ProtocolRevision:
    generation = GenerationInfo("model", "high", "v1", "0.1", "trace", sha256_text(source), T0)
    return ProtocolRevision.from_source(
        source, author, "generation", T0, generation=generation if author == "agent" else None
    )


def record() -> RunRecord:
    return RunRecord(Request("transfer", "scientist", T0), "tenant", "lab")


def result(run: RunRecord, check: str = "simulation", passed: bool = True, **kwargs: object) -> ValidationResult:
    """A validation result for the run's *current* protocol revision."""
    assert run.protocol is not None
    return ValidationResult(check, passed, protocol_sha256=run.protocol.source_sha256, **kwargs)  # type: ignore[arg-type]


def draft() -> RunRecord:
    run = record()
    run.transition(RunStatus.GENERATING, "worker", at=T0)
    run.add_protocol_revision(revision())
    run.record_validation(result(run))
    run.transition(RunStatus.DRAFT, "agent", at=T0)
    return run


def test_new_record_starts_requested_and_round_trips() -> None:
    run = record()
    assert run.status is RunStatus.REQUESTED
    assert RunRecord.from_json(run.to_json()) == run
    assert json.loads(run.to_json())["schema_version"] == SCHEMA_VERSION == "0.4"


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
    # Bypass the aggregate on purpose: RUNNING must still refuse if the internals were tampered with.
    run._protocol_revisions.append(revision("changed", author="human"))
    with pytest.raises(ProtocolChangedSinceApproval):
        run.transition(RunStatus.RUNNING, "operator", at=T0)


def test_edit_after_approval_returns_to_draft_and_preserves_approval() -> None:
    run = draft()
    old_approval = run.transition(RunStatus.APPROVED, "reviewer", at=T0)
    run.add_protocol_revision(revision("edited", author="human"))
    assert run.status is RunStatus.DRAFT
    assert not run.validated
    assert len(run.validations) == 1  # the old result is kept as history, but no longer counts
    assert old_approval in run.history
    assert run.history[-1].note == "protocol changed after approval"


def test_approval_requires_protocol_and_error_free_validation() -> None:
    run = record()
    run.transition(RunStatus.GENERATING, "worker", at=T0)
    run.transition(RunStatus.DRAFT, "agent", at=T0)
    with pytest.raises(InvalidTransition, match="no protocol"):
        run.transition(RunStatus.APPROVED, "reviewer", at=T0)
    run.add_protocol_revision(revision())
    run.record_validation(result(run, "warning", False, severity=ValidationSeverity.WARNING))
    run.transition(RunStatus.APPROVED, "reviewer", at=T0)


def test_error_validation_blocks_approval() -> None:
    run = draft()
    run.record_validation(result(run, "bad", False, message="unsafe"))
    with pytest.raises(InvalidTransition, match="validation"):
        run.transition(RunStatus.APPROVED, "reviewer", at=T0)


def test_value_objects_and_full_record_round_trip() -> None:
    run = record()
    run.transition(RunStatus.GENERATING, "worker", at=T0)
    run.ask_clarification(["volume?"], "agent", at=T0)
    run.answer_clarification(0, "10 uL", "scientist", at=T0)
    run.transition(RunStatus.GENERATING, "worker", at=T0)
    run.add_protocol_revision(
        ProtocolRevision.from_source(
            "source",
            "agent",
            "generation",
            T0,
            deck=(LabwarePlacement("1", "plate", "source", "inventory"),),
            parameters={"volume_ul": 10, "wells": ["A1", "A2"]},
            generation=GenerationInfo("model", "high", "v1", "0.1", "trace", sha256_text("source"), T0),
        )
    )
    run.record_validation(result(run))
    run.record_consumable(Consumable("tips", 12, "tips", "lot"))
    run.add_external_ref(ExternalRef("lims", "idea", "42"))
    run.record_validation(
        result(
            run,
            "review",
            False,
            message="consider this",
            severity=ValidationSeverity.INFO,
            source=ValidationSource.AI_REVIEW,
        )
    )
    restored = RunRecord.from_dict(run.to_dict())
    assert restored == run
    assert restored.protocol is not None
    assert restored.protocol.generation is not None
    assert restored.protocol.generation.to_dict()["model"] == "model"
    assert restored.protocol.parameters == {"volume_ul": 10, "wells": ["A1", "A2"]}
    assert restored.clarifications[0].answer == "10 uL"


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
    assert RunRecord.from_dict(old).schema_version == SCHEMA_VERSION
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
            if state is RunStatus.NEEDS_CLARIFICATION:
                run.ask_clarification(["which plate?"], "agent", at=T0)
            else:
                run.transition(state, "actor", at=T0)
            assert run.history[:-1] == before
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


def test_withdrawn_approval_is_not_current_but_stays_auditable() -> None:
    run = draft()
    first = run.transition(RunStatus.APPROVED, "reviewer", at=T0)
    assert run.approval == first
    run.add_protocol_revision(revision("edited", author="human"))
    assert run.status is RunStatus.DRAFT
    assert run.approval is None
    assert run.approvals == (first,)
    run.transition(RunStatus.GENERATING, "scientist", at=T0)
    assert run.approval is None


def test_approval_survives_running_and_completion() -> None:
    run = running()
    approval = run.approvals[-1]
    run.transition(RunStatus.COMPLETED, "operator", at=T0)
    assert run.approval == approval


# --- append-only collections -------------------------------------------------------------------------------


def test_collections_are_read_only_tuples() -> None:
    run = draft()
    for name in ("history", "protocol_revisions", "validations", "external_refs", "consumables", "clarifications"):
        assert isinstance(getattr(run, name), tuple), name
        with pytest.raises(AttributeError):
            setattr(run, name, ())


# --- validations are bound to a protocol hash --------------------------------------------------------------


def test_validation_counts_only_for_the_revision_it_checked() -> None:
    run = draft()
    assert run.validated
    run.add_protocol_revision(revision("edited", author="human"))
    assert not run.validated
    assert run.current_validations == ()
    run.record_validation(result(run))
    assert run.validated
    assert [v.protocol_sha256 for v in run.validations] == [sha256_text("source"), sha256_text("edited")]


def test_failure_on_old_revision_does_not_block_new_revision() -> None:
    run = draft()
    run.record_validation(result(run, "bad", False))
    assert not run.validated
    run.add_protocol_revision(revision("fixed", author="human"))
    run.record_validation(result(run))
    assert run.validated


def test_validation_for_a_stale_protocol_is_rejected() -> None:
    run = draft()
    stale = result(run)
    run.add_protocol_revision(revision("edited", author="human"))
    with pytest.raises(ValidationRejected, match="current protocol"):
        run.record_validation(stale)


def test_validation_requires_a_protocol_and_an_editable_status() -> None:
    run = record()
    run.transition(RunStatus.GENERATING, "worker", at=T0)
    with pytest.raises(ValidationRejected, match="no protocol"):
        run.record_validation(ValidationResult("sim", True, protocol_sha256=sha256_text("x")))
    approved = draft()
    approved.transition(RunStatus.APPROVED, "reviewer", at=T0)
    with pytest.raises(ValidationRejected, match="approved"):
        approved.record_validation(result(approved))


# --- deck and parameters belong to a revision ---------------------------------------------------------------


def test_deck_and_parameters_live_on_the_revision() -> None:
    placement = LabwarePlacement("1", "plate", "source")
    parameters: dict[str, object] = {"volume_ul": 10}
    rev = ProtocolRevision.from_source("s", "scientist", "human_edit", T0, deck=[placement], parameters=parameters)
    parameters["volume_ul"] = 99
    assert rev.deck == (placement,)
    assert rev.parameters == {"volume_ul": 10}
    with pytest.raises(TypeError):
        rev.parameters["volume_ul"] = 5  # type: ignore[index]
    assert ProtocolRevision.from_dict(rev.to_dict()) == rev


# --- external refs and consumables -------------------------------------------------------------------------


def test_add_external_ref_ignores_exact_duplicates() -> None:
    run = record()
    run.add_external_ref(ExternalRef("lims", "idea", "42"))
    run.add_external_ref(ExternalRef("lims", "idea", "42"))
    run.add_external_ref(ExternalRef("lims", "idea", "43"))
    assert run.external_refs == (ExternalRef("lims", "idea", "42"), ExternalRef("lims", "idea", "43"))


def test_record_consumable_appends() -> None:
    run = record()
    run.record_consumable(Consumable("tips", 12, "tips"))
    run.record_consumable(Consumable("tips", 12, "tips"))
    assert len(run.consumables) == 2


# --- clarifications ----------------------------------------------------------------------------------------


def generating() -> RunRecord:
    run = record()
    run.transition(RunStatus.GENERATING, "worker", at=T0)
    return run


def test_ask_clarification_moves_to_needs_clarification() -> None:
    run = generating()
    asked = run.ask_clarification(["which plate?", "what volume?"], "agent", at=T0)
    assert run.status is RunStatus.NEEDS_CLARIFICATION
    assert asked == (Clarification("which plate?", T0), Clarification("what volume?", T0))
    assert run.clarifications == asked
    assert run.history[-1].actor == "agent"


def test_needs_clarification_is_only_reachable_through_ask_clarification() -> None:
    run = generating()
    with pytest.raises(InvalidTransition, match="ask_clarification"):
        run.transition(RunStatus.NEEDS_CLARIFICATION, "agent", at=T0)


@pytest.mark.parametrize("questions", [[], "which plate?", [""]])
def test_ask_clarification_rejects_bad_questions(questions: object) -> None:
    with pytest.raises(ValueError):
        generating().ask_clarification(questions, "agent", at=T0)  # type: ignore[arg-type]


def test_ask_clarification_requires_generating() -> None:
    with pytest.raises(InvalidTransition):
        draft().ask_clarification(["late question"], "agent", at=T0)


def test_answer_clarification_once_and_only_while_waiting() -> None:
    run = generating()
    run.ask_clarification(["which plate?"], "agent", at=T0)
    answered = run.answer_clarification(0, "the 96-well one", "scientist", at=T0)
    assert answered == Clarification("which plate?", T0, "the 96-well one", "scientist", T0)
    assert run.clarifications == (answered,)
    with pytest.raises(ClarificationNotAllowed, match="already answered"):
        run.answer_clarification(0, "changed my mind", "scientist", at=T0)
    with pytest.raises(ClarificationNotAllowed, match="no clarification"):
        run.answer_clarification(1, "?", "scientist", at=T0)
    run.transition(RunStatus.GENERATING, "worker", at=T0)
    run.ask_clarification(["what volume?"], "agent", at=T0)
    run.transition(RunStatus.ABORTED, "scientist", at=T0)
    with pytest.raises(ClarificationNotAllowed, match="aborted"):
        run.answer_clarification(1, "10 uL", "scientist", at=T0)


# --- schema 0.3 -> 0.4 -------------------------------------------------------------------------------------


def v03_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": "0.3",
        "run_id": "r",
        "tenant_id": "t",
        "lab_profile_id": "lab",
        "version": 3,
        "request": {"text": "x", "requested_by": "u", "submitted_at": T0.isoformat()},
        "protocol_revisions": [
            {"source_sha256": "a" * 64, "author": "scientist", "created_at": T0.isoformat(), "reason": "human_edit"},
            {"source_sha256": "b" * 64, "author": "scientist", "created_at": T0.isoformat(), "reason": "human_edit"},
        ],
        "deck": [{"slot": "1", "load_name": "plate", "label": "source", "inventory_id": None}],
        "parameters": {"volume_ul": 10},
        "validations": [{"check": "sim", "passed": True, "message": "", "severity": "error", "source": "simulation"}],
        "consumables": [],
        "external_refs": [],
        "clarifications": [],
        "history": [
            {"from": "requested", "to": "generating", "actor": "w", "at": T0.isoformat(), "note": ""},
            {"from": "generating", "to": "draft", "actor": "a", "at": T0.isoformat(), "note": ""},
        ],
    }
    document.update(overrides)
    return document


def test_upgrade_03_attaches_deck_parameters_and_validations_to_latest_revision() -> None:
    old = v03_document()
    upgraded = upgrade_v03_to_v04(old)
    assert old["schema_version"] == "0.3" and "deck" in old  # pure: the input is untouched
    assert upgraded["schema_version"] == "0.4"
    assert "deck" not in upgraded and "parameters" not in upgraded
    first, latest = upgraded["protocol_revisions"]
    assert (first["deck"], first["parameters"]) == ([], {})
    assert latest["deck"] == old["deck"] and latest["parameters"] == {"volume_ul": 10}
    assert upgraded["validations"][0]["protocol_sha256"] == "b" * 64
    run = RunRecord.from_dict(old)
    assert run.validated
    assert run.protocol is not None and run.protocol.parameters == {"volume_ul": 10}


def test_upgrade_03_without_revisions_and_without_evidence_loads() -> None:
    old = v03_document(protocol_revisions=[], deck=[], parameters={}, validations=[])
    assert RunRecord.from_dict(old).protocol is None


def test_upgrade_03_refuses_to_drop_evidence_that_has_no_revision() -> None:
    with pytest.raises(ValueError, match="no protocol revision"):
        upgrade_v03_to_v04(v03_document(protocol_revisions=[]))


def test_upgrade_02_attaches_validations_deck_and_parameters_to_migrated_revision() -> None:
    source_hash = "c" * 64
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
        "deck": [{"slot": "2", "load_name": "tips", "label": "tips"}],
        "parameters": {"mix": True},
        "validations": [{"check": "sim", "passed": True}],
        "history": [],
    }
    run = RunRecord.from_dict(old)
    assert run.protocol is not None
    assert run.protocol.deck == (LabwarePlacement("2", "tips", "tips"),)
    assert run.protocol.parameters == {"mix": True}
    assert [v.protocol_sha256 for v in run.validations] == [source_hash]
    assert run.validated


def test_run_with_revisions_can_be_deep_copied() -> None:
    run = draft()
    clone = copy.deepcopy(run)
    assert clone == run
    assert clone._history is not run._history


def test_a_run_without_protocol_has_no_current_validations() -> None:
    assert record().current_validations == ()
    assert not record().validated
