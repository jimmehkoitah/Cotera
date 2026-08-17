# Cotera focused-agent fan-out

Runs **one** focused agent across **many** hiring rows in parallel, so the export
lands where it belongs without placing each one in by hand.

```
sheet row ──┐
sheet row ──┼──► focused agent 92e07017-… ──► agent writes into the Google Doc
sheet row ──┘        (N runs in parallel)
```

## What this orchestrator does and does not do

| Does | Does not |
|---|---|
| Build `raw_hiring_row` from the sheet columns | Generate, rewrite, or personalize any copy |
| Send one agent run per row, N in flight | Reformat or summarize the agent's output |
| Dedupe and resume across re-runs | Read or write the Google Doc |
| Record every attempt in a ledger | Decide where in the doc content goes |

The agent owns the doc insertion. The orchestrator is a dispatcher, and keeping it
that way is what makes every message consistent.

## Payload

Each run posts exactly these fields:

```json
{
  "agent_id": "92e07017-49a4-54f4-9913-f887bc2284f8",
  "google_doc_id": "1jmuUvzNz55xQTAo29Vwh5eEifgCCqew416zRM2UGReM",
  "raw_hiring_row": "<the full messy row>",
  "output_destination": "google_doc",
  "write_mode": "insert_in_existing_structure",
  "dedupe_key": "<company>|<job_url>|<primary_email_or_linkedin>",
  "preserve_agent_output_exactly": true
}
```

`raw_hiring_row` is the row serialized as `Column: value` lines, with empty
columns dropped and nothing else touched — the messiness is deliberate, the agent
decides what matters. Use `--columns` to send a subset.

## Setup

```bash
export COTERA_API_KEY=...            # required for real runs
export COTERA_API_BASE=https://api.cotera.co
export COTERA_RUN_PATH=/v1/agents/{agent_id}/runs
```

`FOCUSED_AGENT_ID` and `GOOGLE_DOC_ID` default to the values above; override via
env or `--agent-id` / `--google-doc-id`.

## Pointing at the real endpoint

`COTERA_RUN_PATH` is configurable because the agent-run route was **not verified**
when this was written — `cotera.co` and `api.cotera.co` are blocked by the network
egress policy of the environment it was built in, so the docs could not be read.
Confirm the route and auth header against your Cotera workspace before the first
real run. If Cotera authenticates with something other than
`Authorization: Bearer`, adjust the headers in `run_agent()`.

Everything else — batching, dedupe, resume, retries — is independent of that route.

## Running it

Export the hiring sheet as CSV (File → Download → CSV), then:

```bash
# 1. Preview the payloads without calling anything
python orchestrator/cotera_fanout.py --input rows.csv --dry-run

# 2. Prove the wiring on a single row
python orchestrator/cotera_fanout.py --input rows.csv --limit 1

# 3. Run the batch
python orchestrator/cotera_fanout.py --input rows.csv --concurrency 5
```

Start at `--concurrency 5` and raise it once you know Cotera's rate limits.

### Column mapping

Defaults assume `Company`, `Job URL`, `Email`, `LinkedIn URL`. Point them at your
actual headers — each flag takes several names and uses the first non-empty one:

```bash
python orchestrator/cotera_fanout.py --input rows.csv \
  --company-col "Company" \
  --job-url-col "Job URL" "Posting Link" \
  --email-col "Primary Email" "Email" \
  --linkedin-col "LinkedIn URL"
```

If the sheet has banner rows above the headers, pass `--header-row N`.

## Dedupe and resume

Every attempt appends to `orchestrator/runs.jsonl` keyed by `dedupe_key`. On a
re-run, rows already logged `ok` are skipped, so a batch that half-failed can be
re-run as-is without double-posting into the doc. Duplicate keys within one input
file are collapsed to a single run.

Override with `--rerun-succeeded`, or point `--ledger` at a different file to keep
separate batches apart. Retries are automatic on 408/429/5xx and network errors —
five attempts with exponential backoff.

Failures never stop the batch; each one is logged and the summary reports the
count. Re-run the same command to retry only what failed.
