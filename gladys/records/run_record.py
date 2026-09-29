"""Structured, platform-neutral record of a single Gladys run.

A RunRecord is the data contract between Gladys and downstream systems
(ELN, LIMS, data lake). It carries the full provenance chain: what was
asked, what protocol was generated (and by which model), how it was
checked, who moved it through each stage, and what happened when it ran.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

SCHEMA_VERSION = "0.2"


class RunStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.DRAFT: frozenset({RunStatus.APPROVED, RunStatus.ABORTED}),
    RunStatus.APPROVED: frozenset({RunStatus.RUNNING, RunStatus.DRAFT, RunStatus.ABORTED}),
    RunStatus.RUNNING: frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.ABORTED}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.ABORTED: frozenset(),
}

_TERMINAL = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.ABORTED}


class InvalidTransition(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _dt_out(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _dt_in(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass
class Request:
    """The scientist's original request, verbatim."""

    text: str
    requested_by: str
    submitted_at: datetime = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "requested_by": self.requested_by,
            "submitted_at": _dt_out(self.submitted_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Request:
        return cls(data["text"], data["requested_by"], _dt_in(data["submitted_at"]))


@dataclass
class ProtocolRef:
    """Identifies the exact protocol by content hash, with AI provenance.

    `generated_sha256` is the hash of the model's original output and
    `source_sha256` the hash of the final protocol. If they differ, a human
    edited the protocol before it was recorded.
    """

    platform: str
    version: str
    source_sha256: str
    generated_by: str
    generated_sha256: str
    generated_at: datetime = field(default_factory=_now)

    @classmethod
    def from_source(
        cls,
        source: str,
        platform: str,
        version: str,
        generated_by: str,
        generated_source: str | None = None,
        generated_at: datetime | None = None,
    ) -> ProtocolRef:
        """`generated_source` is the model's original output; omit it if unedited."""
        original = source if generated_source is None else generated_source
        return cls(
            platform=platform,
            version=version,
            source_sha256=_sha256(source),
            generated_by=generated_by,
            generated_sha256=_sha256(original),
            generated_at=generated_at or _now(),
        )

    @property
    def human_edited(self) -> bool:
        return self.source_sha256 != self.generated_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "version": self.version,
            "source_sha256": self.source_sha256,
            "generated_by": self.generated_by,
            "generated_sha256": self.generated_sha256,
            "generated_at": _dt_out(self.generated_at),
            "human_edited": self.human_edited,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProtocolRef:
        return cls(
            data["platform"],
            data["version"],
            data["source_sha256"],
            data["generated_by"],
            data["generated_sha256"],
            _dt_in(data["generated_at"]),
        )


@dataclass
class LabwarePlacement:
    """A piece of labware on the deck.

    `label` is the semantic name used across requests, protocols and
    records (e.g. "source_plate"); `load_name` is the platform's own id;
    `inventory_id` links to the lab's inventory system, if any.
    """

    slot: str
    load_name: str
    label: str
    inventory_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "load_name": self.load_name,
            "label": self.label,
            "inventory_id": self.inventory_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LabwarePlacement:
        return cls(data["slot"], data["load_name"], data["label"], data.get("inventory_id"))


@dataclass
class ValidationResult:
    check: str
    passed: bool
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"check": self.check, "passed": self.passed, "message": self.message}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValidationResult:
        return cls(data["check"], data["passed"], data.get("message", ""))


@dataclass
class Consumable:
    name: str
    quantity: float
    unit: str
    inventory_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "quantity": self.quantity,
            "unit": self.unit,
            "inventory_id": self.inventory_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Consumable:
        return cls(data["name"], data["quantity"], data["unit"], data.get("inventory_id"))


@dataclass
class ExternalRef:
    """A pointer to the same work in another system.

    e.g. ExternalRef("cheminventory", "idea", "421393") links this run back
    to the design idea it is making or testing.
    """

    system: str
    kind: str
    id: str

    def to_dict(self) -> dict[str, Any]:
        return {"system": self.system, "kind": self.kind, "id": self.id}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExternalRef:
        return cls(data["system"], data["kind"], data["id"])


