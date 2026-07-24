"""Server-side refusal fallbacks with `fallbacks: "default"` (new on Opus 5).

Opus 5's safety classifiers can decline a request (stop_reason "refusal").
Without fallbacks, the request simply stops. The new "default" mode re-runs a
declined request server-side on Anthropic's recommended fallback model, routed
by refusal category (cyber-category refusals go to Opus 4.8) — no fallback
model list to maintain, and no re-migration when a pinned model is deprecated.

Beta header: server-side-fallback-2026-07-01 (the older array form
`fallbacks=[{"model": ...}]` uses -2026-06-01 instead — don't mix them).
Claude API only; not available on Bedrock, Vertex, or Foundry.
"""

import anthropic

client = anthropic.Anthropic()

response = client.beta.messages.create(
    model="claude-opus-5",
    max_tokens=16000,
    betas=["server-side-fallback-2026-07-01"],
    # If your installed SDK doesn't type the scalar form yet, pass it via
    # extra_body={"fallbacks": "default"} instead.
    fallbacks="default",
    messages=[{"role": "user", "content": "Summarize the OWASP Top 10."}],
)

# A refusal on the FINAL response means the whole chain refused.
if response.stop_reason == "refusal":
    print("Declined by the full fallback chain.")
else:
    # Switch points: one `fallback` block per model that ran and declined.
    for block in response.content:
        if block.type == "fallback":
            print(f"{block.from_.model} declined; {block.to.model} continued")

    # Served-by signal — covers sticky turns, which carry no fallback block.
    fallback_ran = any(
        entry.type == "fallback_message"
        for entry in response.usage.iterations or []
    )
    print(f"Served by: {response.model}"
          + (" (via fallback)" if fallback_ran else ""))

    text = next((b.text for b in response.content if b.type == "text"), "")
    print(text[:500])
