"""Tests for mission decomposition schemas."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from droid_sdk.schemas.enums import (
    DismissalType,
    FeatureStatus,
    FeatureSuccessState,
    IssueSeverity,
    ProgressLogEntryType,
)
from droid_sdk.schemas.mission import (
    DiscoveredIssue,
    DismissalRecord,
    Handoff,
    HandoffItemsDismissedEntry,
    InteractiveCheck,
    MilestoneValidationTriggeredEntry,
    MissionAcceptedEntry,
    MissionFeature,
    MissionPausedEntry,
    MissionResumedEntry,
    MissionRunStartedEntry,
    ProgressLogEntry,
    SkillDeviation,
    SkillFeedback,
    TestCase,
    TestFile,
    Tests,
    Verification,
    VerificationCommand,
    WorkerCompletedEntry,
    WorkerFailedEntry,
    WorkerPausedEntry,
    WorkerSelectedFeatureEntry,
    WorkerStartedEntry,
)

# ============================================================
# MissionFeature
# ============================================================


class TestMissionFeature:
    """Tests for MissionFeature schema."""

    def test_construction_required_fields(self) -> None:
        """Construct with required fields only."""
        feature = MissionFeature(
            id="feature-1",
            description="Build the thing",
            status=FeatureStatus.Pending,
            skill_name="python-sdk-worker",
            preconditions=["dep-1"],
            expected_behavior=["it works"],
            verification_steps=["run tests"],
        )
        assert feature.id == "feature-1"
        assert feature.description == "Build the thing"
        assert feature.status == FeatureStatus.Pending
        assert feature.skill_name == "python-sdk-worker"
        assert feature.preconditions == ["dep-1"]
        assert feature.expected_behavior == ["it works"]
        assert feature.verification_steps == ["run tests"]
        assert feature.fulfills is None
        assert feature.milestone is None
        assert feature.worker_session_ids is None
        assert feature.current_worker_session_id is None
        assert feature.completed_worker_session_id is None

    def test_construction_all_fields(self) -> None:
        """Construct with all fields including optional ones."""
        feature = MissionFeature(
            id="feature-2",
            description="Full feature",
            status=FeatureStatus.Completed,
            skill_name="python-sdk-worker",
            preconditions=[],
            expected_behavior=["everything works"],
            verification_steps=["pytest -v"],
            fulfills=["VAL-001", "VAL-002"],
            milestone="foundation",
            worker_session_ids=["sess-1", "sess-2"],
            current_worker_session_id="sess-2",
            completed_worker_session_id="sess-1",
        )
        assert feature.fulfills == ["VAL-001", "VAL-002"]
        assert feature.milestone == "foundation"
        assert feature.worker_session_ids == ["sess-1", "sess-2"]
        assert feature.current_worker_session_id == "sess-2"
        assert feature.completed_worker_session_id == "sess-1"

    def test_camel_case_serialization(self) -> None:
        """Serialization with by_alias=True produces camelCase keys."""
        feature = MissionFeature(
            id="f",
            description="d",
            status=FeatureStatus.InProgress,
            skill_name="sk",
            preconditions=[],
            expected_behavior=[],
            verification_steps=[],
            worker_session_ids=["a"],
            current_worker_session_id="a",
        )
        data = feature.model_dump(by_alias=True)
        assert "skillName" in data
        assert "expectedBehavior" in data
        assert "verificationSteps" in data
        assert "workerSessionIds" in data
        assert "currentWorkerSessionId" in data

    def test_deserialization_from_camel_case(self) -> None:
        """Parse from camelCase JSON."""
        raw = {
            "id": "f1",
            "description": "desc",
            "status": "pending",
            "skillName": "worker",
            "preconditions": [],
            "expectedBehavior": ["works"],
            "verificationSteps": ["test"],
        }
        feature = MissionFeature.model_validate(raw)
        assert feature.skill_name == "worker"
        assert feature.expected_behavior == ["works"]

    def test_json_roundtrip(self) -> None:
        """model_validate_json(model_dump_json()) produces equal model."""
        feature = MissionFeature(
            id="f",
            description="d",
            status=FeatureStatus.Pending,
            skill_name="sk",
            preconditions=["p1"],
            expected_behavior=["e1"],
            verification_steps=["v1"],
            fulfills=["VAL-001"],
            milestone="m1",
        )
        roundtripped = MissionFeature.model_validate_json(
            feature.model_dump_json(by_alias=True)
        )
        assert roundtripped == feature

    def test_extra_field_allowed(self) -> None:
        """Response models tolerate extra fields for protocol evolution."""
        feature = MissionFeature.model_validate(
            {
                "id": "f",
                "description": "d",
                "status": "pending",
                "skillName": "sk",
                "preconditions": [],
                "expectedBehavior": [],
                "verificationSteps": [],
                "extraField": "tolerated",
            }
        )
        assert feature.id == "f"

    def test_null_current_worker_session_id(self) -> None:
        """currentWorkerSessionId can be null."""
        feature = MissionFeature(
            id="f",
            description="d",
            status=FeatureStatus.Pending,
            skill_name="sk",
            preconditions=[],
            expected_behavior=[],
            verification_steps=[],
            current_worker_session_id=None,
        )
        assert feature.current_worker_session_id is None


# ============================================================
# DiscoveredIssue
# ============================================================


class TestDiscoveredIssue:
    """Tests for DiscoveredIssue schema."""

    def test_construction(self) -> None:
        """Construct with required and optional fields."""
        issue = DiscoveredIssue(
            severity=IssueSeverity.Blocking,
            description="Something is broken",
            suggested_fix="Fix the thing",
        )
        assert issue.severity == IssueSeverity.Blocking
        assert issue.description == "Something is broken"
        assert issue.suggested_fix == "Fix the thing"

    def test_optional_suggested_fix(self) -> None:
        """suggestedFix is optional."""
        issue = DiscoveredIssue(
            severity=IssueSeverity.NonBlocking,
            description="Minor issue",
        )
        assert issue.suggested_fix is None

    def test_camel_case_serialization(self) -> None:
        """Serialization produces camelCase keys."""
        issue = DiscoveredIssue(
            severity=IssueSeverity.Suggestion,
            description="desc",
            suggested_fix="fix",
        )
        data = issue.model_dump(by_alias=True)
        assert "suggestedFix" in data

    def test_json_roundtrip(self) -> None:
        issue = DiscoveredIssue(severity=IssueSeverity.Blocking, description="d")
        roundtripped = DiscoveredIssue.model_validate_json(
            issue.model_dump_json(by_alias=True)
        )
        assert roundtripped == issue


# ============================================================
# VerificationCommand and Verification
# ============================================================


class TestVerification:
    """Tests for VerificationCommand, InteractiveCheck, Verification schemas."""

    def test_verification_command(self) -> None:
        """Construct VerificationCommand."""
        cmd = VerificationCommand(
            command="uv run pytest",
            exit_code=0,
            observation="All tests passed",
        )
        assert cmd.command == "uv run pytest"
        assert cmd.exit_code == 0
        assert cmd.observation == "All tests passed"

    def test_verification_command_camel_case(self) -> None:
        """Serialization produces camelCase keys."""
        cmd = VerificationCommand(command="cmd", exit_code=1, observation="obs")
        data = cmd.model_dump(by_alias=True)
        assert "exitCode" in data

    def test_interactive_check(self) -> None:
        """Construct InteractiveCheck."""
        check = InteractiveCheck(action="clicked button", observed="page loaded")
        assert check.action == "clicked button"
        assert check.observed == "page loaded"

    def test_verification_minimal(self) -> None:
        """Verification with only commandsRun."""
        v = Verification(
            commands_run=[
                VerificationCommand(command="test", exit_code=0, observation="ok")
            ]
        )
        assert len(v.commands_run) == 1
        assert v.interactive_checks is None

    def test_verification_all_fields(self) -> None:
        """Verification with both commandsRun and interactiveChecks."""
        v = Verification(
            commands_run=[
                VerificationCommand(command="test", exit_code=0, observation="ok")
            ],
            interactive_checks=[InteractiveCheck(action="a", observed="b")],
        )
        assert v.interactive_checks is not None
        assert len(v.interactive_checks) == 1

    def test_verification_camel_case(self) -> None:
        """Serialization produces camelCase keys."""
        v = Verification(
            commands_run=[
                VerificationCommand(command="c", exit_code=0, observation="o")
            ],
            interactive_checks=[InteractiveCheck(action="a", observed="b")],
        )
        data = v.model_dump(by_alias=True)
        assert "commandsRun" in data
        assert "interactiveChecks" in data


# ============================================================
# TestCase, TestFile, Tests
# ============================================================


class TestTestSchemas:
    """Tests for TestCase, TestFile, Tests schemas."""

    def test_test_case(self) -> None:
        tc = TestCase(name="test_foo", verifies="foo behavior")
        assert tc.name == "test_foo"
        assert tc.verifies == "foo behavior"

    def test_test_file(self) -> None:
        tf = TestFile(
            file="tests/test_foo.py",
            cases=[TestCase(name="test_foo", verifies="foo behavior")],
        )
        assert tf.file == "tests/test_foo.py"
        assert len(tf.cases) == 1

    def test_tests_minimal(self) -> None:
        tests = Tests(
            added=[
                TestFile(
                    file="tests/test.py",
                    cases=[TestCase(name="t", verifies="v")],
                )
            ],
            coverage="80% coverage",
        )
        assert len(tests.added) == 1
        assert tests.coverage == "80% coverage"
        assert tests.updated is None

    def test_tests_with_updated(self) -> None:
        tests = Tests(
            added=[],
            updated=["tests/old.py"],
            coverage="60%",
        )
        assert tests.updated == ["tests/old.py"]


# ============================================================
# SkillDeviation and SkillFeedback
# ============================================================


class TestSkillFeedback:
    """Tests for SkillDeviation and SkillFeedback schemas."""

    def test_skill_deviation(self) -> None:
        dev = SkillDeviation(
            step="1.3 Baseline Validation",
            what_i_did_instead="Skipped it",
            why="Tests were already passing",
        )
        assert dev.step == "1.3 Baseline Validation"

    def test_skill_deviation_camel_case(self) -> None:
        dev = SkillDeviation(step="s", what_i_did_instead="x", why="y")
        data = dev.model_dump(by_alias=True)
        assert "whatIDidInstead" in data

    def test_skill_feedback(self) -> None:
        fb = SkillFeedback(
            followed_procedure=True,
            deviations=[],
        )
        assert fb.followed_procedure is True
        assert fb.deviations == []
        assert fb.suggested_changes is None

    def test_skill_feedback_with_changes(self) -> None:
        fb = SkillFeedback(
            followed_procedure=False,
            deviations=[SkillDeviation(step="s", what_i_did_instead="x", why="y")],
            suggested_changes=["Add more docs"],
        )
        assert len(fb.deviations) == 1
        assert fb.suggested_changes == ["Add more docs"]

    def test_skill_feedback_camel_case(self) -> None:
        fb = SkillFeedback(
            followed_procedure=True,
            deviations=[],
            suggested_changes=["s"],
        )
        data = fb.model_dump(by_alias=True)
        assert "followedProcedure" in data
        assert "suggestedChanges" in data


# ============================================================
# Handoff
# ============================================================


class TestHandoff:
    """Tests for Handoff schema."""

    def test_construction_minimal(self) -> None:
        """Construct with required fields only."""
        handoff = Handoff(
            what_was_implemented="Implemented feature X",
            what_was_left_undone="",
            verification=Verification(
                commands_run=[
                    VerificationCommand(command="test", exit_code=0, observation="ok")
                ]
            ),
            tests=Tests(
                added=[
                    TestFile(
                        file="test.py",
                        cases=[TestCase(name="t", verifies="v")],
                    )
                ],
                coverage="100%",
            ),
            discovered_issues=[],
        )
        assert handoff.salient_summary is None
        assert handoff.skill_feedback is None

    def test_construction_all_fields(self) -> None:
        """Construct with all fields."""
        handoff = Handoff(
            salient_summary="Did the thing",
            what_was_implemented="feature X",
            what_was_left_undone="nothing",
            verification=Verification(
                commands_run=[
                    VerificationCommand(command="c", exit_code=0, observation="o")
                ],
                interactive_checks=[InteractiveCheck(action="a", observed="b")],
            ),
            tests=Tests(
                added=[],
                updated=["old.py"],
                coverage="80%",
            ),
            discovered_issues=[
                DiscoveredIssue(
                    severity=IssueSeverity.NonBlocking,
                    description="minor",
                )
            ],
            skill_feedback=SkillFeedback(
                followed_procedure=True,
                deviations=[],
            ),
        )
        assert handoff.salient_summary == "Did the thing"
        assert handoff.skill_feedback is not None

    def test_camel_case_serialization(self) -> None:
        """Serialization produces camelCase keys."""
        handoff = Handoff(
            salient_summary="s",
            what_was_implemented="i",
            what_was_left_undone="",
            verification=Verification(commands_run=[]),
            tests=Tests(added=[], coverage="c"),
            discovered_issues=[],
            skill_feedback=SkillFeedback(followed_procedure=True, deviations=[]),
        )
        data = handoff.model_dump(by_alias=True)
        assert "salientSummary" in data
        assert "whatWasImplemented" in data
        assert "whatWasLeftUndone" in data
        assert "discoveredIssues" in data
        assert "skillFeedback" in data

    def test_json_roundtrip(self) -> None:
        """model_validate_json(model_dump_json()) produces equal model."""
        handoff = Handoff(
            what_was_implemented="impl",
            what_was_left_undone="",
            verification=Verification(
                commands_run=[
                    VerificationCommand(command="c", exit_code=0, observation="o")
                ]
            ),
            tests=Tests(added=[], coverage="c"),
            discovered_issues=[
                DiscoveredIssue(severity=IssueSeverity.Blocking, description="d")
            ],
        )
        roundtripped = Handoff.model_validate_json(
            handoff.model_dump_json(by_alias=True)
        )
        assert roundtripped == handoff


# ============================================================
# DismissalRecord
# ============================================================


class TestDismissalRecord:
    """Tests for DismissalRecord schema."""

    def test_construction(self) -> None:
        record = DismissalRecord(
            type=DismissalType.DiscoveredIssue,
            source_feature_id="feat-1",
            summary="issue dismissed",
            justification="not relevant",
        )
        assert record.type == DismissalType.DiscoveredIssue
        assert record.source_feature_id == "feat-1"

    def test_camel_case(self) -> None:
        record = DismissalRecord(
            type=DismissalType.CriticalContext,
            source_feature_id="f",
            summary="s",
            justification="j",
        )
        data = record.model_dump(by_alias=True)
        assert "sourceFeatureId" in data


# ============================================================
# ProgressLogEntry - Discriminated Union over 11 types
# ============================================================


class TestProgressLogEntryTypes:
    """Tests for each individual ProgressLogEntry type."""

    def test_mission_accepted_entry(self) -> None:
        entry = MissionAcceptedEntry(
            timestamp="2024-01-01T00:00:00Z",
            type=ProgressLogEntryType.MissionAccepted,
            title="My Mission",
        )
        assert entry.type == ProgressLogEntryType.MissionAccepted
        assert entry.title == "My Mission"

    def test_mission_paused_entry(self) -> None:
        entry = MissionPausedEntry(
            timestamp="2024-01-01T00:00:00Z",
            type=ProgressLogEntryType.MissionPaused,
        )
        assert entry.type == ProgressLogEntryType.MissionPaused

    def test_mission_resumed_entry(self) -> None:
        entry = MissionResumedEntry(
            timestamp="2024-01-01T00:00:00Z",
            type=ProgressLogEntryType.MissionResumed,
        )
        assert entry.type == ProgressLogEntryType.MissionResumed

    def test_mission_run_started_entry(self) -> None:
        entry = MissionRunStartedEntry(
            timestamp="2024-01-01T00:00:00Z",
            type=ProgressLogEntryType.MissionRunStarted,
            message="Starting run",
        )
        assert entry.message == "Starting run"

    def test_mission_run_started_optional_message(self) -> None:
        entry = MissionRunStartedEntry(
            timestamp="2024-01-01T00:00:00Z",
            type=ProgressLogEntryType.MissionRunStarted,
        )
        assert entry.message is None

    def test_worker_started_entry(self) -> None:
        entry = WorkerStartedEntry(
            timestamp="2024-01-01T00:00:00Z",
            type=ProgressLogEntryType.WorkerStarted,
            worker_session_id="ws-1",
            spawn_id="sp-1",
            feature_id="f-1",
        )
        assert entry.worker_session_id == "ws-1"
        assert entry.spawn_id == "sp-1"
        assert entry.feature_id == "f-1"

    def test_worker_started_optional_feature_id(self) -> None:
        entry = WorkerStartedEntry(
            timestamp="2024-01-01T00:00:00Z",
            type=ProgressLogEntryType.WorkerStarted,
            worker_session_id="ws-1",
            spawn_id="sp-1",
        )
        assert entry.feature_id is None

    def test_worker_selected_feature_entry(self) -> None:
        entry = WorkerSelectedFeatureEntry(
            timestamp="2024-01-01T00:00:00Z",
            type=ProgressLogEntryType.WorkerSelectedFeature,
            worker_session_id="ws-1",
            feature_id="f-1",
        )
        assert entry.worker_session_id == "ws-1"
        assert entry.feature_id == "f-1"

    def test_worker_completed_entry_minimal(self) -> None:
        entry = WorkerCompletedEntry(
            timestamp="2024-01-01T00:00:00Z",
            type=ProgressLogEntryType.WorkerCompleted,
            worker_session_id="ws-1",
            feature_id="f-1",
            success_state=FeatureSuccessState.Success,
            return_to_orchestrator=False,
            exit_code=0,
        )
        assert entry.commit_id is None
        assert entry.validators_passed is None
        assert entry.handoff is None

    def test_worker_completed_entry_all_fields(self) -> None:
        handoff = Handoff(
            what_was_implemented="impl",
            what_was_left_undone="",
            verification=Verification(commands_run=[]),
            tests=Tests(added=[], coverage="c"),
            discovered_issues=[],
        )
        entry = WorkerCompletedEntry(
            timestamp="2024-01-01T00:00:00Z",
            type=ProgressLogEntryType.WorkerCompleted,
            worker_session_id="ws-1",
            feature_id="f-1",
            success_state=FeatureSuccessState.Success,
            return_to_orchestrator=False,
            commit_id="abc123",
            exit_code=0,
            validators_passed=True,
            handoff=handoff,
        )
        assert entry.commit_id == "abc123"
        assert entry.validators_passed is True
        assert entry.handoff is not None

    def test_worker_failed_entry(self) -> None:
        entry = WorkerFailedEntry(
            timestamp="2024-01-01T00:00:00Z",
            type=ProgressLogEntryType.WorkerFailed,
            spawn_id="sp-1",
            reason="OOM",
        )
        assert entry.worker_session_id is None
        assert entry.exit_code is None
        assert entry.reason == "OOM"

    def test_worker_paused_entry(self) -> None:
        entry = WorkerPausedEntry(
            timestamp="2024-01-01T00:00:00Z",
            type=ProgressLogEntryType.WorkerPaused,
            worker_session_id="ws-1",
        )
        assert entry.feature_id is None

    def test_handoff_items_dismissed_entry(self) -> None:
        entry = HandoffItemsDismissedEntry(
            timestamp="2024-01-01T00:00:00Z",
            type=ProgressLogEntryType.HandoffItemsDismissed,
            dismissals=[
                DismissalRecord(
                    type=DismissalType.DiscoveredIssue,
                    source_feature_id="f",
                    summary="s",
                    justification="j",
                )
            ],
        )
        assert entry.dismissals is not None
        assert len(entry.dismissals) == 1

    def test_milestone_validation_triggered_entry(self) -> None:
        entry = MilestoneValidationTriggeredEntry(
            timestamp="2024-01-01T00:00:00Z",
            type=ProgressLogEntryType.MilestoneValidationTriggered,
            milestone="foundation",
            feature_id="f-1",
        )
        assert entry.milestone == "foundation"


# ============================================================
# ProgressLogEntry discriminated union
# ============================================================


PROGRESS_LOG_ENTRY_PAYLOADS: list[tuple[str, dict[str, Any]]] = [
    (
        "mission_accepted",
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "mission_accepted",
            "title": "My Mission",
        },
    ),
    (
        "mission_paused",
        {"timestamp": "2024-01-01T00:00:00Z", "type": "mission_paused"},
    ),
    (
        "mission_resumed",
        {"timestamp": "2024-01-01T00:00:00Z", "type": "mission_resumed"},
    ),
    (
        "mission_run_started",
        {"timestamp": "2024-01-01T00:00:00Z", "type": "mission_run_started"},
    ),
    (
        "worker_started",
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "worker_started",
            "workerSessionId": "ws-1",
            "spawnId": "sp-1",
        },
    ),
    (
        "worker_selected_feature",
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "worker_selected_feature",
            "workerSessionId": "ws-1",
            "featureId": "f-1",
        },
    ),
    (
        "worker_completed",
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "worker_completed",
            "workerSessionId": "ws-1",
            "featureId": "f-1",
            "successState": "success",
            "returnToOrchestrator": False,
            "exitCode": 0,
        },
    ),
    (
        "worker_failed",
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "worker_failed",
            "spawnId": "sp-1",
            "reason": "crash",
        },
    ),
    (
        "worker_paused",
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "worker_paused",
            "workerSessionId": "ws-1",
        },
    ),
    (
        "handoff_items_dismissed",
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "handoff_items_dismissed",
        },
    ),
    (
        "milestone_validation_triggered",
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "milestone_validation_triggered",
            "milestone": "foundation",
            "featureId": "f-1",
        },
    ),
]


class TestProgressLogEntryUnion:
    """Tests for the ProgressLogEntry discriminated union."""

    @pytest.mark.parametrize(
        ("entry_type", "payload"),
        PROGRESS_LOG_ENTRY_PAYLOADS,
        ids=[p[0] for p in PROGRESS_LOG_ENTRY_PAYLOADS],
    )
    def test_dispatches_all_11_types(
        self, entry_type: str, payload: dict[str, Any]
    ) -> None:
        """ProgressLogEntry dispatches on type field for all 11 types."""
        parsed = ProgressLogEntry(payload)
        assert parsed.root.type.value == entry_type

    def test_rejects_unknown_type(self) -> None:
        """Unknown type raises ValidationError."""
        with pytest.raises(ValidationError):
            ProgressLogEntry(
                {
                    "timestamp": "2024-01-01T00:00:00Z",
                    "type": "unknown_type",
                }
            )

    def test_worker_completed_with_full_handoff(self) -> None:
        """WorkerCompleted with deeply nested handoff structure parses."""
        payload = {
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "worker_completed",
            "workerSessionId": "ws-1",
            "featureId": "f-1",
            "successState": "success",
            "returnToOrchestrator": False,
            "commitId": "abc123",
            "exitCode": 0,
            "validatorsPassed": True,
            "handoff": {
                "salientSummary": "Did good work",
                "whatWasImplemented": "Everything",
                "whatWasLeftUndone": "",
                "verification": {
                    "commandsRun": [
                        {
                            "command": "pytest",
                            "exitCode": 0,
                            "observation": "all passed",
                        }
                    ],
                    "interactiveChecks": [
                        {"action": "clicked", "observed": "rendered"}
                    ],
                },
                "tests": {
                    "added": [
                        {
                            "file": "test.py",
                            "cases": [{"name": "test_x", "verifies": "x works"}],
                        }
                    ],
                    "updated": ["old.py"],
                    "coverage": "95%",
                },
                "discoveredIssues": [
                    {
                        "severity": "non_blocking",
                        "description": "minor issue",
                        "suggestedFix": "fix it",
                    }
                ],
                "skillFeedback": {
                    "followedProcedure": True,
                    "deviations": [],
                    "suggestedChanges": ["better docs"],
                },
            },
        }
        parsed = ProgressLogEntry(payload)
        assert isinstance(parsed.root, WorkerCompletedEntry)
        assert parsed.root.handoff is not None
        assert parsed.root.handoff.salient_summary == "Did good work"
        assert len(parsed.root.handoff.verification.commands_run) == 1
        assert len(parsed.root.handoff.tests.added) == 1
        assert len(parsed.root.handoff.discovered_issues) == 1
        assert parsed.root.handoff.skill_feedback is not None

    def test_roundtrip_via_json(self) -> None:
        """All entry types roundtrip through JSON."""
        for _name, payload in PROGRESS_LOG_ENTRY_PAYLOADS:
            parsed = ProgressLogEntry(payload)
            json_str = parsed.model_dump_json(by_alias=True)
            reparsed = ProgressLogEntry.model_validate_json(json_str)
            assert reparsed == parsed


# ============================================================
# Cross-model behavior tests
# ============================================================


class TestMissionCrossModelBehavior:
    """Cross-model behavior tests for mission schemas."""

    def test_all_models_use_config_dict(self) -> None:
        """All mission models use ConfigDict with correct settings.

        Mission models are server response data, so they use extra='allow'
        to tolerate new fields during protocol evolution.
        """
        from droid_sdk.schemas import mission

        model_classes = [
            mission.MissionFeature,
            mission.DiscoveredIssue,
            mission.VerificationCommand,
            mission.InteractiveCheck,
            mission.Verification,
            mission.TestCase,
            mission.TestFile,
            mission.Tests,
            mission.SkillDeviation,
            mission.SkillFeedback,
            mission.Handoff,
            mission.DismissalRecord,
        ]
        for cls in model_classes:
            config = cls.model_config
            assert config.get("populate_by_name") is True, (
                f"{cls.__name__} missing populate_by_name=True"
            )
            assert config.get("extra") == "allow", (
                f"{cls.__name__} should use extra='allow' for protocol evolution"
            )

    def test_enum_fields_serialize_as_raw_strings(self) -> None:
        """Enum fields in mission models serialize as raw strings."""
        feature = MissionFeature(
            id="f",
            description="d",
            status=FeatureStatus.InProgress,
            skill_name="sk",
            preconditions=[],
            expected_behavior=[],
            verification_steps=[],
        )
        data = json.loads(feature.model_dump_json(by_alias=True))
        assert data["status"] == "in_progress"

    def test_deeply_nested_deserialization(self) -> None:
        """Deeply nested mission data deserializes correctly."""
        raw = {
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "worker_completed",
            "workerSessionId": "ws-1",
            "featureId": "f-1",
            "successState": "partial",
            "returnToOrchestrator": True,
            "exitCode": 1,
            "handoff": {
                "whatWasImplemented": "partial impl",
                "whatWasLeftUndone": "rest of it",
                "verification": {
                    "commandsRun": [
                        {
                            "command": "pytest",
                            "exitCode": 1,
                            "observation": "2 failures",
                        }
                    ],
                },
                "tests": {
                    "added": [],
                    "coverage": "40%",
                },
                "discoveredIssues": [
                    {"severity": "blocking", "description": "broken dep"}
                ],
            },
        }
        entry = WorkerCompletedEntry.model_validate(raw)
        assert entry.handoff is not None
        assert entry.handoff.discovered_issues[0].severity == IssueSeverity.Blocking
