"""Platform-neutral, provenance-rich run aggregate."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, cast

SCHEMA_VERSION = "0.3"


class DomainError(ValueError):
    """Base for violations of the run's rules; ``api/errors.py`` maps these to HTTP responses."""


class InvalidTransition(DomainError):
    pass


class ProtocolChangedSinceApproval(InvalidTransition):
    pass


class ProtocolLocked(DomainError):
    """The protocol can no longer change: the run is past approval (or never started generating)."""


class RunStatus(StrEnum):
    REQUESTED = "requested"
    GENERATING = "generating"
    NEEDS_CLARIFICATION = "needs_clarification"
    GENERATION_FAILED = "generation_failed"
    DRAFT = "draft"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.REQUESTED: frozenset({RunStatus.GENERATING}),
    RunStatus.GENERATING: frozenset({RunStatus.DRAFT, RunStatus.NEEDS_CLARIFICATION, RunStatus.GENERATION_FAILED}),
    RunStatus.NEEDS_CLARIFICATION: frozenset({RunStatus.GENERATING, RunStatus.ABORTED}),
    RunStatus.GENERATION_FAILED: frozenset({RunStatus.GENERATING, RunStatus.ABORTED}),
    RunStatus.DRAFT: frozenset({RunStatus.APPROVED, RunStatus.GENERATING, RunStatus.ABORTED}),
    RunStatus.APPROVED: frozenset({RunStatus.RUNNING, RunStatus.DRAFT, RunStatus.ABORTED}),
    RunStatus.RUNNING: frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.ABORTED}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.ABORTED: frozenset(),
}
_TERMINAL = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.ABORTED}
_PROTOCOL_EDITABLE = {RunStatus.GENERATING, RunStatus.DRAFT, RunStatus.APPROVED}


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _dt(value: object) -> datetime:
    result = datetime.fromisoformat(str(value))
    _aware(result, "datetime")
    return result


@dataclass(frozen=True)
class Request:
    text: str
    requested_by: str
    submitted_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        _aware(self.submitted_at, "submitted_at")

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "requested_by": self.requested_by,
            "submitted_at": self.submitted_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Request:
        return cls(str(data["text"]), str(data["requested_by"]), _dt(data["submitted_at"]))


@dataclass(frozen=True)
class GenerationInfo:
    model: str
    effort: str
    prompt_version: str
    gladys_version: str
    trace_id: str
    generated_sha256: str
    generated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        _aware(self.generated_at, "generated_at")

    def to_dict(self) -> dict[str, object]:
        result = self.__dict__.copy()
        result["generated_at"] = self.generated_at.isoformat()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> GenerationInfo:
        return cls(
            str(data["model"]),
            str(data["effort"]),
            str(data["prompt_version"]),
            str(data["gladys_version"]),
            str(data["trace_id"]),
            str(data["generated_sha256"]),
            _dt(data["generated_at"]),
        )


