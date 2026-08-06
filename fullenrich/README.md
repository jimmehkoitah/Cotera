# FullEnrich phone enrichment

Takes a TSV contact export, fetches phone numbers from FullEnrich's bulk
waterfall API, and writes the same TSV back with the phone columns filled in.
Row order and every original column are preserved, so the output can be pasted
straight back over the source sheet.

## Why you run this and not the agent

`app.fullenrich.com` is blocked by the egress policy on the Claude Code remote
environment, so the enrichment cannot be executed from a session there. The
script is the deliverable; you run it wherever the network is open.

## Setup

No dependencies -- standard-library Python 3.8+.

```bash
cd fullenrich
export FULLENRICH_API_KEY=<your key>
```

The key is read from the environment only. It is never written to a file, a
log line, or a commit.

## Run it

```bash
# 1. See what would be sent. Calls nothing, spends nothing.
python3 enrich_phones.py --dry-run

# 2. Two contacts against the live API, dumping raw JSON so you can confirm
#    the response schema before committing to the full batch.
python3 enrich_phones.py --probe --limit 2

# 3. The real run.
python3 enrich_phones.py
```

Output lands in `data/contacts_enriched.tsv`.

| Flag | Effect |
|---|---|
| `--input` / `--output` | file paths (default `data/contacts.tsv` → `data/contacts_enriched.tsv`) |
| `--dry-run` | build payloads, print them, call nothing |
| `--probe` | dump raw API JSON — use on the first run to verify the schema |
| `--limit N` | only enrich the first N eligible rows |
| `--overwrite` | replace phone values that are already present (default: skip those rows) |
| `--resume ID` | skip submitting, just re-poll an enrichment that timed out |

## What it writes

Only three columns are ever modified — `direct_phone`, `company_phone`, and
`phone_status`. Everything else is passed through byte-for-byte.

On a miss, the FullEnrich outcome is *appended* to `phone_status` rather than
replacing it, so an existing Apollo note survives and you can see that both
vendors were tried.

## How rows are matched

Each row is sent with an opaque `row_id` in FullEnrich's `custom` field and
matched back on that id. Results are never matched by contact name — two rows
with similar names are exactly how the wrong person's phone number gets
attached. A result that comes back without a usable `row_id` is dropped and
counted in a warning, never guessed at.

The script also refuses to start if any input row has the wrong field count.
A shifted row silently moves data into neighbouring columns, which produces
output that looks right and is not.

## Input requirements

FullEnrich needs `firstname` + `lastname` + (`domain` or `company_name`).
`linkedin_url` is optional but materially raises the hit rate, so include it
where you have it.

`contact_name` is split first-token / last-token. A surname that is only an
initial is still submitted, but flagged in the run log as low-odds.

## Known data issues in `data/contacts.tsv`

- **Alexander Younes (Dovetail)** — the source row was short one field, which
  shifted every column from `company_phone` rightward: the phone-status text
  sat in `company_phone`, the Reddit URL sat in `phone_status`, and
  `enrichment_notes` fell off the end. Corrected here; fix it in the source
  sheet too.
- **Andrew H. (Recorded Future)** and **Debbie F. (Remote)** — surname is an
  initial. Both will likely miss. Their LinkedIn URLs suggest `Andrew Hoyt`
  and `Debbie Fossum`; confirm and fill in the real surnames for a real shot.
- **`#ERROR!` in `company_phone`** on Erica Leigh French and David Thai —
  treated as empty, not as a phone number.
- **6 rows have no `linkedin_url`**, which lowers their hit rate.

## Tests

`tests/mock_fullenrich.py` stands in for the API so the full submit → poll →
match → write path can be exercised offline:

```bash
python3 tests/mock_fullenrich.py 8777 &
export no_proxy=127.0.0.1
FULLENRICH_API_KEY=test python3 enrich_phones.py \
    --api-base http://127.0.0.1:8777/api/v1 --output /tmp/out.tsv
```

The mock encodes each row's index inside the phone number it returns, so
misalignment between a result and its row shows up as a wrong digit rather
than passing silently.

## One caveat on the API schema

`docs.fullenrich.com` is also blocked by the same egress policy, so the
request and response shapes here come from secondary sources, not the vendor
reference. The submit path and the field names are the well-documented parts;
the *result* envelope is the guess. The parser walks the response for
phone-shaped values instead of assuming one fixed layout, and `--probe` prints
the raw JSON. Run `--probe --limit 2` first — if the envelope differs, that
output shows it for the cost of two credits.
