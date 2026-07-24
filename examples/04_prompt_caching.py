"""Prompt caching with Opus 5's 512-token minimum.

The minimum cacheable prefix drops to 512 tokens on Opus 5 — down from 1024
on Opus 4.8 and 4096 on Opus 4.6. Prompts previously too short to cache now
create cache entries with no code change.

Cache reads cost ~0.1x base input price; writes cost 1.25x (5-minute TTL).
Verify hits via usage.cache_read_input_tokens — zero across repeated
identical-prefix requests means a silent invalidator (timestamp, UUID,
unsorted JSON) is changing the prefix bytes.
"""

import anthropic

client = anthropic.Anthropic()

# A system prompt in the 512-1024 token range: cacheable on Opus 5,
# silently NOT cacheable on Opus 4.8 and earlier.
SYSTEM_PROMPT = (
    "You are a support agent for Acme Analytics. "
    + "Answer questions about dashboards, alerts, and data connectors. "
    + "Escalate billing questions to a human. " * 40
)

def ask(question: str) -> anthropic.types.Message:
    return client.messages.create(
        model="claude-opus-5",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": question}],
    )

first = ask("How do I add a Postgres connector?")
print(f"1st request — cache written:  {first.usage.cache_creation_input_tokens} tokens")

second = ask("Can I schedule a dashboard email?")
print(f"2nd request — cache read:     {second.usage.cache_read_input_tokens} tokens")
print(f"2nd request — uncached input: {second.usage.input_tokens} tokens")
