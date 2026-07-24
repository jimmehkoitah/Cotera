"""Opus 5 basics: thinking on by default, the effort ladder, refusal handling.

Two breaking changes vs Opus 4.8:
1. Omitting `thinking` now runs adaptive thinking (4.8 ran without thinking).
2. `thinking: {"type": "disabled"}` is only accepted at effort `high` or lower.
"""

import anthropic

client = anthropic.Anthropic()

# Thinking is on by default — no `thinking` param needed. Control depth with
# effort: low | medium | high (default) | xhigh | max. On Opus 5, low/medium
# often match what prior models needed xhigh for.
response = client.messages.create(
    model="claude-opus-5",
    max_tokens=16000,  # hard cap on thinking + response text together
    output_config={"effort": "medium"},
    messages=[{"role": "user", "content": "Explain CRDTs in three sentences."}],
)

# Opus 5's safety classifiers can decline a request: HTTP 200 with
# stop_reason "refusal". Always check before reading content.
if response.stop_reason == "refusal":
    details = response.stop_details
    print(f"Declined (category: {details.category if details else 'unknown'})")
else:
    for block in response.content:
        if block.type == "text":
            print(block.text)

print(f"\n[effort=medium, output tokens: {response.usage.output_tokens}]")
