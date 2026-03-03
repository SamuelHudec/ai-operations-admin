---
name: fill-clockify-from-sources
description: Use this skill when the user wants to fill Clockify time entries from multiple sources such as ADO, meetings/calendar events, and public holidays using personal schedule rules and stored credentials.
---

# Fill Clockify From Sources

## When to use this skill

Use this skill when the task is to create or update Clockify time entries from one or more configured sources for a date range.

Examples:
- "Fill Clockify from my ADO tickets and meetings for this week."
- "Sync yesterday from all configured sources."
- "Backfill last month based on ADO, calendar, and holiday rules."

## Inputs required

Before running sync, ensure these are available:
- Date range (for example: `2026-03-01` to `2026-03-07`)
- Person identity mappings per source and Clockify
- Personal schedule config (work days and daily target hours)
- Credentials for enabled source adapters and Clockify

Read these files as needed:
- [references/config.md](references/config.md): config schema and mapping rules
- [references/security.md](references/security.md): API key storage and handling
- [references/process.md](references/process.md): process sketch and script boundaries
- [assets/config.template.yaml](assets/config.template.yaml): starter config template

Phase 1 scope:
- Use ADO and Clockify only.
- Check credentials with:
  - `python skills/fill-clockify-from-sources/scripts/check_credentials.py`
- Keep local credentials in `skills/fill-clockify-from-sources/.credentials.env` (not committed).
- In `.credentials.env`, fill both API keys and personal workload fields:
  - `WORK_DAYS=mon,tue,wed,thu,fri`
  - `DAILY_TARGET_HOURS=8`
  - optional `USER_TIMEZONE=...`
- Find missing Clockify days with:
  - `python skills/fill-clockify-from-sources/scripts/clockify_reported_days.py --from-date YYYY-MM-DD --to-date YYYY-MM-DD --out-json reports/clockify-days.json`
- Pull ADO tickets by day with:
  - `python skills/fill-clockify-from-sources/scripts/ado_tickets_by_day.py --from-date YYYY-MM-DD --to-date YYYY-MM-DD --only-days-json reports/clockify-days.json --out-json reports/ado-days.json`
- Build combined day-fill plan with:
  - `python skills/fill-clockify-from-sources/scripts/plan_ado_clockify_fill.py --from-date YYYY-MM-DD --to-date YYYY-MM-DD --out-json reports/plan.json`
- Review and request corrections with:
  - `python skills/fill-clockify-from-sources/scripts/review_plan.py --plan-json reports/plan.json --corrections-json reports/plan.corrections.json`
- Suggest Clockify log blocks from rules and review corrections with:
  - `python skills/fill-clockify-from-sources/scripts/suggest_clockify_logs.py --plan-json reports/plan.json --config config/fill-clockify-from-sources.yaml --out-json reports/suggested-logs.json --corrections-json reports/suggested-logs.corrections.json`
  - Rule target: fill Monday-Friday workload to configured daily hours using ticket-based blocks between 1h and 6h.
- Write accepted suggestion table to Clockify:
  - `python skills/fill-clockify-from-sources/scripts/write_clockify_logs.py --accepted-json reports/suggested-logs.accepted.json`
  - Add `--apply` to actually create entries (without it, script runs dry-run).

## Workflow

1. Validate config and credentials
- Confirm config file exists and has valid timezone, workday rules, and project mappings.
- Confirm required credentials are present in environment variables or secure local secret store.
- Fail fast with a clear message if anything is missing.

2. Collect source activity
- Load all enabled source adapters from config (`ado`, `calendar`, `holidays`, and others later).
- Query each source in the date range for the configured user/location.
- Normalize all outputs into internal candidate entries with: date, duration candidate, source id, source type, title, tags, metadata.

3. Apply personal schedule rules
- Keep only configured working days.
- Cap total daily hours to configured `daily_target_hours` unless override mode is requested.
- If ADO data has less detail than needed, distribute hours across eligible tickets using rule priority from `references/config.md`.
- If multiple sources overlap (for example meeting plus ticket work), apply overlap policy from config.

4. Map to Clockify dimensions
- Resolve Clockify workspace, project, task, and tags from per-source mapping rules.
- Build final upsert payloads with external reference fields for idempotency:
  - `source_type`
  - `source_entry_id`
  - `sync_source=multi`

5. Upsert to Clockify
- For each target day, fetch existing Clockify entries created by this sync source (`sync_source=multi`).
- Update matching entries when payload changed.
- Create missing entries.
- Do not duplicate entries for the same source entry and day.

6. Report results
- Return summary:
  - date range
  - entries created/updated/skipped
  - unresolved mappings
  - validation warnings
- Show a compact per-day table with total planned vs synced hours.

## Operating modes

- `dry_run=true` (default for first pass): show what would change without writing to Clockify.
- `apply=true`: execute writes after validation passes.

## Guardrails

- Never print full API keys in logs or output.
- Never write credentials into tracked files.
- If mapping cannot be resolved, skip entry and report it instead of guessing.
- If a day exceeds allowed hours, either cap and report, or require explicit override.
- If two sources conflict for the same time window, apply configured precedence and report conflict count.

## Output contract

When this skill is used, return:
1. A short execution summary.
2. A list of unresolved items requiring user action.
3. Exact next command to run for apply mode if current run was dry-run.
