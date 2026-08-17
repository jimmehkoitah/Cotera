"""Export above-the-line stakeholders who have a LinkedIn but no email.

The by-company sheet stores ``committee``, ``linkedins`` and ``emails`` as
separate newline-separated lists. They are compressed independently -- a company
with 15 committee members can list 12 LinkedIn URLs and 7 emails -- so position
in one list does not identify a person in another. Everything here therefore
matches on names, and only confident matches are reported.

Emails are name-derived (``nina.etienne@booksy.com``) and match well. LinkedIn
slugs are sometimes opaque (``maedbo`` for Maxime Edgar Bonnet), so a person can
have a LinkedIn we cannot confidently attribute; those are counted and excluded
rather than guessed, because a mis-paired URL enriches the wrong person.

    python orchestrator/build_enrichment_csv.py --input sheet.csv --out enrich.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path

# Seniority prefixes in the committee column, most senior first.
ABOVE_THE_LINE = ["C-Suite", "VP", "Director"]
BELOW_THE_LINE = ["Manager", "Employee"]

COMMITTEE_RE = re.compile(r"^\s*([^:]{1,25}?)\s*:\s*(.+?)\s*(?:—|--|–)\s*(.*)$")


UMLAUT_EXPANSIONS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}


def normalize(text: str) -> str:
    """Lowercase, strip accents, drop everything but letters."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", stripped.lower())


def normalize_variants(text: str) -> set[str]:
    """Both spellings of a name: accents folded, and umlauts expanded.

    German names travel either way -- "Strüven" becomes both "struven" and
    "strueven", and the email may use either.
    """
    expanded = "".join(UMLAUT_EXPANSIONS.get(c, c) for c in text.lower())
    return {normalize(text), normalize(expanded)} - {""}


# Credentials and generational suffixes that must not be read as surnames.
NAME_SUFFIXES = {
    "mba", "phd", "md", "cpa", "jd", "msc", "bsc", "ma", "cfa", "pmp",
    "jr", "sr", "ii", "iii", "iv",
}


def name_tokens(name: str) -> list[str]:
    """Meaningful name parts, dropping initials, masked parts and credentials."""
    parts = []
    for raw in re.split(r"[\s.,]+", name):
        if "*" in raw:  # masked in the source, e.g. "Ur***o"
            continue
        token = normalize(raw)
        if len(token) > 1 and token not in NAME_SUFFIXES:
            parts.append(token)
    return parts


class Person:
    def __init__(self, company: str, level: str, name: str, title: str):
        self.company = company
        self.level = level
        self.name = name
        self.title = title
        self.tokens = name_tokens(name)
        self.email = ""
        self.linkedin = ""

    @property
    def first(self) -> str:
        return self.tokens[0] if self.tokens else ""

    @property
    def last(self) -> str:
        return self.tokens[-1] if len(self.tokens) > 1 else ""

    @property
    def display_first(self) -> str:
        return self.name.split()[0] if self.name.split() else ""

    @property
    def display_last(self) -> str:
        parts = self.name.split()
        return parts[-1] if len(parts) > 1 else ""


def score_identifier(person: Person, blob: str, first_is_unique: bool = True) -> int:
    """How strongly ``blob`` (email local part or LinkedIn slug) names ``person``.

    2 = confident, 1 = plausible, 0 = no. ``first_is_unique`` says whether the
    person's first name is unique within their company; first-name-only handles
    (``hunter@basiccapital.com``) are only confident when nobody else could
    claim them.
    """
    if not person.tokens:
        return 0
    flat = normalize(blob)
    if not flat:
        return 0

    first, last = person.first, person.last

    # Any token after the first can be the surname in the handle: maiden names
    # appear parenthetically ("Katie (Kelley) Linafelter" -> "kkelley@").
    surnames = [s for token in person.tokens[1:] for s in normalize_variants(token)]
    firsts = normalize_variants(person.display_first) or {first}

    for surname in surnames:
        has_surname = surname in flat
        matching_first = next((f for f in firsts if f in flat), "")
        if has_surname and matching_first:
            return 2
        # first-initial + surname, e.g. "jkoitah", "j.koitah", "kkelley"
        if has_surname and (flat.startswith(first[0]) or f"{first[0]}{surname}" in flat):
            return 2
        # Transliteration drops a prefix: "Elgammal" -> "agammal", "gammal"
        if len(surname) >= 6 and surname[2:] in flat and flat.startswith(first[0]):
            return 2
        if has_surname and len(surname) >= 5:
            return 1

    # Initials-only handle: "ccr@" for Carl-Christoph Reckers, "jj@" for June-June.
    initials = "".join(t[0] for t in person.tokens)
    # Hyphenated given names contribute both letters: "Carl-Christoph" -> "cc".
    parts = [normalize(p) for p in re.split(r"[-\s]+", person.name)]
    hyphen_initials = "".join(p[0] for p in parts if p)
    # A prefix covers initials of the given name alone: "jj@" for June-June Shih.
    if 2 <= len(flat) <= 4 and (
        flat in {initials, hyphen_initials} or hyphen_initials.startswith(flat)
    ):
        return 1

    if surnames:
        # First-name-only handle: "marlon@", "hunter@", "daniel@"
        if flat in firsts:
            return 2 if first_is_unique else 1
        if any(f in flat and len(f) >= 4 for f in firsts):
            return 2 if first_is_unique else 1
        # Nickname or shortened first name, either direction:
        # "jono" for Jonathan, "jonathan@" for Jon, "chris@" for Christopher.
        if first_is_unique and len(flat) >= 3:
            shared = len(os.path.commonprefix([flat, first]))
            if shared >= 3 and shared >= min(len(flat), len(first)) - 1:
                return 1
    else:
        # Masked or single-token name ("Piotr R."): first name alone is weak
        # evidence, so only accept it when the blob leads with that name.
        if first and flat.startswith(first):
            return 1
    return 0


