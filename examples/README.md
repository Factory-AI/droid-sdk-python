# Examples

Run examples from the repository root:

```bash
uv sync
export FACTORY_API_KEY="..."
uv run python examples/query.py
```

| Example | Purpose |
| --- | --- |
| [`query.py`](query.py) | Run one prompt with Auto Router |
| [`multi_turn_session.py`](multi_turn_session.py) | Preserve context across turns |
| [`model_discovery.py`](model_discovery.py) | List available model IDs |
| [`model_selection.py`](model_selection.py) | Select Auto Router or a fixed model |
| [`resume_session.py`](resume_session.py) | Resume a saved session |
| [`structured_output.py`](structured_output.py) | Request JSON Schema output |
| [`permission_handler.py`](permission_handler.py) | Handle tool approval requests |
| [`attachment.py`](attachment.py) | Send an image, PDF, or text file |
| [`session_lifecycle.py`](session_lifecycle.py) | Fork and continue a session |
| [`interactive_session.py`](interactive_session.py) | Run an interactive terminal session |

Each example starts a local `droid exec` subprocess. It uses your current
directory unless its usage says otherwise.
