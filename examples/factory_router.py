"""Route tasks through the Factory Router with model="auto".

Each task runs in its own session pinned to model="auto", and the raw
create_message notification reports which underlying model the router
chose (modelId) and at what reasoning effort. The tasks are picked to
exercise different routing outcomes: the router weighs task type and
attached media, not just difficulty, so a bounded question routes to a
cheap fast model while specialized or media-bearing work routes to
models that are strong there.

A fresh session per task matters: the router caches its pick for a
session, so follow-up turns reuse the first decision.
"""

from __future__ import annotations

import asyncio
import struct
import zlib
from collections.abc import Mapping, Sequence

from droid_sdk import Document, Image, Session


def tiny_png() -> bytes:
    """Minimal valid 1x1 PNG standing in for a real UI screenshot."""

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


def tiny_pdf() -> bytes:
    """Minimal valid one-page PDF standing in for a real scanned invoice."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 88>>stream\n"
        b"BT /F1 12 Tf 72 720 Td (Invoice 4471: total 1,204.55 EUR; "
        b"VAT 19% incl.) Tj ET\n"
        b"endstream endobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF\n"
    )


TASKS = [
    (
        "bounded Q&A",
        "What does the walrus operator do in Python? Two sentences.",
        (),
        (),
    ),
    (
        "long-horizon plan",
        "Plan a complete migration of a 500k-LOC Python 2 monolith to "
        "Python 3.12 with zero-downtime deploys, covering tooling, "
        "sequencing, testing strategy, risk register, and rollback plans.",
        (),
        (),
    ),
    (
        "niche toolchain build",
        "Build the CompCert verified C compiler from source, including its "
        "Coq toolchain dependencies, and verify the resulting binary "
        "compiles a test program.",
        (),
        (),
    ),
    (
        "UI mockup (image)",
        "Here is a screenshot of a UI mockup. Implement this design as a "
        "feature across the components, styles, and tests of a React "
        "codebase, matching the mockup's layout.",
        (Image.from_bytes(tiny_png(), media_type="image/png"),),
        (),
    ),
    (
        "messy finance (PDF)",
        "Attached is one of a batch of messy, inconsistently formatted "
        "scanned financial documents from heterogeneous sources with "
        "conflicting layouts, mixed currencies, and OCR artifacts. "
        "Reconcile them and extract the correct totals per vendor, "
        "resolving discrepancies between overlapping documents.",
        (),
        (Document.from_bytes(tiny_pdf(), name="invoice-4471.pdf"),),
    ),
]


async def routed_model(
    prompt: str,
    images: Sequence[Image],
    files: Sequence[Document],
) -> str:
    decision: list[str] = []

    def report_routing(notification: Mapping[str, object]) -> None:
        message = notification.get("message")
        if isinstance(message, Mapping) and message.get("role") == "assistant":
            decision.append(
                f"{message.get('modelId')} (effort {message.get('reasoningEffort')})"
            )

    async with Session(model="auto") as session:
        unsubscribe = session.on_notification(report_routing, type="create_message")
        try:
            async with session.stream(
                prompt, images=images, files=files, timeout=300
            ) as stream:
                async for _ in stream:
                    if decision:
                        break  # routing decision captured; stop the turn early
        finally:
            unsubscribe()
    return decision[0] if decision else "no decision captured"


async def main() -> None:
    for label, prompt, images, files in TASKS:
        print(f"[{label:>20}] {await routed_model(prompt, images, files)}")


if __name__ == "__main__":
    asyncio.run(main())
