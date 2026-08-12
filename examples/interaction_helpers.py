"""Exercise interaction response helpers without starting Droid."""

from droid_sdk import (
    PermissionOption,
    PermissionRequest,
    Question,
    QuestionRequest,
    ToolConfirmationOutcome,
)


def main() -> None:
    permission = PermissionRequest(
        actions=(),
        options=(
            PermissionOption(
                label="Proceed once",
                value=ToolConfirmationOutcome.PROCEED_ONCE,
            ),
            PermissionOption(
                label="Cancel",
                value=ToolConfirmationOutcome.CANCEL,
            ),
        ),
    )
    response = permission.respond(
        ToolConfirmationOutcome.PROCEED_ONCE,
        comment="Approved by the offline example.",
    )

    single = Question(
        index=1,
        topic="Language",
        question="Which language?",
        options=("Python", "TypeScript"),
    )
    multiple = Question(
        index=2,
        topic="Checks",
        question="Which checks?",
        options=("tests", "lint", "types"),
        multi_select=True,
    )
    questionnaire = QuestionRequest(
        tool_call_id="offline-tool-call",
        questions=(single, multiple),
    )
    answers = questionnaire.submit(
        (
            single.answer("Python"),
            multiple.answer_multiple(("tests", "types")),
        )
    )
    cancelled = questionnaire.cancel()

    print(response)
    print(answers)
    print(cancelled)


if __name__ == "__main__":
    main()
