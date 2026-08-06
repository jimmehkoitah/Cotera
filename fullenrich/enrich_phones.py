#!/usr/bin/env python3
"""Attach FullEnrich phone numbers to a TSV contact export.

Reads a TSV, sends each usable row to FullEnrich's bulk waterfall enrichment,
polls for the result, and writes the same TSV back with the phone columns
filled in. Row order and every original column are preserved, so the output
can be pasted straight back over the source sheet.

Results are matched back to rows by an opaque per-row id round-tripped through
FullEnrich's `custom` field -- never by name. Name matching is what silently
attaches the wrong person's phone number when two rows collide.

Usage:
    export FULLENRICH_API_KEY=...
    python3 enrich_phones.py --dry-run                 # build payloads, call nothing
    python3 enrich_phones.py --probe --limit 2         # 2 contacts, dump raw JSON
    python3 enrich_phones.py                           # full run
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_API_BASE = "https://app.fullenrich.com/api/v1"

# FullEnrich bulk limits: 100 contacts per call, 60 calls/minute.
MAX_BATCH = 100
POLL_INTERVAL_SEC = 10
POLL_TIMEOUT_SEC = 900

# Columns this script writes. Everything else is passed through untouched.
COL_DIRECT = "direct_phone"
COL_COMPANY = "company_phone"
COL_STATUS = "phone_status"

# Values that look populated but mean "empty".
JUNK_VALUES = {"", "#ERROR!", "#N/A", "N/A", "-", "null", "None"}


class FullEnrichError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# input
# --------------------------------------------------------------------------

def read_tsv(path):
    """Read the TSV, refusing anything with a ragged row.

    A row with the wrong field count means the columns are shifted, and a
    shifted row is exactly how a phone number lands on the wrong contact.
    Better to stop than to write a plausible-looking wrong answer.
    """
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh, delimiter="\t")
        try:
            header = next(reader)
        except StopIteration:
            raise FullEnrichError(f"{path} is empty")
        rows = list(reader)

    problems = []
    for i, row in enumerate(rows, start=2):  # +2: 1-indexed, and header is line 1
        if len(row) != len(header):
            problems.append(f"  line {i}: {len(row)} fields, expected {len(header)}")
    if problems:
        raise FullEnrichError(
            "Ragged rows -- columns are shifted, so enrichment would attach "
            "phones to the wrong contacts. Fix these lines first:\n"
            + "\n".join(problems)
        )

    for required in (COL_DIRECT, COL_COMPANY, COL_STATUS):
        if required not in header:
            raise FullEnrichError(f"{path} has no '{required}' column")

    return header, [dict(zip(header, row)) for row in rows]


def clean(value):
    value = (value or "").strip()
    return "" if value in JUNK_VALUES else value


def split_name(full_name):
    """Split a display name into (firstname, lastname, note).

    First token wins as the given name, last token as the surname; anything in
    between is dropped, which is what FullEnrich expects. A surname that is
    just an initial ("Andrew H.") is returned with a warning note -- the
    waterfall providers key on a real surname and will usually miss.
    """
    parts = clean(full_name).split()
    if len(parts) < 2:
        return "", "", "no surname -- FullEnrich needs firstname + lastname"
    first, last = parts[0], parts[-1]
    if len(last.rstrip(".")) <= 1:
        return first, last, f"surname is an initial ({last!r}) -- low match odds"
    return first, last, ""


def build_payload(row, row_id):
    """Build one FullEnrich contact payload, or return (None, reason)."""
    first, last, note = split_name(row.get("contact_name", ""))
    if not first or not last:
        return None, note

    domain = clean(row.get("domain"))
    company = clean(row.get("company"))
    if not domain and not company:
        return None, "no domain and no company name"

    payload = {
        "firstname": first,
        "lastname": last,
        "enrich_fields": ["contact.phones"],
        # Round-tripped verbatim by FullEnrich; this is how results find their
        # way home without us ever matching on a name.
        "custom": {"row_id": row_id},
    }
    if domain:
        payload["domain"] = domain
    if company:
        payload["company_name"] = company

    linkedin = clean(row.get("linkedin_url"))
    if linkedin:
        payload["linkedin_url"] = linkedin

    return payload, note


# --------------------------------------------------------------------------
# api
# --------------------------------------------------------------------------

def request_json(url, api_key, method="GET", body=None, timeout=60):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        if exc.code in (401, 403):
            raise FullEnrichError(
                f"HTTP {exc.code} from FullEnrich -- check FULLENRICH_API_KEY. {detail}"
            )
        raise FullEnrichError(f"HTTP {exc.code} from {method} {url}: {detail}")
    except urllib.error.URLError as exc:
        raise FullEnrichError(
            f"Could not reach {url}: {exc.reason}. If you are behind a "
            f"restrictive egress proxy, app.fullenrich.com must be allowlisted."
        )


def submit_batch(api_base, api_key, contacts, batch_name):
    body = {"name": batch_name, "datas": contacts}
    result = request_json(f"{api_base}/contact/enrich/bulk", api_key, "POST", body)
    enrichment_id = (
        result.get("enrichment_id") or result.get("id") or result.get("bulk_id")
    )
    if not enrichment_id:
        raise FullEnrichError(f"No enrichment id in response: {json.dumps(result)[:400]}")
    return enrichment_id, result


def poll_batch(api_base, api_key, enrichment_id, timeout=POLL_TIMEOUT_SEC, quiet=False):
    """Poll until the batch reports a terminal status, then return the payload."""
    url = f"{api_base}/contact/enrich/bulk/{enrichment_id}"
    deadline = time.time() + timeout
    attempt = 0
    while True:
        result = request_json(url, api_key)
        status = str(result.get("status", "")).upper()
        if status in ("FINISHED", "COMPLETED", "DONE", "SUCCESS", ""):
            return result
        if status in ("FAILED", "ERROR", "CANCELED", "CANCELLED"):
            raise FullEnrichError(f"Batch {enrichment_id} ended as {status}")
        if time.time() >= deadline:
            raise FullEnrichError(
                f"Batch {enrichment_id} still {status} after {timeout}s. "
                f"It is not lost -- re-poll with --resume {enrichment_id}."
            )
        attempt += 1
        if not quiet:
            print(f"    {status or 'PENDING'}... (poll {attempt})", file=sys.stderr)
        time.sleep(POLL_INTERVAL_SEC)


# --------------------------------------------------------------------------
# response parsing
# --------------------------------------------------------------------------

def iter_result_records(payload):
    """Yield per-contact records from a bulk result, whatever it is nested in."""
    if isinstance(payload, list):
        return payload
    for key in ("datas", "data", "results", "contacts", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def collect_phones(record):
    """Pull every phone-ish value out of a record, newest schema or old.

    Returns a list of (number, kind, confidence) with kind in
    {"mobile", "direct", "company", "unknown"}.
    """
    found = []

    def classify(entry):
        label = " ".join(
            str(entry.get(k, "")) for k in ("type", "kind", "label", "category")
        ).lower()
        if "mobile" in label or "cell" in label:
            return "mobile"
        if "direct" in label or "personal" in label:
            return "direct"
        if "hq" in label or "company" in label or "office" in label or "work" in label:
            return "company"
        return "unknown"

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if "phone" in key.lower():
                    if isinstance(value, str) and value.strip():
                        found.append((value.strip(), "unknown", None))
                    elif isinstance(value, list):
                        for entry in value:
                            if isinstance(entry, str) and entry.strip():
                                found.append((entry.strip(), "unknown", None))
                            elif isinstance(entry, dict):
                                number = (
                                    entry.get("number")
                                    or entry.get("phone")
                                    or entry.get("value")
                                    or ""
                                ).strip()
                                if number:
                                    found.append(
                                        (
                                            number,
                                            classify(entry),
                                            entry.get("confidence")
                                            or entry.get("score"),
                                        )
                                    )
                    elif isinstance(value, dict):
                        walk(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(record)

    deduped, seen = [], set()
    for number, kind, confidence in found:
        if number not in seen:
            seen.add(number)
            deduped.append((number, kind, confidence))
    return deduped


def record_row_id(record):
    """Recover the row_id we sent, wherever FullEnrich echoed it back."""
    for key in ("custom", "custom_fields", "metadata"):
        blob = record.get(key)
        if isinstance(blob, dict) and "row_id" in blob:
            return str(blob["row_id"])
        if isinstance(blob, str):
            try:
                parsed = json.loads(blob)
                if isinstance(parsed, dict) and "row_id" in parsed:
                    return str(parsed["row_id"])
            except (ValueError, TypeError):
                pass
    if "row_id" in record:
        return str(record["row_id"])
    return None


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default="data/contacts.tsv")
    parser.add_argument("--output", default="data/contacts_enriched.tsv")
    parser.add_argument("--api-base", default=os.environ.get("FULLENRICH_API_BASE", DEFAULT_API_BASE))
    parser.add_argument("--limit", type=int, help="only enrich the first N eligible rows")
    parser.add_argument("--dry-run", action="store_true", help="build payloads, call nothing")
    parser.add_argument("--probe", action="store_true", help="dump raw API JSON (schema check)")
    parser.add_argument("--overwrite", action="store_true", help="replace existing phone values")
    parser.add_argument("--resume", help="skip submit, poll this existing enrichment id")
    parser.add_argument("--batch-name", default="cotera-phone-enrichment")
    args = parser.parse_args()

    try:
        header, rows = read_tsv(args.input)
    except FullEnrichError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Read {len(rows)} rows from {args.input}", file=sys.stderr)

    # Decide what to send.
    payloads, skipped, notes = [], [], {}
    for index, row in enumerate(rows):
        row_id = str(index)
        already = clean(row.get(COL_DIRECT))
        if already and not args.overwrite:
            skipped.append((index, row.get("contact_name", ""), "already has a phone"))
            continue
        payload, note = build_payload(row, row_id)
        if note:
            notes[row_id] = note
        if payload is None:
            skipped.append((index, row.get("contact_name", ""), note))
            continue
        payloads.append(payload)
        if args.limit and len(payloads) >= args.limit:
            break

    print(f"Eligible to enrich: {len(payloads)}   Skipped: {len(skipped)}", file=sys.stderr)
    for index, name, reason in skipped:
        print(f"  skip row {index + 2}: {name or '(no name)'} -- {reason}", file=sys.stderr)
    for row_id, note in notes.items():
        if note and not any(s[0] == int(row_id) for s in skipped):
            print(f"  warn row {int(row_id) + 2}: {note}", file=sys.stderr)

    if args.dry_run:
        print(json.dumps(payloads, indent=2, ensure_ascii=False))
        print(f"\n[dry run] would submit {len(payloads)} contacts, nothing was called.", file=sys.stderr)
        return 0

    if not payloads and not args.resume:
        print("Nothing to enrich.", file=sys.stderr)
        return 0

    api_key = os.environ.get("FULLENRICH_API_KEY", "").strip()
    if not api_key:
        print("error: FULLENRICH_API_KEY is not set", file=sys.stderr)
        return 2

    # Submit and poll.
    results = []
    try:
        if args.resume:
            batches = [args.resume]
            print(f"Resuming enrichment {args.resume}", file=sys.stderr)
        else:
            batches = []
            for start in range(0, len(payloads), MAX_BATCH):
                chunk = payloads[start:start + MAX_BATCH]
                name = f"{args.batch_name}-{start // MAX_BATCH + 1}"
                enrichment_id, raw = submit_batch(args.api_base, api_key, chunk, name)
                print(f"Submitted {len(chunk)} contacts -> {enrichment_id}", file=sys.stderr)
                if args.probe:
                    print("--- raw submit response ---")
                    print(json.dumps(raw, indent=2, ensure_ascii=False))
                batches.append(enrichment_id)
                if start + MAX_BATCH < len(payloads):
                    time.sleep(1)  # stay under 60 calls/min

        for enrichment_id in batches:
            print(f"Polling {enrichment_id}...", file=sys.stderr)
            payload = poll_batch(args.api_base, api_key, enrichment_id)
            if args.probe:
                print("--- raw result response ---")
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            results.extend(iter_result_records(payload))
    except FullEnrichError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Received {len(results)} result records", file=sys.stderr)

    # Match results back to rows by row_id.
    unmatched = 0
    hits = 0
    for record in results:
        row_id = record_row_id(record)
        if row_id is None or not row_id.isdigit() or int(row_id) >= len(rows):
            unmatched += 1
            continue
        row = rows[int(row_id)]
        phones = collect_phones(record)
        if not phones:
            # Append rather than replace: the existing note (e.g. an Apollo
            # result) is still true, and silently dropping it would hide that
            # a second vendor was also tried and also missed.
            prior = clean(row.get(COL_STATUS))
            marker = "FullEnrich: no phone found"
            if marker not in prior:
                row[COL_STATUS] = f"{prior}; {marker}" if prior else marker
            continue

        mobile = [p for p in phones if p[1] in ("mobile", "direct")]
        company = [p for p in phones if p[1] == "company"]
        other = [p for p in phones if p[1] == "unknown"]

        direct = (mobile or other or [(None, None, None)])[0]
        if direct[0]:
            row[COL_DIRECT] = direct[0]
            hits += 1
        if company:
            row[COL_COMPANY] = company[0][0]
        elif clean(row.get(COL_COMPANY)) == "" or clean(row.get(COL_COMPANY)) == "#ERROR!":
            row[COL_COMPANY] = ""

        bits = [f"FullEnrich: {len(phones)} phone(s)"]
        if direct[2] is not None:
            bits.append(f"confidence {direct[2]}")
        if len(phones) > 1:
            bits.append("extras: " + ", ".join(p[0] for p in phones[1:]))
        row[COL_STATUS] = "; ".join(bits)

    if unmatched:
        print(
            f"warning: {unmatched} result record(s) had no usable row_id and were "
            f"dropped rather than guessed at by name.",
            file=sys.stderr,
        )

    # Write output, preserving every original column and row order.
    with open(args.output, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in header})

    print(f"\nPhones found: {hits}/{len(payloads)}", file=sys.stderr)
    print(f"Wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
