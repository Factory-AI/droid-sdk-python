"""List models available to the current Factory account and project."""

from __future__ import annotations

import asyncio
from pathlib import Path

from droid_sdk import list_models


async def main() -> None:
    models = await list_models(
        include_disabled=True,
        cwd=Path.cwd(),
    )
    for model in models:
        status = f"disabled: {model.disabled_reason}" if model.disabled else "available"
        efforts = ", ".join(
            effort.value for effort in model.supported_reasoning_efforts
        )
        print(f"{model.display_name} ({model.id})")
        print(f"  status: {status}")
        print(f"  reasoning: {efforts}")


if __name__ == "__main__":
    asyncio.run(main())
