"""Settings, context, tools, skills, spec, and replacement ownership."""

from __future__ import annotations

import asyncio
import contextlib

from droid_sdk import Autonomy, Session, SessionReplacedError


async def main() -> None:
    session = Session()
    await session.open()
    try:
        await session.update_settings(autonomy=Autonomy.LOW)
        print(await session.context())
        print([tool.id for tool in await session.list_tools()])
        print([skill.name for skill in (await session.list_skills()).skills])
        await session.enter_spec()
        await session.leave_spec()

        successor = await session.fork(title="SDK example fork")
        with contextlib.suppress(SessionReplacedError):
            await session.context()
        async with successor:
            async with successor.stream(
                "Reply with exactly: ready to compact",
                timeout=60,
            ) as stream:
                async for _ in stream:
                    pass
            print(stream.result.text)
            compacted = await successor.compact(instructions="Keep decisions.")
            async with compacted.session:
                print(compacted.removed_count)
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
