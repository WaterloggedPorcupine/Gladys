import json
from datetime import datetime, timedelta, timezone

import pytest

from gladys.records import (
    SCHEMA_VERSION,
    Consumable,
    ExternalRef,
    InvalidTransition,
    LabwarePlacement,
    ProtocolRef,
    Request,
    RunRecord,
    RunStatus,
    ValidationResult,
)

T0 = datetime(2026, 9, 28, 9, 0, tzinfo=timezone.utc)
MODEL = "claude-opus-5-5"


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def draft_record() -> RunRecord:
    return RunRecord(
        request=Request("Serial dilution of compound A, 1:2 across row A", "zsolan", T0),
        protocol=ProtocolRef.from_source(
            "# protocol source", "opentrons", "1", MODEL, generated_at=at(5)
        ),
        deck=[
            LabwarePlacement(
                "1", "corning_96_wellplate_360ul_flat", "dilution_plate", inventory_id="PL-0042"
            ),
            LabwarePlacement("2", "opentrons_96_tiprack_300ul", "tips_300"),
        ],
        parameters={"dilution_factor": 2, "wells": ["A1", "A2", "A3"]},
        validations=[ValidationResult("simulates_cleanly", True)],
        consumables=[Consumable("tips_300", 12, "tips", inventory_id="TIP-300-LOT7")],
        external_refs=[ExternalRef("cheminventory", "idea", "421393")],
    )


def completed_record() -> RunRecord:
    record = draft_record()
    record.transition(RunStatus.APPROVED, "zsolan", "looks good", at=at(10))
    record.transition(RunStatus.RUNNING, "ot2-bench-3", at=at(15))
    record.transition(RunStatus.COMPLETED, "ot2-bench-3", at=at(45))
    return record


# --- serialization ---


def test_json_round_trip_preserves_everything():
    record = completed_record()
    assert RunRecord.from_json(record.to_json()) == record


def test_minimal_record_round_trips():
    record = RunRecord(request=Request("do something", "zsolan", T0))
    restored = RunRecord.from_json(record.to_json())
    assert restored == record
    assert restored.protocol is None
    assert restored.status is RunStatus.DRAFT


def test_serialized_form_is_plain_json():
    data = json.loads(completed_record().to_json())
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["status"] == "completed"
    assert data["request"]["submitted_at"] == "2026-09-28T09:00:00+00:00"
    assert data["deck"][0]["inventory_id"] == "PL-0042"
    assert data["external_refs"] == [{"system": "cheminventory", "kind": "idea", "id": "421393"}]
    assert [h["to"] for h in data["history"]] == ["approved", "running", "completed"]
    assert data["protocol"]["generated_by"] == MODEL
    assert data["protocol"]["human_edited"] is False


# --- protocol provenance ---


def test_protocol_ref_hash_is_content_addressed():
    a = ProtocolRef.from_source("x = 1", "opentrons", "1", MODEL)
    b = ProtocolRef.from_source("x = 1", "opentrons", "1", MODEL)
    c = ProtocolRef.from_source("x = 2", "opentrons", "1", MODEL)
    assert a.source_sha256 == b.source_sha256 != c.source_sha256


def test_human_edited_is_derived_from_hashes():
    unedited = ProtocolRef.from_source("x = 1", "opentrons", "1", MODEL)
    edited = ProtocolRef.from_source("x = 2", "opentrons", "1", MODEL, generated_source="x = 1")
    assert not unedited.human_edited
    assert edited.human_edited
    assert edited.generated_sha256 == unedited.source_sha256


# --- status history ---


def test_new_record_is_draft_with_empty_history():
    record = draft_record()
    assert record.status is RunStatus.DRAFT
    assert record.history == []


def test_transitions_build_audit_trail():
    record = completed_record()
    assert record.status is RunStatus.COMPLETED
    assert [(h.from_status, h.to_status) for h in record.history] == [
        (RunStatus.DRAFT, RunStatus.APPROVED),
        (RunStatus.APPROVED, RunStatus.RUNNING),
        (RunStatus.RUNNING, RunStatus.COMPLETED),
    ]
    assert record.approval.actor == "zsolan"
    assert record.approval.note == "looks good"
    assert record.started_at == at(15)
    assert record.ended_at == at(45)


def test_turnaround_time():
    assert completed_record().turnaround_time == timedelta(minutes=45)
    assert draft_record().turnaround_time is None


@pytest.mark.parametrize(
    "path",
    [
        [RunStatus.RUNNING],
        [RunStatus.COMPLETED],
        [RunStatus.APPROVED, RunStatus.COMPLETED],
        [RunStatus.ABORTED, RunStatus.DRAFT],
    ],
)
def test_invalid_transitions_are_rejected(path):
    record = draft_record()
    *ok, bad = path
    for status in ok:
        record.transition(status, "zsolan")
    with pytest.raises(InvalidTransition):
        record.transition(bad, "zsolan")


def test_cannot_approve_without_protocol():
    record = RunRecord(request=Request("x", "zsolan", T0))
    with pytest.raises(InvalidTransition, match="no protocol"):
        record.transition(RunStatus.APPROVED, "zsolan")


def test_cannot_approve_unvalidated_run():
    record = draft_record()
    record.validations.append(ValidationResult("tip_collision", False, "slot 2"))
    with pytest.raises(InvalidTransition, match="validation"):
        record.transition(RunStatus.APPROVED, "zsolan")


def test_revoked_approval_clears_approval():
    record = draft_record()
    record.transition(RunStatus.APPROVED, "zsolan")
    record.transition(RunStatus.DRAFT, "zsolan", "needs another look")
    assert record.status is RunStatus.DRAFT
    assert record.approval is None
    assert len(record.history) == 2


# --- validation ---


def test_validated_requires_checks_and_all_passing():
    record = RunRecord(request=Request("x", "zsolan", T0))
    assert not record.validated
    record.validations.append(ValidationResult("a", True))
    assert record.validated
    record.validations.append(ValidationResult("b", False, "tip collision"))
    assert not record.validated


def test_run_ids_are_unique():
    assert RunRecord(request=Request("x", "z")).run_id != RunRecord(request=Request("x", "z")).run_id