@dataclass(frozen=True)
class ProtocolRevision:
    source_sha256: str
    author: str
    created_at: datetime
    reason: str
    platform: str = "opentrons"
    version: str = "1"
    generation: GenerationInfo | None = None

    def __post_init__(self) -> None:
        _aware(self.created_at, "created_at")
        if self.author == "agent" and self.generation is None:
            raise ValueError("agent-authored revisions require generation info")

    @classmethod
    def from_source(
        cls,
        source: str,
        author: str,
        reason: str,
        created_at: datetime | None = None,
        *,
        platform: str = "opentrons",
        version: str = "1",
        generation: GenerationInfo | None = None,
    ) -> ProtocolRevision:
        return cls(sha256_text(source), author, created_at or _now(), reason, platform, version, generation)

    @property
    def human_edited(self) -> bool:
        return self.generation is None or self.source_sha256 != self.generation.generated_sha256

    def to_dict(self) -> dict[str, object]:
        return {
            "source_sha256": self.source_sha256,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "reason": self.reason,
            "platform": self.platform,
            "version": self.version,
            "generation": self.generation.to_dict() if self.generation else None,
            "human_edited": self.human_edited,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ProtocolRevision:
        generation = data.get("generation")
        return cls(
            str(data["source_sha256"]),
            str(data["author"]),
            _dt(data["created_at"]),
            str(data["reason"]),
            str(data.get("platform", "opentrons")),
            str(data.get("version", "1")),
            GenerationInfo.from_dict(cast(dict[str, object], generation)) if generation else None,
        )


ProtocolRef = ProtocolRevision


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationSource(StrEnum):
    STATIC = "static"
    SIMULATION = "simulation"
    AI_REVIEW = "ai_review"


@dataclass(frozen=True)
class ValidationResult:
    check: str
    passed: bool
    message: str = ""
    severity: ValidationSeverity = ValidationSeverity.ERROR
    source: ValidationSource = ValidationSource.STATIC

    def to_dict(self) -> dict[str, object]:
        return {
            "check": self.check,
            "passed": self.passed,
            "message": self.message,
            "severity": self.severity.value,
            "source": self.source.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ValidationResult:
        return cls(
            str(data["check"]),
            bool(data["passed"]),
            str(data.get("message", "")),
            ValidationSeverity(str(data.get("severity", "error"))),
            ValidationSource(str(data.get("source", "static"))),
        )


@dataclass(frozen=True)
class StatusChange:
    from_status: RunStatus
    to_status: RunStatus
    actor: str
    at: datetime = field(default_factory=_now)
    note: str = ""
    protocol_sha256: str | None = None

    def __post_init__(self) -> None:
        _aware(self.at, "at")

    def to_dict(self) -> dict[str, object]:
        return {
            "from": self.from_status.value,
            "to": self.to_status.value,
            "actor": self.actor,
            "at": self.at.isoformat(),
            "note": self.note,
            "protocol_sha256": self.protocol_sha256,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> StatusChange:
        return cls(
            RunStatus(str(data["from"])),
            RunStatus(str(data["to"])),
            str(data["actor"]),
            _dt(data["at"]),
            str(data.get("note", "")),
            cast(str | None, data.get("protocol_sha256")),
        )


@dataclass(frozen=True)
class Clarification:
    question: str
    asked_at: datetime
    answer: str | None = None
    answered_by: str | None = None
    answered_at: datetime | None = None

    def __post_init__(self) -> None:
        _aware(self.asked_at, "asked_at")
        if self.answered_at is not None:
            _aware(self.answered_at, "answered_at")

    def to_dict(self) -> dict[str, object]:
        return {
            "question": self.question,
            "asked_at": self.asked_at.isoformat(),
            "answer": self.answer,
            "answered_by": self.answered_by,
            "answered_at": self.answered_at.isoformat() if self.answered_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Clarification:
        answered_at = data.get("answered_at")
        return cls(
            str(data["question"]),
            _dt(data["asked_at"]),
            cast(str | None, data.get("answer")),
            cast(str | None, data.get("answered_by")),
            _dt(answered_at) if answered_at else None,
        )


@dataclass(frozen=True)
class LabwarePlacement:
    slot: str
    load_name: str
    label: str
    inventory_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> LabwarePlacement:
        return cls(
            str(d["slot"]),
            str(d["load_name"]),
            str(d["label"]),
            cast(str | None, d.get("inventory_id")),
        )


@dataclass(frozen=True)
class Consumable:
    name: str
    quantity: float
    unit: str
    inventory_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> Consumable:
        return cls(
            str(d["name"]),
            float(cast(float, d["quantity"])),
            str(d["unit"]),
            cast(str | None, d.get("inventory_id")),
        )


@dataclass(frozen=True)
class ExternalRef:
    system: str
    kind: str
    id: str

    def to_dict(self) -> dict[str, object]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> ExternalRef:
        return cls(str(d["system"]), str(d["kind"]), str(d["id"]))


@dataclass
class RunRecord:
    request: Request
    tenant_id: str
    lab_profile_id: str
    protocol_revisions: list[ProtocolRevision] = field(default_factory=list)
    deck: list[LabwarePlacement] = field(default_factory=list)
    parameters: dict[str, object] = field(default_factory=dict)
    validations: list[ValidationResult] = field(default_factory=list)
    consumables: list[Consumable] = field(default_factory=list)
    external_refs: list[ExternalRef] = field(default_factory=list)
    clarifications: list[Clarification] = field(default_factory=list)
    history: list[StatusChange] = field(default_factory=list)
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    version: int = 0
    schema_version: str = SCHEMA_VERSION

    @property
    def status(self) -> RunStatus:
        return self.history[-1].to_status if self.history else RunStatus.REQUESTED

    @property
    def protocol(self) -> ProtocolRevision | None:
        return self.protocol_revisions[-1] if self.protocol_revisions else None

    @property
    def human_edited(self) -> bool:
        if not self.protocol:
            return False
        generated = next(
            (r.generation.generated_sha256 for r in reversed(self.protocol_revisions) if r.generation is not None),
            None,
        )
        return generated is not None and self.protocol.source_sha256 != generated

    @property
    def validated(self) -> bool:
        return bool(self.validations) and not any(
            not v.passed and v.severity is ValidationSeverity.ERROR for v in self.validations
        )

    def add_protocol_revision(self, revision: ProtocolRevision) -> None:
        if self.status not in _PROTOCOL_EDITABLE:
            raise ProtocolLocked(f"cannot revise the protocol of a {self.status.value} run")
        self.protocol_revisions.append(revision)
        self.validations.clear()
        if self.status is RunStatus.APPROVED:
            self.transition(
                RunStatus.DRAFT,
                revision.author,
                "protocol changed after approval",
                at=revision.created_at,
            )

    def transition(self, to_status: RunStatus, actor: str, note: str = "", at: datetime | None = None) -> StatusChange:
        current = self.status
        if to_status not in ALLOWED_TRANSITIONS[current]:
            raise InvalidTransition(f"cannot move from {current.value} to {to_status.value}")
        if to_status is RunStatus.APPROVED:
            if self.protocol is None:
                raise InvalidTransition("cannot approve a run with no protocol")
            if not self.validated:
                raise InvalidTransition("cannot approve a run that has not passed validation")
        approval = self.approval
        if to_status is RunStatus.RUNNING and (
            self.protocol is None or approval is None or approval.protocol_sha256 != self.protocol.source_sha256
        ):
            raise ProtocolChangedSinceApproval("protocol bytes changed since approval")
        protocol_hash = self.protocol.source_sha256 if to_status is RunStatus.APPROVED and self.protocol else None
        change = StatusChange(current, to_status, actor, at or _now(), note, protocol_hash)
        self.history.append(change)
        return change

    def _last_change_to(self, statuses: set[RunStatus]) -> StatusChange | None:
        return next((c for c in reversed(self.history) if c.to_status in statuses), None)

    @property
    def approval(self) -> StatusChange | None:
        return self._last_change_to({RunStatus.APPROVED})

    @property
    def started_at(self) -> datetime | None:
        change = self._last_change_to({RunStatus.RUNNING})
        return change.at if change else None

    @property
    def ended_at(self) -> datetime | None:
        change = self._last_change_to(_TERMINAL)
        return change.at if change else None

    @property
    def turnaround_time(self) -> timedelta | None:
        return self.ended_at - self.request.submitted_at if self.ended_at else None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "lab_profile_id": self.lab_profile_id,
            "version": self.version,
            "status": self.status.value,
            "request": self.request.to_dict(),
            "protocol_revisions": [p.to_dict() for p in self.protocol_revisions],
            "deck": [p.to_dict() for p in self.deck],
            "parameters": self.parameters,
            "validations": [v.to_dict() for v in self.validations],
            "consumables": [c.to_dict() for c in self.consumables],
            "external_refs": [r.to_dict() for r in self.external_refs],
            "clarifications": [c.to_dict() for c in self.clarifications],
            "history": [h.to_dict() for h in self.history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunRecord:
        upgraded = upgrade_document(data)
        return cls(
            Request.from_dict(upgraded["request"]),
            upgraded["tenant_id"],
            upgraded["lab_profile_id"],
            [ProtocolRevision.from_dict(v) for v in upgraded.get("protocol_revisions", [])],
            [LabwarePlacement.from_dict(v) for v in upgraded.get("deck", [])],
            upgraded.get("parameters", {}),
            [ValidationResult.from_dict(v) for v in upgraded.get("validations", [])],
            [Consumable.from_dict(v) for v in upgraded.get("consumables", [])],
            [ExternalRef.from_dict(v) for v in upgraded.get("external_refs", [])],
            [Clarification.from_dict(v) for v in upgraded.get("clarifications", [])],
            [StatusChange.from_dict(v) for v in upgraded.get("history", [])],
            upgraded["run_id"],
            upgraded.get("version", 0),
            SCHEMA_VERSION,
        )

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), **kwargs)

    @classmethod
    def from_json(cls, text: str) -> RunRecord:
        return cls.from_dict(json.loads(text))


def upgrade_v02_to_v03(data: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(data)
    protocol = result.pop("protocol", None)
    result["schema_version"] = "0.3"
    result.setdefault("tenant_id", "default")
    result.setdefault("lab_profile_id", "default")
    result.setdefault("version", 0)
    result.setdefault("clarifications", [])
    result["protocol_revisions"] = []
    if protocol:
        generation = {
            "model": protocol["generated_by"],
            "effort": "legacy",
            "prompt_version": "legacy-0.2",
            "gladys_version": "0.1.0",
            "trace_id": "legacy",
            "generated_sha256": protocol["generated_sha256"],
            "generated_at": protocol["generated_at"],
        }
        result["protocol_revisions"].append(
            {
                "source_sha256": protocol["source_sha256"],
                "author": "agent",
                "created_at": protocol["generated_at"],
                "reason": "generation",
                "platform": protocol["platform"],
                "version": protocol["version"],
                "generation": generation,
            }
        )
    for validation in result.get("validations", []):
        validation.setdefault("severity", "error")
        validation.setdefault("source", "static")
    for change in result.get("history", []):
        change.setdefault(
            "protocol_sha256",
            protocol["source_sha256"] if protocol and change["to"] == "approved" else None,
        )
    if not result.get("history"):
        result["history"] = [
            {
                "from": "requested",
                "to": "generating",
                "actor": "migration",
                "at": result["request"]["submitted_at"],
                "note": "migrated from 0.2",
                "protocol_sha256": None,
            },
            {
                "from": "generating",
                "to": "draft",
                "actor": "migration",
                "at": result["request"]["submitted_at"],
                "note": "migrated from 0.2",
                "protocol_sha256": None,
            },
        ]
    return result


def upgrade_document(data: dict[str, Any]) -> dict[str, Any]:
    version = data.get("schema_version", "0.2")
    if version == "0.2":
        return upgrade_v02_to_v03(data)
    if version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema version: {version}")
    return copy.deepcopy(data)
