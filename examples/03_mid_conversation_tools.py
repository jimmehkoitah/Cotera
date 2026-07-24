"""Mid-conversation tool changes (new on Opus 5).

Before Opus 5, the `tools` array was fixed for a conversation's lifetime —
any edit changed the very front of the prompt prefix and invalidated the
entire prompt cache. Now you can:

1. Declare tools up front with `defer_loading: True` (known to the request,
   but not loaded into the model's context yet), and
2. surface or revoke them between turns via `tool_addition` / `tool_removal`
   blocks on a {"role": "system"} message — the cached prefix survives.

Beta header: mid-conversation-tool-changes-2026-07-01. SDK typings lag these
blocks, so they're passed as plain dicts (the SDK forwards unknown keys).
"""

import anthropic

client = anthropic.Anthropic()

tools = [
    {
        "name": "get_weather",
        "description": "Get current weather for a city.",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
    {
        "name": "get_forecast",
        "description": "Get the 5-day forecast for a city.",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
        # Declared but not loaded — the model can't see it until a
        # tool_addition block surfaces it.
        "defer_loading": True,
    },
]

messages = [
    {"role": "user", "content": "What weather tools do you have available?"},
    # Your application decides mid-conversation that the forecast tool should
    # now be available — e.g. the user upgraded a plan, or a mode toggled.
    {
        "role": "system",
        "content": [
            {
                "type": "tool_addition",
                "tool": {"type": "tool_reference", "name": "get_forecast"},
            },
        ],
    },
]

response = client.beta.messages.create(
    model="claude-opus-5",
    max_tokens=16000,
    betas=["mid-conversation-tool-changes-2026-07-01"],
    tools=tools,
    messages=messages,
)

for block in response.content:
    if block.type == "text":
        print(block.text)
    elif block.type == "tool_use":
        print(f"[tool_use] {block.name}({block.input})")
