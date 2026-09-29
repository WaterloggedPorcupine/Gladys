"""Stateful property test: random sequences of *every* aggregate operation keep the run's invariants.

Transitions alone never reach APPROVED (approval needs a validated protocol), so the rules also add
revisions, record passing and failing validations, and ask/answer clarifications.
"""

from datetime import UTC, datetime
from typing import ClassVar

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    precondition,
    rule,
    run_state_machine_as_test,
)

from gladys.domain.records import (
    ALLOWED_TRANSITIONS,
    ClarificationNotAllowed,
    GenerationInfo,
    InvalidTransition,
    ProtocolLocked,
    ProtocolRevision,
    Request,
    RunRecord,
    RunStatus,
    StatusChange,
    ValidationRejected,
    ValidationResult,
    ValidationSeverity,
    sha256_text,
)

T0 = datetime(2026, 9, 28, 9, tzinfo=UTC)
EDITABLE = {RunStatus.GENERATING, RunStatus.DRAFT, RunStatus.APPROVED}
VALIDATION_OPEN = {RunStatus.GENERATING, RunStatus.DRAFT}
TERMINAL = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.ABORTED}
# Hypothesis favors the first element of sampled_from. Alphabetical order would put ABORTED first from
# almost every state, so most examples would abort early. This order puts each state's forward move first
# (e.g. DRAFT -> APPROVED before DRAFT -> GENERATING); failure exits come last.
PROGRESS = [
    RunStatus.APPROVED,
    RunStatus.RUNNING,
    RunStatus.COMPLETED,
    RunStatus.DRAFT,
    RunStatus.GENERATING,
    RunStatus.GENERATION_FAILED,
    RunStatus.FAILED,
    RunStatus.ABORTED,
]

# Use @precondition (skips a rule) rather than assume() inside a rule: a failed assume() discards the
# whole example, which silently prevents long sequences (and so APPROVED/RUNNING) from ever being explored.


