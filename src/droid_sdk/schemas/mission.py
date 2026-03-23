"""Mission decomposition schemas for the Factory Droid protocol.

Ported from TypeScript source:
- packages/common/src/droid/schemas/mission-decomposition.ts
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from droid_sdk.schemas.enums import (  # noqa: TC001
    DismissalType,
    FeatureStatus,
    FeatureSuccessState,
    IssueSeverity,
    ProgressLogEntryType,
)

__all__ = [
    "DiscoveredIssue",
    "DismissalRecord",
    "Handoff",
    "HandoffItemsDismissedEntry",
    "InteractiveCheck",
    "MilestoneValidationTriggeredEntry",
    "MissionAcceptedEntry",
    "MissionFeature",
    "MissionPausedEntry",
    "MissionResumedEntry",
    "MissionRunStartedEntry",
    "ProgressLogEntry",
    "SkillDeviation",
    "SkillFeedback",
    "TestCase",
    "TestFile",
    "Tests",
    "Verification",
    "VerificationCommand",
    "WorkerCompletedEntry",
    "WorkerFailedEntry",
    "WorkerPausedEntry",
    "WorkerSelectedFeatureEntry",
    "WorkerStartedEntry",
]


# ============================================================
# Feature schema
# ============================================================


class MissionFeature(BaseModel):
    """Mission feature schema.

    Represents a single unit of work in a mission decomposition.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str
    """Feature identifier."""

    description: str
    """Human-readable description of the feature."""

    status: FeatureStatus
    """Current lifecycle status."""

    skill_name: str = Field(alias="skillName")
    """Skill to use for implementing this feature."""

    preconditions: list[str]
    """List of prerequisite conditions (feature IDs or descriptions)."""

    expected_behavior: list[str] = Field(alias="expectedBehavior")
    """Expected behaviors when this feature is complete."""

    verification_steps: list[str] = Field(alias="verificationSteps")
    """Steps to verify the feature works correctly."""

    fulfills: list[str] | None = None
    """Optional validation contract assertion IDs this feature fulfills."""

    milestone: str | None = None
    """Optional milestone this feature belongs to."""

    worker_session_ids: list[str] | None = Field(default=None, alias="workerSessionIds")
    """Optional list of worker session IDs that have worked on this feature."""

    current_worker_session_id: str | None = Field(
        default=None, alias="currentWorkerSessionId"
    )
    """Optional current worker session ID (nullable)."""

    completed_worker_session_id: str | None = Field(
        default=None, alias="completedWorkerSessionId"
    )
    """Optional worker session ID that completed this feature (nullable)."""


# ============================================================
# Handoff-related schemas
# ============================================================


class DiscoveredIssue(BaseModel):
    """An issue discovered during feature implementation."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    severity: IssueSeverity
    """Issue severity level."""

    description: str
    """Description of the issue."""

    suggested_fix: str | None = Field(default=None, alias="suggestedFix")
    """Optional suggested fix for the issue."""


class VerificationCommand(BaseModel):
    """A command run during verification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    command: str
    """The shell command that was run."""

    exit_code: int = Field(alias="exitCode")
    """Exit code of the command."""

    observation: str
    """What was observed in the output."""


class InteractiveCheck(BaseModel):
    """An interactive check performed during verification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    action: str
    """What action was performed."""

    observed: str
    """What was observed as a result."""


class Verification(BaseModel):
    """Verification performed during feature implementation."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    commands_run: list[VerificationCommand] = Field(alias="commandsRun")
    """Shell commands run with their results."""

    interactive_checks: list[InteractiveCheck] | None = Field(
        default=None, alias="interactiveChecks"
    )
    """Optional interactive/UI checks performed."""


class TestCase(BaseModel):
    """A single test case."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str
    """Test case name."""

    verifies: str
    """What behavior this test verifies."""


class TestFile(BaseModel):
    """A test file with its test cases."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    file: str
    """Test file path."""

    cases: list[TestCase]
    """Test cases in this file."""


class Tests(BaseModel):
    """Test information for a feature implementation."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    added: list[TestFile]
    """Test files added."""

    updated: list[str] | None = None
    """Existing test files that were modified."""

    coverage: str
    """Summary of what the tests cover."""


class SkillDeviation(BaseModel):
    """A deviation from the skill procedure."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    step: str
    """Which skill step was deviated from."""

    what_i_did_instead: str = Field(alias="whatIDidInstead")
    """What was actually done."""

    why: str
    """Why the deviation occurred."""


class SkillFeedback(BaseModel):
    """Feedback on the skill procedure."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    followed_procedure: bool = Field(alias="followedProcedure")
    """Whether the skill procedure was followed as written."""

    deviations: list[SkillDeviation]
    """Details of any deviations from the procedure."""

    suggested_changes: list[str] | None = Field(default=None, alias="suggestedChanges")
    """Optional suggestions for improving the skill."""


class Handoff(BaseModel):
    """Worker handoff information.

    Contains all details about what was implemented, verified, and discovered.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    salient_summary: str | None = Field(default=None, alias="salientSummary")
    """Optional brief summary (1-4 sentences)."""

    what_was_implemented: str = Field(alias="whatWasImplemented")
    """Concrete description of what was built."""

    what_was_left_undone: str = Field(alias="whatWasLeftUndone")
    """What's incomplete. Empty string if everything is done."""

    verification: Verification
    """Verification performed."""

    tests: Tests
    """Test information."""

    discovered_issues: list[DiscoveredIssue] = Field(alias="discoveredIssues")
    """Issues found during implementation."""

    skill_feedback: SkillFeedback | None = Field(default=None, alias="skillFeedback")
    """Optional feedback on the skill procedure."""