def best_match(
    person: Person,
    candidates: list[str],
    used: set[str],
    first_is_unique: bool = True,
) -> tuple[str, int]:
    """Pick the highest-scoring unused candidate for this person."""
    best, best_score = "", 0
    for candidate in candidates:
        if candidate in used:
            continue
        blob = candidate.split("@")[0] if "@" in candidate else candidate
        blob = re.sub(r"^https?://(www\.)?linkedin\.com/in/", "", blob).strip("/")
        blob = re.sub(r"\d+$", "", blob)  # trailing id digits
        score = score_identifier(person, blob, first_is_unique)
        if score > best_score:
            best, best_score = candidate, score
    return best, best_score


def split_lines(row: dict[str, str], key: str) -> list[str]:
    return [x.strip() for x in (row.get(key) or "").split("\n") if x.strip()]


def parse_committee(row: dict[str, str]) -> list[Person]:
    people = []
    for entry in split_lines(row, "committee"):
        match = COMMITTEE_RE.match(entry)
        if match:
            level, name, title = match.groups()
        elif ":" in entry:
            level, rest = entry.split(":", 1)
            name, title = rest.strip(), ""
        else:
            continue
        people.append(Person(row.get("company", "").strip(), level.strip(), name, title))
    return people


def company_domain(emails: list[str]) -> str:
    """Most common domain among the company's known emails."""
    domains = [e.split("@")[1].lower() for e in emails if "@" in e]
    return Counter(domains).most_common(1)[0][0] if domains else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--levels",
        nargs="+",
        default=ABOVE_THE_LINE,
        help=f"Seniority levels to include (default: {' '.join(ABOVE_THE_LINE)})",
    )
    parser.add_argument(
        "--min-linkedin-score",
        type=int,
        default=2,
        choices=[1, 2],
        help="1 keeps plausible LinkedIn pairings, 2 only confident ones (default: 2)",
    )
    args = parser.parse_args(argv)

    with args.input.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    stats = Counter()
    out_rows = []

    for row in rows:
        emails = split_lines(row, "emails")
        linkedins = split_lines(row, "linkedins")
        people = parse_committee(row)
        stats["people"] += len(people)
        stats["emails_listed"] += len(emails)

        used_emails: set[str] = set()
        used_linkedins: set[str] = set()
        first_counts = Counter(p.first for p in people if p.first)

        # Confident passes first, so a strong match is never stolen by a weak one.
        for min_score in (2, 1):
            for person in people:
                unique = first_counts[person.first] == 1 if person.first else False
                if not person.email:
                    match, score = best_match(person, emails, used_emails, unique)
                    if match and score >= min_score:
                        person.email = match
                        used_emails.add(match)
                if not person.linkedin:
                    match, score = best_match(person, linkedins, used_linkedins, unique)
                    if match and score >= max(min_score, args.min_linkedin_score):
                        person.linkedin = match
                        used_linkedins.add(match)

        stats["emails_matched"] += len(used_emails)
        stats["emails_unmatched"] += len(emails) - len(used_emails)
        stats["linkedins_unmatched"] += len(linkedins) - len(used_linkedins)

        domain = company_domain(emails)
        job_link = (split_lines(row, "job_links") or [""])[0]

        for person in people:
            if person.level not in args.levels:
                continue
            stats["above_the_line"] += 1
            if person.email:
                stats["atl_has_email"] += 1
                continue
            if not person.linkedin:
                stats["atl_no_email_no_linkedin"] += 1
                continue
            stats["exported"] += 1
            out_rows.append(
                {
                    "company": person.company,
                    "first_name": person.display_first,
                    "last_name": person.display_last,
                    "full_name": person.name,
                    "title": person.title,
                    "level": person.level,
                    "linkedin_url": person.linkedin,
                    "company_domain": domain,
                    "job_link": job_link,
                    "ats": row.get("ats", "").strip(),
                    "job_titles": (split_lines(row, "job_titles") or [""])[0],
                    "stack": row.get("stack", "").strip(),
                }
            )

    out_rows.sort(key=lambda r: (r["company"].lower(), r["level"], r["last_name"]))
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"wrote {len(out_rows)} rows to {args.out}\n")
    print(f"  committee people           {stats['people']}")
    print(f"  above the line ({'/'.join(args.levels)})  {stats['above_the_line']}")
    print(f"    already have email       {stats['atl_has_email']}")
    print(f"    no email, has LinkedIn   {stats['exported']}  <- exported")
    print(f"    no email, no LinkedIn    {stats['atl_no_email_no_linkedin']}")
    print("\n  match quality:")
    print(
        f"    emails paired to a person {stats['emails_matched']}/{stats['emails_listed']}"
        f" ({stats['emails_unmatched']} unattributed)"
    )
    print(f"    LinkedIn URLs unattributed {stats['linkedins_unmatched']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
