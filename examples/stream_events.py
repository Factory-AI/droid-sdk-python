"""Stream every kind of turn activity: text, thinking, tools, permissions, hooks."""

from __future__ import annotations

import asyncio

from droid_sdk import (
    Autonomy,
    HookExecution,
    InteractionHandlers,
    PermissionRequest,
    PermissionResolved,
    PermissionResponse,
    Session,
    SessionConfig,
    TextComplete,
    TextDelta,
    ThinkingComplete,
    ThinkingDelta,
    TokenUsageUpdate,
    ToolCall,
    ToolCallDelta,
    ToolConfirmationOutcome,
    ToolProgress,
    ToolResult,
    WorkingStateChanged,
)


def approve_once(request: PermissionRequest) -> PermissionResponse:
    actions = ", ".join(type(action).__name__ for action in request.actions)
    print(f"\n[permission requested] {actions}")
    return request.respond(ToolConfirmationOutcome.PROCEED_ONCE)


async def main() -> None:
    session = Session(
        config=SessionConfig(autonomy=Autonomy.LOW),  # every tool call asks first
        interactions=InteractionHandlers(on_permission=approve_once),
    )
    async with session:
        async with session.stream(
            "Run `touch /tmp/droid-stream-demo.txt`, then summarize what you did.",
            include_partial_messages=True,
            timeout=120,
        ) as stream:
            async for event in stream:
                match event:
                    case TextDelta(text=text) | ThinkingDelta(text=text):
                        print(text, end="", flush=True)
                    case TextComplete():
                        print()
                    case ThinkingComplete():
                        print("\n[thinking done]")
                    case ToolCallDelta(tool_use=tool_use):
                        print(f"[tool call delta] {tool_use.name}")
                    case ToolCall(name=name, input=arguments):
                        print(f"[tool call] {name} {dict(arguments)}")
                    case ToolProgress(tool_name=name, update=update):
                        print(f"[tool progress] {name}: {update.type}")
                    case ToolResult(tool_name=name, is_error=is_error):
                        print(f"[tool result] {name} error={is_error}")
                    case PermissionResolved(selected_option=option):
                        print(f"[permission resolved] {option.value}")
                    case HookExecution(hook_id=hook_id, status=status):
                        print(f"[hook] {hook_id}: {status}")
                    case WorkingStateChanged(state=state):
                        print(f"[state] {state.value}")
                    case TokenUsageUpdate(output_tokens=output_tokens):
                        print(f"[usage] {output_tokens} output tokens")
                    case _:
                        print(f"[{type(event).__name__}]")

        result = stream.result
        print(f"[done] {result.subtype} in {result.duration.total_seconds():.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