class DismissalRecord(BaseModel):
    """A record of a dismissed handoff item."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: DismissalType
    """Type of the dismissed item."""

    source_feature_id: str = Field(alias="sourceFeatureId")
    """Feature ID that produced the dismissed item."""

    summary: str
    """Summary of the dismissed item."""

    justification: str
    """Justification for dismissing the item."""


# ============================================================
# Progress log entry schemas
# ============================================================


class _BaseProgressLogEntry(BaseModel):
    """Base schema for all progress log entries."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    timestamp: str
    """ISO 8601 timestamp of the event."""


class MissionAcceptedEntry(_BaseProgressLogEntry):
    """Mission was accepted by the orchestrator."""

    type: Literal[ProgressLogEntryType.MissionAccepted]
    """Entry type discriminator."""

    title: str
    """Mission title."""


class MissionPausedEntry(_BaseProgressLogEntry):
    """Mission was paused."""

    type: Literal[ProgressLogEntryType.MissionPaused]
    """Entry type discriminator."""


class MissionResumedEntry(_BaseProgressLogEntry):
    """Mission was resumed."""

    type: Literal[ProgressLogEntryType.MissionResumed]
    """Entry type discriminator."""


class MissionRunStartedEntry(_BaseProgressLogEntry):
    """A mission run was started."""

    type: Literal[ProgressLogEntryType.MissionRunStarted]
    """Entry type discriminator."""

    message: str | None = None
    """Optional message about the run."""


class WorkerStartedEntry(_BaseProgressLogEntry):
    """A worker was started."""

    type: Literal[ProgressLogEntryType.WorkerStarted]
    """Entry type discriminator."""

    worker_session_id: str = Field(alias="workerSessionId")
    """Worker session identifier."""

    spawn_id: str = Field(alias="spawnId")
    """Spawn identifier."""

    feature_id: str | None = Field(default=None, alias="featureId")
    """Optional feature ID the worker is assigned to."""


class WorkerSelectedFeatureEntry(_BaseProgressLogEntry):
    """A worker selected a feature to work on."""

    type: Literal[ProgressLogEntryType.WorkerSelectedFeature]
    """Entry type discriminator."""

    worker_session_id: str = Field(alias="workerSessionId")
    """Worker session identifier."""

    feature_id: str = Field(alias="featureId")
    """Feature ID that was selected."""


class WorkerCompletedEntry(_BaseProgressLogEntry):
    """A worker completed its task."""

    type: Literal[ProgressLogEntryType.WorkerCompleted]
    """Entry type discriminator."""

    worker_session_id: str = Field(alias="workerSessionId")
    """Worker session identifier."""

    feature_id: str = Field(alias="featureId")
    """Feature ID that was worked on."""

    success_state: FeatureSuccessState = Field(alias="successState")
    """Outcome of the work."""

    return_to_orchestrator: bool = Field(alias="returnToOrchestrator")
    """Whether control should return to the orchestrator."""

    commit_id: str | None = Field(default=None, alias="commitId")
    """Optional git commit ID."""

    exit_code: int = Field(alias="exitCode")
    """Worker process exit code."""

    validators_passed: bool | None = Field(default=None, alias="validatorsPassed")
    """Whether all validators passed."""

    handoff: Handoff | None = None
    """Optional detailed handoff information."""


class WorkerFailedEntry(_BaseProgressLogEntry):
    """A worker failed."""

    type: Literal[ProgressLogEntryType.WorkerFailed]
    """Entry type discriminator."""

    worker_session_id: str | None = Field(default=None, alias="workerSessionId")
    """Optional worker session identifier."""

    spawn_id: str = Field(alias="spawnId")
    """Spawn identifier."""

    exit_code: int | None = Field(default=None, alias="exitCode")
    """Optional exit code."""

    reason: str
    """Reason for the failure."""


class WorkerPausedEntry(_BaseProgressLogEntry):
    """A worker was paused."""

    type: Literal[ProgressLogEntryType.WorkerPaused]
    """Entry type discriminator."""

    worker_session_id: str = Field(alias="workerSessionId")
    """Worker session identifier."""

    feature_id: str | None = Field(default=None, alias="featureId")
    """Optional feature ID the worker was working on."""


class HandoffItemsDismissedEntry(_BaseProgressLogEntry):
    """Handoff items were dismissed by the orchestrator."""

    type: Literal[ProgressLogEntryType.HandoffItemsDismissed]
    """Entry type discriminator."""

    dismissals: list[DismissalRecord] | None = None
    """Optional list of dismissal records."""


class MilestoneValidationTriggeredEntry(_BaseProgressLogEntry):
    """Milestone validation was triggered."""

    type: Literal[ProgressLogEntryType.MilestoneValidationTriggered]
    """Entry type discriminator."""

    milestone: str
    """Milestone name."""

    feature_id: str = Field(alias="featureId")
    """Feature ID that triggered validation."""


# ============================================================
# Discriminated union over all 11 progress log entry types
# ============================================================

ProgressLogEntryUnion = Annotated[
    MissionAcceptedEntry
    | MissionPausedEntry
    | MissionResumedEntry
    | MissionRunStartedEntry
    | WorkerStartedEntry
    | WorkerSelectedFeatureEntry
    | WorkerCompletedEntry
    | WorkerFailedEntry
    | WorkerPausedEntry
    | HandoffItemsDismissedEntry
    | MilestoneValidationTriggeredEntry,
    Field(discriminator="type"),
]


class ProgressLogEntry(RootModel[ProgressLogEntryUnion]):
    """Discriminated union over all 11 progress log entry types.

    Dispatches on the ``type`` field to the appropriate entry model.
    """
