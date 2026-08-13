"""Pydantic structured output from one bounded turn."""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import BaseModel

from droid_sdk import run


class Finding(BaseModel):
    severity: Literal["low", "medium", "high"]
    message: str


class Review(BaseModel):
    summary: str
    findings: list[Finding]


async def main() -> None:
    result = await run(
        "Return a short repository summary and zero or more findings.",
        output=Review,
        timeout=180,
    )
    assert result.output is not None, result.output_validation_error
    print(result.output.summary)


if __name__ == "__main__":
    asyncio.run(main())
