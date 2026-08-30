# Attio provisioning — Cotera RevOps custom fields

Applied 2026-08-30 against Attio workspace `cotera`
(`workspace_id: bed06138-1ac3-497d-804d-58d42890b438`).

24 attributes created, 23 select options created, 0 pre-existing attributes
touched. Re-running `python3 attio/provision_attio_fields.py` is a no-op and
reports all 24 as existing — the script is idempotent and safe to re-run.

Object slugs confirmed live: **`companies`** and **`people`**.

## Companies (13 created)

| Slug | Attio type | Requested |
|---|---|---|
| `current_thesis` | text | Long text |
| `current_thesis_summary` | text | Short text |
| `current_thesis_version_id` | text | Short text |
| `current_thesis_updated_at` | timestamp | Date/time |
| `latest_signal_type` | text | Select or short text |
| `latest_signal_summary` | text | Long text |
| `latest_signal_source_url` | text | URL |
| `account_score` | number | Number |
| `account_score_reason` | text | Long text |
| `enrichment_status` | select (5 options) | Select |
| `next_best_action` | select (8 options) | Select or short text |
| `play_key` | text | Short text |
| `cotera_relationship_id` | text | Short text |

## People (11 created)

| Slug | Attio type | Requested |
|---|---|---|
| `person_current_thesis` | text | Long text |
| `persona_angle` | text | Long text |
| `three_questions_to_pressure_test` | text | Long text |
| `call_context` | text | Long text |
| `context_confidence` | select (4 options) | Select |
| `needs_review` | checkbox | Checkbox |
| `needs_review_reason` | text | Long text |
| `latest_signal_summary` | text | Long text |
| `recommended_play` | text | Short text |
| `manual_touch_status` | select (6 options) | Select |
| `cotera_relationship_id` | text | Short text |

## Deviations from the requested schema

Attio exposes a single `text` type — there is no short/long distinction and no
URL type for custom attributes. Short text, Long text and URL therefore all
map to `text` (17 of 24 fields). Consequences worth knowing:

- `latest_signal_source_url` gets no URL validation and no clickable-link
  rendering. Attio's `domain` type holds bare domains, not full source URLs,
  so it is not a substitute.
- No length enforcement anywhere, so the 500–700 character budget on
  `call_context` must be enforced by Cotera before write.

Where the spec allowed "Select or short text": `next_best_action` is a
`select` (closed action set, filterable); `latest_signal_type` is `text`, on
the assumption the signal taxonomy keeps growing. Changing the latter to a
select later requires a new attribute — Attio cannot retype in place.

## Notes for whoever runs this next

- The script reads `ATTIO_API_KEY`. In the environment this was applied from
  the credential was present under a different name (`Attio_API_Key`) and had
  to be mapped at invocation. Confirm the variable name in whatever runner
  executes this on a schedule.
- The provisioning token carries only `object_configuration:read-write`. That
  is enough to create, update and archive attributes, but it CANNOT read or
  write record values — syncing actual data needs a token with record scopes.
- Attio has no delete for attributes; removal is archival via
  `PATCH /v2/objects/{object}/attributes/{slug}` with `is_archived: true`.
