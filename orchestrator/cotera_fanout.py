"""Fan a sheet of hiring rows out to a single Cotera focused agent, in parallel.

The orchestrator does exactly three things per row:

  1. build ``raw_hiring_row`` from the sheet columns,
  2. send it to the focused agent,
  3. record what the agent returned.

It never generates copy, never edits the agent's output, and never writes to the
Google Doc -- the agent owns the doc insertion. That keeps every message
consistent, which is the whole point of routing through one focused agent.

Usage:

    python orchestrator/cotera_fanout.py --input rows.csv --dry-run
    python orchestrator/cotera_fanout.py --input rows.csv --concurrency 5

See orchestrator/README.md for configuration and the resume/dedupe model.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_AGENT_ID = "92e07017-49a4-54f4-9913-f887bc2284f8"
DEFAULT_GOOGLE_DOC_ID = "1jmuUvzNz55xQTAo29Vwh5eEifgCCqew416zRM2UGReM"
DEFAULT_API_BASE = "https://api.cotera.co"
# Path template for the agent-run endpoint. Overridable because the exact route
# is deployment-specific -- see README.md ("Pointing at the real endpoint").
DEFAULT_RUN_PATH = "/v1/agents/{agent_id}/runs"
# Route that accepts a message for Coco. Also unverified -- set COTERA_COCO_PATH.
DEFAULT_COCO_PATH = "/v1/coco/messages"

RETRY_STATUSES = {408, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5


class ConfigError(Exception):
    """Raised for missing credentials or unusable column mappings."""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# Row loading and payload construction
# --------------------------------------------------------------------------


def load_rows(path: Path, header_row: int) -> list[dict[str, str]]:
    """Read a CSV/TSV export, treating line ``header_row`` (1-indexed) as headers."""
    delimiter = "\t" if path.suffix.lower() in {".tsv", ".tab"} else ","
    with path.open(newline="", encoding="utf-8-sig") as handle:
        lines = handle.readlines()

    if header_row > len(lines):
        raise ConfigError(f"--header-row {header_row} is past the end of {path}")

    reader = csv.DictReader(lines[header_row - 1 :], delimiter=delimiter)
    rows = []
    for row in reader:
        # Drop the None key csv produces for ragged rows, and blank trailing columns.
        cleaned = {
            (k or "").strip(): (v or "").strip()
            for k, v in row.items()
            if k and k.strip()
        }
        if any(cleaned.values()):
            rows.append(cleaned)
    return rows


def build_raw_hiring_row(row: dict[str, str], columns: list[str] | None) -> str:
    """Serialize the row for the agent, preserving column names and messiness.

    We deliberately do not clean, normalize, or summarize values -- the agent is
    the one that decides what matters in a messy row.
    """
    if columns:
        missing = [c for c in columns if c not in row]
        if missing:
            raise ConfigError(
                f"--columns names fields not in the sheet: {', '.join(missing)}"
            )
        items = [(c, row[c]) for c in columns]
    else:
        items = list(row.items())

    return "\n".join(f"{key}: {value}" for key, value in items if value)


def resolve_column(row: dict[str, str], names: list[str]) -> str:
    """Return the first entry of the first non-empty column among ``names``.

    Columns like ``job_links``, ``emails`` and ``linkedins`` hold several
    newline-separated entries per company. The dedupe key needs one stable
    value, so this takes the first entry -- the whole field still reaches the
    agent inside raw_hiring_row.
    """
    lowered = {k.lower(): v for k, v in row.items()}
    for name in names:
        value = lowered.get(name.lower(), "").strip()
        if value:
            return value.splitlines()[0].strip()
    return ""


def has_any_value(row: dict[str, str], names: list[str]) -> bool:
    lowered = {k.lower(): v for k, v in row.items()}
    return any(lowered.get(name.lower(), "").strip() for name in names)


def build_dedupe_key(row: dict[str, str], args: argparse.Namespace) -> str:
    """company_name|primary_job_url, normalized for stable matching.

    Per the Cotera spec, an unparseable company falls back to "Unknown Company"
    so the job URL still carries the identity.
    """
    company = resolve_column(row, args.company_col) or "Unknown Company"
    job_url = resolve_column(row, args.job_url_col)
    parts = [company, job_url]
    if args.contact_in_dedupe_key:
        parts.append(
            resolve_column(row, args.email_col)
            or resolve_column(row, args.linkedin_col)
        )
    return "|".join(part.strip().lower() for part in parts)


def render_instruction(template: str, row_text: str, args: argparse.Namespace) -> str:
    """Fill the Coco instruction template.

    Only these three placeholders are substituted. ``{{Company Name}}`` and
    ``{{Exact Agent Output}}`` are left intact on purpose -- they are literal
    instructions telling Coco what to write, not values we supply.
    """
    return (
        template.replace("{{agent_id}}", args.agent_id)
        .replace("{{google_doc_id}}", args.google_doc_id)
        .replace("{{raw_hiring_row}}", row_text)
    )


def build_payload(row: dict[str, str], args: argparse.Namespace) -> dict:
    """Build the request body, plus the dedupe key the ledger tracks it by."""
    row_text = build_raw_hiring_row(row, args.columns)
    dedupe_key = build_dedupe_key(row, args)

    if args.mode == "coco":
        # Coco runs the focused agent and writes the doc; we only hand it the row.
        return {
            "_dedupe_key": dedupe_key,
            args.message_field: render_instruction(args.instruction, row_text, args),
        }

    return {
        "_dedupe_key": dedupe_key,
        "agent_id": args.agent_id,
        "google_doc_id": args.google_doc_id,
        "raw_hiring_row": row_text,
        "output_destination": "google_doc",
        "write_mode": "insert_in_existing_structure",
        "dedupe_key": dedupe_key,
        "preserve_agent_output_exactly": True,
    }


# --------------------------------------------------------------------------
# Cotera client
# --------------------------------------------------------------------------


def run_agent(payload: dict, args: argparse.Namespace) -> dict:
    """POST one row to the focused agent, retrying transient failures.

    Returns the decoded response body. Raises on non-retryable errors and on
    exhausting retries, so the caller can record the row as failed.
    """
    path = args.coco_path if args.mode == "coco" else args.run_path
    url = args.api_base.rstrip("/") + path.format(agent_id=args.agent_id)
    # _dedupe_key is bookkeeping for the ledger, not part of the API contract.
    body = json.dumps({k: v for k, v in payload.items() if k != "_dedupe_key"}).encode(
        "utf-8"
    )

    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {args.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=args.timeout) as response:
                raw = response.read().decode("utf-8")
                try:
                    return json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    # Some deployments return the agent's plain-text output directly.
                    return {"output": raw}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            last_error = RuntimeError(f"HTTP {exc.code}: {detail}")
            if exc.code not in RETRY_STATUSES:
                raise last_error from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = RuntimeError(f"network error: {exc}")

        if attempt < MAX_ATTEMPTS:
            backoff = 2**attempt + random.uniform(0, 1)
            time.sleep(backoff)

    raise last_error or RuntimeError("agent run failed")


# --------------------------------------------------------------------------
# Ledger (dedupe + resume)
# --------------------------------------------------------------------------


class Ledger:
    """Append-only JSONL record of every attempt, keyed by dedupe_key.

    Rows that already succeeded are skipped on re-runs, so a partially failed
    batch can be re-run safely without double-posting into the doc.
    """

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self.succeeded: set[str] = set()
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("status") == "ok" and entry.get("dedupe_key"):
                        self.succeeded.add(entry["dedupe_key"])

    def record(self, entry: dict) -> None:
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")
            if entry.get("status") == "ok" and entry.get("dedupe_key"):
                self.succeeded.add(entry["dedupe_key"])


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fan sheet rows out to one Cotera focused agent, in parallel."
    )
    parser.add_argument(
        "--input", required=True, type=Path, help="CSV/TSV export of the hiring sheet"
    )
    parser.add_argument(
        "--header-row",
        type=int,
        default=1,
        help="1-indexed line holding the column headers (default: 1)",
    )
    parser.add_argument(
        "--columns",
        nargs="+",
        help="Subset of columns to send as raw_hiring_row (default: every column)",
    )
    parser.add_argument("--company-col", nargs="+", default=["company", "Company"])
    parser.add_argument(
        "--job-url-col", nargs="+", default=["job_links", "Job URL", "Job Link"]
    )
    parser.add_argument("--email-col", nargs="+", default=["emails", "Email"])
    parser.add_argument(
        "--linkedin-col", nargs="+", default=["linkedins", "LinkedIn URL"]
    )
    parser.add_argument(
        "--contact-in-dedupe-key",
        action="store_true",
        help="Append the primary email/LinkedIn to the dedupe key "
        "(default: company|primary_job_url, per the Cotera spec)",
    )
    parser.add_argument(
        "--require",
        nargs="+",
        metavar="COL",
        help="Skip rows where all of these columns are empty "
        "(e.g. --require emails linkedins skips companies with no contact)",
    )
    parser.add_argument(
        "--mode",
        choices=["coco", "agent"],
        default="coco",
        help="coco: send the instruction to Coco, which runs the agent AND writes "
        "the doc. agent: call the focused agent directly and write nothing "
        "(default: coco)",
    )
    parser.add_argument(
        "--instruction-file",
        type=Path,
        default=Path(__file__).with_name("coco_instruction.txt"),
        help="Instruction template used in coco mode",
    )
    parser.add_argument(
        "--message-field",
        default="message",
        help="JSON field Coco expects the instruction in (default: message)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        help="Rows in flight at once (default: 1 in coco mode, 5 in agent mode). "
        "Appending to one doc is a read-modify-write, so parallel coco runs can "
        "interleave entries -- raise this only if Cotera confirms writes are locked",
    )
    parser.add_argument("--limit", type=int, help="Process at most N rows")
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("orchestrator/runs.jsonl"),
        help="Attempt log used for dedupe and resume",
    )
    parser.add_argument(
        "--rerun-succeeded",
        action="store_true",
        help="Re-send rows the ledger already marked ok (default: skip them)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the payloads that would be sent; make no API calls",
    )
    parser.add_argument("--timeout", type=int, default=300, help="Per-run seconds")
    parser.add_argument(
        "--agent-id", default=os.environ.get("FOCUSED_AGENT_ID", DEFAULT_AGENT_ID)
    )
    parser.add_argument(
        "--google-doc-id",
        default=os.environ.get("GOOGLE_DOC_ID", DEFAULT_GOOGLE_DOC_ID),
    )
    parser.add_argument(
        "--api-base", default=os.environ.get("COTERA_API_BASE", DEFAULT_API_BASE)
    )
    parser.add_argument(
        "--run-path", default=os.environ.get("COTERA_RUN_PATH", DEFAULT_RUN_PATH)
    )
    parser.add_argument(
        "--coco-path", default=os.environ.get("COTERA_COCO_PATH", DEFAULT_COCO_PATH)
    )
    args = parser.parse_args(argv)
    args.api_key = os.environ.get("COTERA_API_KEY", "")

    if args.concurrency is None:
        # One at a time in coco mode: every run appends to the same document.
        args.concurrency = 1 if args.mode == "coco" else 5

    args.instruction = ""
    if args.mode == "coco":
        try:
            args.instruction = args.instruction_file.read_text(encoding="utf-8")
        except OSError as exc:
            parser.error(f"could not read {args.instruction_file}: {exc}")
        if "{{raw_hiring_row}}" not in args.instruction:
            parser.error(
                f"{args.instruction_file} has no {{{{raw_hiring_row}}}} placeholder"
            )
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.dry_run and not args.api_key:
        print("COTERA_API_KEY is not set (use --dry-run to preview)", file=sys.stderr)
        return 2

    try:
        rows = load_rows(args.input, args.header_row)
    except (OSError, ConfigError) as exc:
        print(f"could not read {args.input}: {exc}", file=sys.stderr)
        return 2

    if not rows:
        print(f"no data rows found in {args.input}", file=sys.stderr)
        return 2

    skipped_empty = 0
    if args.require:
        kept = [row for row in rows if has_any_value(row, args.require)]
        skipped_empty = len(rows) - len(kept)
        rows = kept

    try:
        payloads = [build_payload(row, args) for row in rows]
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    ledger = Ledger(args.ledger)

    queued: list[dict] = []
    seen_this_run: set[str] = set()
    skipped_done = skipped_dupe = 0
    for payload in payloads:
        key = payload["_dedupe_key"]
        if key in seen_this_run:
            skipped_dupe += 1
            continue
        if key in ledger.succeeded and not args.rerun_succeeded:
            skipped_done += 1
            continue
        seen_this_run.add(key)
        queued.append(payload)

    if args.limit:
        queued = queued[: args.limit]

    summary = [
        f"{len(queued)} to run",
        f"{skipped_done} already done",
        f"{skipped_dupe} duplicate keys",
    ]
    if args.require:
        summary.append(f"{skipped_empty} missing {'/'.join(args.require)}")
    print(f"{len(rows) + skipped_empty} rows read | " + " | ".join(summary))

    if args.dry_run:
        for payload in queued:
            print(json.dumps(payload, indent=2))
        print(f"\ndry run: {len(queued)} agent runs not sent")
        return 0

    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    failures = 0

    def dispatch(payload: dict) -> tuple[dict, dict]:
        return payload, run_agent(payload, args)

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(dispatch, p): p for p in queued}
        for done, future in enumerate(as_completed(futures), start=1):
            payload = futures[future]
            key = payload["_dedupe_key"]
            try:
                _, response = future.result()
            except Exception as exc:  # noqa: BLE001 - every row failure is recorded
                failures += 1
                ledger.record(
                    {
                        "ts": utcnow(),
                        "dedupe_key": key,
                        "status": "error",
                        "error": str(exc),
                    }
                )
                print(f"[{done}/{len(queued)}] FAIL {key}: {exc}", file=sys.stderr)
                continue

            ledger.record(
                {
                    "ts": utcnow(),
                    "dedupe_key": key,
                    "status": "ok",
                    "run_id": response.get("id") or response.get("run_id"),
                    "response": response,
                }
            )
            print(f"[{done}/{len(queued)}] ok   {key}")

    print(f"\ndone: {len(queued) - failures} succeeded, {failures} failed")
    print(f"ledger: {args.ledger}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
