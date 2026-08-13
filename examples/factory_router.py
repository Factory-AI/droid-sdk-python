"""Route turns through the Factory Router with model="auto"."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from droid_sdk import Session, run


def report_routing(notification: Mapping[str, object]) -> None:
    message = notification.get("message")
    if isinstance(message, Mapping) and message.get("role") == "assistant":
        print(f"routed to {message.get('modelId')} (router {message.get('routerId')})")


async def main() -> None:
    result = await run("Reply with exactly: ROUTER READY", model="auto", timeout=180)
    print(result.text)

    async with Session(model="auto") as session:
        unsubscribe = session.on_notification(report_routing, type="create_message")
        try:
            async with session.stream(
                "Reply with exactly: ROUTED TURN DONE",
                timeout=180,
            ) as stream:
                async for _ in stream:
                    pass
        finally:
            unsubscribe()
        print(stream.result.text)
        print(f"session model setting: {session.settings.model}")


if __name__ == "__main__":
    asyncio.run(main())