class RunMachine(RuleBasedStateMachine):
    visited: ClassVar[set[str]] = set()

    def __init__(self) -> None:
        super().__init__()
        self.run = RunRecord(Request("transfer", "scientist", T0), "tenant", "lab")
        self.seen_history: tuple[StatusChange, ...] = ()

    @initialize(start=st.sampled_from([RunStatus.REQUESTED, RunStatus.DRAFT, RunStatus.APPROVED, RunStatus.RUNNING]))
    def fast_forward(self, start: RunStatus) -> None:
        """Start some examples deep in the lifecycle (via the real methods), so rules get many steps there."""
        if start is RunStatus.REQUESTED:
            return
        self.run.transition(RunStatus.GENERATING, "worker", at=T0)
        self.run.add_protocol_revision(ProtocolRevision.from_source("start", "scientist", "human_edit", T0))
        assert self.run.protocol is not None
        self.run.record_validation(ValidationResult("sim", True, protocol_sha256=self.run.protocol.source_sha256))
        self.run.transition(RunStatus.DRAFT, "agent", at=T0)
        if start is not RunStatus.DRAFT:
            self.run.transition(RunStatus.APPROVED, "reviewer", at=T0)
        if start is RunStatus.RUNNING:
            self.run.transition(RunStatus.RUNNING, "operator", at=T0)

    # --- transitions -----------------------------------------------------------------------------------

    @precondition(lambda self: self.run.status not in TERMINAL)
    @rule(data=st.data())
    def allowed_transition(self, data: st.DataObject) -> None:
        options = [s for s in PROGRESS if s in ALLOWED_TRANSITIONS[self.run.status]]
        target = data.draw(st.sampled_from(options))
        before = self.run.history
        if target is RunStatus.APPROVED and not self.run.validated:
            try:
                self.run.transition(target, "reviewer", at=T0)
            except InvalidTransition:
                assert self.run.history == before
                return
            raise AssertionError("approved a run without a validated protocol")
        # Every other allowed move must succeed; in particular APPROVED -> RUNNING, because the approved
        # hash always equals the current hash (an edit after approval sends the run back to DRAFT).
        self.run.transition(target, "actor", at=T0)
        self.visited.add(target.value)

    @rule(data=st.data())
    def disallowed_transition(self, data: st.DataObject) -> None:
        # NEEDS_CLARIFICATION is only reachable through ask_clarification, so transition() always refuses it.
        forbidden = set(RunStatus) - ALLOWED_TRANSITIONS[self.run.status] | {RunStatus.NEEDS_CLARIFICATION}
        status = data.draw(st.sampled_from(sorted(forbidden)))
        before = self.run.history
        try:
            self.run.transition(status, "actor", at=T0)
        except InvalidTransition:
            assert self.run.history == before
        else:
            raise AssertionError(f"moved {self.run.history[-2].to_status} -> {status}")

    # --- protocol and evidence -------------------------------------------------------------------------

    @rule(source=st.sampled_from(["a", "b", "c"]), by_agent=st.booleans())
    def add_revision(self, source: str, by_agent: bool) -> None:
        generation = GenerationInfo("m", "high", "v1", "0.1", "t", sha256_text(source), T0) if by_agent else None
        revision = ProtocolRevision.from_source(
            source, "agent" if by_agent else "scientist", "revision", T0, generation=generation
        )
        status, revisions = self.run.status, self.run.protocol_revisions
        if status not in EDITABLE:
            try:
                self.run.add_protocol_revision(revision)
            except ProtocolLocked:
                assert self.run.protocol_revisions == revisions
                return
            raise AssertionError(f"revised a {status} run")
        self.run.add_protocol_revision(revision)
        assert self.run.protocol == revision
        if status is RunStatus.APPROVED:
            assert self.run.status is RunStatus.DRAFT
            assert self.run.approval is None
            self.visited.add("approval withdrawn")

    @rule(passed=st.booleans(), severity=st.sampled_from(list(ValidationSeverity)))
    def record_validation(self, passed: bool, severity: ValidationSeverity) -> None:
        protocol = self.run.protocol
        result = ValidationResult(
            "check", passed, severity=severity, protocol_sha256=protocol.source_sha256 if protocol else "0" * 64
        )
        if protocol is None or self.run.status not in VALIDATION_OPEN:
            try:
                self.run.record_validation(result)
            except ValidationRejected:
                return
            raise AssertionError("recorded a validation that should have been rejected")
        self.run.record_validation(result)
        if not passed and severity is ValidationSeverity.ERROR:
            assert not self.run.validated
            self.visited.add("failing validation")

    # --- clarifications --------------------------------------------------------------------------------

    @rule()
    def ask_clarification(self) -> None:
        if self.run.status is not RunStatus.GENERATING:
            try:
                self.run.ask_clarification(["which plate?"], "agent", at=T0)
            except InvalidTransition:
                return
            raise AssertionError("asked for clarification outside GENERATING")
        self.run.ask_clarification(["which plate?"], "agent", at=T0)
        self.visited.add(RunStatus.NEEDS_CLARIFICATION.value)

    @precondition(lambda self: any(c.answer is None for c in self.run.clarifications))
    @rule()
    def answer_clarification(self) -> None:
        unanswered = [i for i, c in enumerate(self.run.clarifications) if c.answer is None]
        if self.run.status is RunStatus.NEEDS_CLARIFICATION:
            self.run.answer_clarification(unanswered[0], "the 96-well one", "scientist", at=T0)
            self.visited.add("clarification answered")
        else:
            try:
                self.run.answer_clarification(unanswered[0], "late", "scientist", at=T0)
            except ClarificationNotAllowed:
                return
            raise AssertionError("answered a clarification outside NEEDS_CLARIFICATION")

    # --- invariants ------------------------------------------------------------------------------------

    @invariant()
    def history_is_append_only_and_chained(self) -> None:
        history = self.run.history
        assert history[: len(self.seen_history)] == self.seen_history
        previous = RunStatus.REQUESTED
        for change in history:
            assert change.from_status is previous
            assert change.to_status in ALLOWED_TRANSITIONS[change.from_status]
            previous = change.to_status
        self.seen_history = history

    @invariant()
    def approval_binds_to_the_current_bytes(self) -> None:
        if self.run.status in {RunStatus.APPROVED, RunStatus.RUNNING}:
            assert self.run.approval is not None and self.run.protocol is not None
            assert self.run.approval.protocol_sha256 == self.run.protocol.source_sha256

    @invariant()
    def only_current_validations_count(self) -> None:
        current = self.run.protocol.source_sha256 if self.run.protocol else None
        assert all(v.protocol_sha256 == current for v in self.run.current_validations)

    @invariant()
    def round_trips_through_its_document(self) -> None:
        assert RunRecord.from_dict(self.run.to_dict()) == self.run


def test_random_operation_sequences_keep_invariants_and_reach_deep_states() -> None:
    RunMachine.visited = set()
    run_state_machine_as_test(
        RunMachine,
        settings=settings(max_examples=150, stateful_step_count=30, derandomize=True, database=None, deadline=None),
    )
    deep = {"approved", "running", "completed", "approval withdrawn", "failing validation", "clarification answered"}
    assert deep <= RunMachine.visited, deep - RunMachine.visited
