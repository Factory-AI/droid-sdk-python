#!/usr/bin/env python3
"""Send one image, PDF, or text file.

Usage:
    uv run python examples/attachment.py PATH
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from pathlib import Path

from _helpers import DocumentInput, ImageInput, run_turn

from droid_sdk import DroidClient

_IMAGE_TYPES = {
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    return parser.parse_args()


def encode(path: Path) -> tuple[list[ImageInput], list[DocumentInput]]:
    suffix = path.suffix.lower()
    if suffix in _IMAGE_TYPES:
        image = {
            "type": "base64",
            "data": base64.b64encode(path.read_bytes()).decode("ascii"),
            "mediaType": _IMAGE_TYPES[suffix],
        }
        return [image], []

    if suffix == ".pdf":
        document = {
            "type": "base64",
            "mediaType": "application/pdf",
            "data": base64.b64encode(path.read_bytes()).decode("ascii"),
            "name": path.name,
        }
        return [], [document]

    document = {
        "type": "text",
        "mediaType": "text/plain",
        "data": path.read_text(),
        "name": path.name,
    }
    return [], [document]


async def main(path: Path) -> None:
    images, files = encode(path)
    cwd = str(Path.cwd())

    async with DroidClient(exec_path="droid", cwd=cwd) as client:
        await client.initialize_session(
            machine_id="python-sdk-example",
            cwd=cwd,
        )
        await run_turn(
            client,
            "Describe the attached file.",
            images=images,
            files=files,
        )


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.path))
