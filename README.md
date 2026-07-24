# Claude Opus 5 Capabilities

What `claude-opus-5` can do that previous Claude models could not, with runnable
examples for each new API feature.

Opus 5 is a drop-in upgrade from Opus 4.8 at the same pricing ($5/$25 per MTok),
with 1M context, 128K max output, and its own rate-limit bucket (separate from
the shared Opus 4.x pool).

## New API features

| Feature | What changed | Example |
|---|---|---|
| Mid-conversation tool changes | Add/remove tools between turns **without invalidating the prompt cache** (previously `tools` was fixed for a conversation's lifetime) | [`examples/03_mid_conversation_tools.py`](examples/03_mid_conversation_tools.py) |
| Refusal fallbacks `"default"` | Safety-classifier declines are re-run server-side on Anthropic's recommended fallback model, routed by refusal category — no fallback model list to maintain | [`examples/02_refusal_fallbacks.py`](examples/02_refusal_fallbacks.py) |
| 512-token cache minimum | Minimum cacheable prompt prefix drops to 512 tokens (was 1024 on Opus 4.8, 4096 on Opus 4.6) — short prompts now cache | [`examples/04_prompt_caching.py`](examples/04_prompt_caching.py) |
| Fast mode | `speed: "fast"` at the Opus 5 tier — up to 2.5× output tokens/sec at $10/$50 per MTok (Claude API only, research preview) | [`examples/05_fast_mode.py`](examples/05_fast_mode.py) |

## Capability gains over Opus 4.8

- **Harder agentic coding** — the step change is on difficult work: multi-file
  features, large refactors, long autonomous runs that finish without stubs.
- **Built-in self-verification** — it checks its own work unprompted. Delete
  "double-check your answer" instructions; they now cause over-verification.
- **Code review with high precision *and* recall**, accurate even at low effort.
- **`low`/`medium` effort punch far above their weight** — often exceeding what
  prior models did at `xhigh`, making effort the primary cost/latency lever.
- **Multi-agent coordination** — reliably runs subagent teams (writer-verifier,
  parallel fan-out) without agents clobbering each other's work.
- **Vision** — stronger chart/document/diagram understanding and UI replication,
  especially when given crop/analyze/verify tools.
- **Complex Office deliverables** — multi-sheet Excel with real formulas,
  well-designed PowerPoint decks.

## Two breaking changes to know

1. **Thinking is on by default.** A request that omits `thinking` runs adaptive
   thinking (on Opus 4.8/4.7, omitting it meant *no* thinking). `max_tokens`
   caps thinking + response together, so tightly-sized budgets can truncate.
2. **Disabling thinking is capped at `high` effort.** `thinking: {type:
   "disabled"}` combined with `xhigh`/`max` effort returns a 400.

See [`examples/01_basics.py`](examples/01_basics.py) for both.

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # or `ant auth login`
python examples/01_basics.py
```
