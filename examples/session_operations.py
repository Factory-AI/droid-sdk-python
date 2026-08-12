"""Settings, context, tools, skills, spec, and replacement ownership."""

from __future__ import annotations

import argparse
import asyncio
import contextlib

from droid_sdk import Autonomy, Mode, Session, SessionReplacedError


async def main(run_operations: bool = False) -> None:
    if not run_operations:
        assert Mode.AUTO.value == "auto"
        assert Autonomy.LOW.value == "low"
        print("self-test: operation types ready")
        return

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    asyncio.run(main(parser.parse_args().run))
