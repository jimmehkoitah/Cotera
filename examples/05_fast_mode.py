"""Fast mode on Opus 5 (research preview).

Runs the same model at up to 2.5x higher output tokens per second, priced at
$10/$50 per MTok. Claude API only — not available on Bedrock, Vertex, or
Foundry, and not with the Batches API or Priority Tier. Fast mode draws on
its own rate limits, separate from the standard Opus 5 pool.

Three things are required: the beta messages endpoint, the beta flag
fast-mode-2026-02-01, and speed="fast" as a top-level request parameter.
"""

import anthropic

client = anthropic.Anthropic()

response = client.beta.messages.create(
    model="claude-opus-5",
    max_tokens=4096,
    speed="fast",
    betas=["fast-mode-2026-02-01"],
    messages=[
        {"role": "user", "content": "Write a limerick about fast inference."}
    ],
)

print(f"Speed used: {response.usage.speed}")
for block in response.content:
    if block.type == "text":
        print(block.text)

# On a 429, either retry after the `retry-after` delay or drop `speed` and
# fall back to standard (note: switching speed invalidates the prompt cache).
