"""Pydantic structured output from one bounded turn."""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import BaseModel

from droid_sdk import RunSuccess, SessionConfig, run


class Finding(BaseModel):
    severity: Literal["low", "medium", "high"]
    message: str


class Review(BaseModel):
    summary: str
    findings: list[Finding]


async def main() -> None:
    result = await run(
        (
            'Return summary exactly "Structured output works." and one finding '
            'with severity "low" and message exactly "Example complete."'
        ),
        output=Review,
        timeout=60,
        config=SessionConfig(
            disable_builtin_skills=True,
            restrict_tools=(),
        ),
    )
    assert isinstance(result, RunSuccess), (
        result.error.message if result.error else result.subtype
    )
    assert result.output == Review(
        summary="Structured output works.",
        findings=[
            Finding(
                severity="low",
                message="Example complete.",
            )
        ],
    )
    print(result.output.summary)


if __name__ == "__main__":
    asyncio.run(main())
