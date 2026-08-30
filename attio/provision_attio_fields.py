#!/usr/bin/env python3
"""Create/verify the Cotera RevOps custom fields on Attio's Companies and People objects.

Additive only: this script never deletes, renames, retypes, or archives an existing
attribute, and never touches records, lists, pipeline stages, automations or permissions.
A slug that already exists is reported and left exactly as-is.

Usage:
    export ATTIO_API_KEY=...            # needs object_configuration:read-write
    python3 attio/provision_attio_fields.py            # dry run, shows the plan
    python3 attio/provision_attio_fields.py --apply    # actually creates

The `type` values in cotera_fields.json are the identifiers Attio returns for this
workspace's existing attributes, so they are known-good for this tenant.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_ROOT = "https://api.attio.com/v2"
SPEC = Path(__file__).with_name("cotera_fields.json")


def request(path, token, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API_ROOT}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SystemExit(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc


def fetch_attributes(obj, token):
    """Return {api_slug: attribute} for an object, following pagination."""
    found, offset = {}, 0
    while True:
        page = request(f"/objects/{obj}/attributes?limit=50&offset={offset}", token=token, method="GET")
        items = page.get("data", [])
        for attr in items:
            found[attr["api_slug"]] = attr
        if len(items) < 50:
            return found
        offset += len(items)


def fetch_options(obj, slug, token):
    page = request(f"/objects/{obj}/attributes/{slug}/options", token=token, method="GET")
    return {opt["title"] for opt in page.get("data", [])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="perform writes (default: dry run)")
    args = parser.parse_args()

    token = os.environ.get("ATTIO_API_KEY")
    if not token:
        sys.exit("ATTIO_API_KEY is not set.")

    spec = json.loads(SPEC.read_text())
    created, existed, options_added = [], [], []

    for obj, fields in spec["objects"].items():
        existing = fetch_attributes(obj, token)
        print(f"\n== {obj}: {len(existing)} existing attributes ==")

        for field in fields:
            slug = field["api_slug"]
            ref = f"{obj}.{slug}"

            if slug in existing:
                actual = existing[slug]["type"]
                note = "" if actual == field["type"] else f"  [!] type is {actual!r}, spec wants {field['type']!r}"
                existed.append(ref + note)
                print(f"  exists   {slug} ({actual}){note}")
            else:
                payload = {
                    "data": {
                        "title": field["title"],
                        "description": field["description"],
                        "api_slug": slug,
                        "type": field["type"],
                        "is_required": False,
                        "is_unique": False,
                        "is_multiselect": False,
                    }
                }
                if args.apply:
                    request(f"/objects/{obj}/attributes", token=token, method="POST", body=payload)
                created.append(ref)
                print(f"  {'create ' if args.apply else 'WOULD  '} {slug} ({field['type']})")

            # Reconcile select options additively; never removes an option.
            wanted = field.get("options")
            if not wanted:
                continue
            present = fetch_options(obj, slug, token) if (slug in existing and args.apply) else set()
            for title in wanted:
                if title in present:
                    continue
                if args.apply:
                    request(
                        f"/objects/{obj}/attributes/{slug}/options",
                        token=token,
                        method="POST",
                        body={"data": {"title": title}},
                    )
                options_added.append(f"{ref}={title}")
                print(f"      {'option ' if args.apply else 'WOULD  '} {title}")

    verb = "Created" if args.apply else "Would create"
    print(f"\n{verb}: {len(created)} attributes, {len(options_added)} select options")
    print(f"Already existed: {len(existed)}")
    for line in existed:
        if "[!]" in line:
            print(f"  needs manual review: {line}")
    if not args.apply:
        print("\nDry run only. Re-run with --apply to write to Attio.")


if __name__ == "__main__":
    main()