@dataclass
class StatusChange:
    """One entry in a run's audit trail."""

    from_status: RunStatus
    to_status: RunStatus
    actor: str
    at: datetime = field(default_factory=_now)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_status.value,
            "to": self.to_status.value,
            "actor": self.actor,
            "at": _dt_out(self.at),
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StatusChange:
        return cls(
            RunStatus(data["from"]),
            RunStatus(data["to"]),
            data["actor"],
            _dt_in(data["at"]),
            data.get("note", ""),
        )


@dataclass
class RunRecord:
    request: Request
    protocol: ProtocolRef | None = None
    deck: list[LabwarePlacement] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    validations: list[ValidationResult] = field(default_factory=list)
    consumables: list[Consumable] = field(default_factory=list)
    external_refs: list[ExternalRef] = field(default_factory=list)
    history: list[StatusChange] = field(default_factory=list)
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    schema_version: str = SCHEMA_VERSION

    @property
    def status(self) -> RunStatus:
        return self.history[-1].to_status if self.history else RunStatus.DRAFT

    @property
    def validated(self) -> bool:
        """True when at least one check ran and every check passed."""
        return bool(self.validations) and all(v.passed for v in self.validations)

    def transition(
        self,
        to_status: RunStatus,
        actor: str,
        note: str = "",
        at: datetime | None = None,
    ) -> StatusChange:
        """Move the run to a new status, appending to the audit trail."""
        current = self.status
        if to_status not in ALLOWED_TRANSITIONS[current]:
            raise InvalidTransition(f"cannot move from {current.value} to {to_status.value}")
        if to_status is RunStatus.APPROVED:
            if self.protocol is None:
                raise InvalidTransition("cannot approve a run with no protocol")
            if not self.validated:
                raise InvalidTransition("cannot approve a run that has not passed validation")
        change = StatusChange(current, to_status, actor, at or _now(), note)
        self.history.append(change)
        return change

    def _last_change_to(self, statuses: set[RunStatus]) -> StatusChange | None:
        for change in reversed(self.history):
            if change.to_status in statuses:
                return change
        return None

    @property
    def approval(self) -> StatusChange | None:
        """The most recent approval, if the run is currently past draft."""
        if self.status is RunStatus.DRAFT:
            return None
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
        """Request submitted to run ended, or None if the run hasn't ended."""
        ended = self.ended_at
        return ended - self.request.submitted_at if ended else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "status": self.status.value,
            "request": self.request.to_dict(),
            "protocol": self.protocol.to_dict() if self.protocol else None,
            "deck": [p.to_dict() for p in self.deck],
            "parameters": self.parameters,
            "validations": [v.to_dict() for v in self.validations],
            "consumables": [c.to_dict() for c in self.consumables],
            "external_refs": [r.to_dict() for r in self.external_refs],
            "history": [h.to_dict() for h in self.history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunRecord:
        return cls(
            request=Request.from_dict(data["request"]),
            protocol=ProtocolRef.from_dict(data["protocol"]) if data.get("protocol") else None,
            deck=[LabwarePlacement.from_dict(p) for p in data.get("deck", [])],
            parameters=data.get("parameters", {}),
            validations=[ValidationResult.from_dict(v) for v in data.get("validations", [])],
            consumables=[Consumable.from_dict(c) for c in data.get("consumables", [])],
            external_refs=[ExternalRef.from_dict(r) for r in data.get("external_refs", [])],
            history=[StatusChange.from_dict(h) for h in data.get("history", [])],
            run_id=data["run_id"],
            schema_version=data.get("schema_version", SCHEMA_VERSION),
        )

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), **kwargs)

    @classmethod
    def from_json(cls, text: str) -> RunRecord:
        return cls.from_dict(json.loads(text))
