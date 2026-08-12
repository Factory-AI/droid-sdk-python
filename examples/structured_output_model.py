"""Pydantic structured output from one bounded turn."""

from __future__ import annotations

import argparse
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


async def main(run_turn: bool = False) -> None:
    if not run_turn:
        assert Review.model_json_schema()["type"] == "object"
        print("self-test: output schema ready")
        return
    result = await run(
        "Return a short repository summary and zero or more findings.",
        output=Review,
        timeout=60,
    )
    assert result.output is not None, result.output_validation_error
    print(result.output.summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    asyncio.run(main(parser.parse_args().run))
