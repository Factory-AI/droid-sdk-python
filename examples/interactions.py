"""Permission and question handlers with safe cancellation defaults."""

from __future__ import annotations

import asyncio

from droid_sdk import (
    InteractionHandlers,
    PermissionRequest,
    PermissionResponse,
    QuestionRequest,
    QuestionResponse,
    Session,
    ToolConfirmationOutcome,
)


def permission(request: PermissionRequest) -> PermissionResponse:
    return request.respond(ToolConfirmationOutcome.CANCEL)


async def question(request: QuestionRequest) -> QuestionResponse:
    answers = [
        item.answer(item.options[0] if item.options else "none")
        for item in request.questions
    ]
    return request.submit(answers)


async def main() -> None:
    handlers = InteractionHandlers(
        on_permission=permission,
        on_question=question,
    )
    async with Session(interactions=handlers) as session:
        async with session.stream(
            "Ask one multiple-choice question, then stop.",
            timeout=60,
        ) as stream:
            async for _ in stream:
                pass
        print(stream.result.subtype)


if __name__ == "__main__":
    asyncio.run(main())
