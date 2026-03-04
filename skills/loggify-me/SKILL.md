---
name: loggify-me
description: Use this skill when the user wants to fill Clockify time entries from multiple sources such as ADO, meetings/calendar events, and public holidays using personal schedule rules and stored credentials.
---

# Fill Clockify From Sources

## Execution mode

- Run the workflow commands directly as the agent.
- Do not ask the user to manually run terminal commands for normal flow.
- Ask user only for required inputs, approvals, or corrections (for example missing credentials, plan confirmation, apply confirmation).

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
- [references/mcp-ado-format.md](references/mcp-ado-format.md): required MCP export format for ADO input
- [references/mcp-ado-workflow.md](references/mcp-ado-workflow.md): MCP-native ADO fetch steps
- [assets/config.template.yaml](assets/config.template.yaml): starter config template

Phase 1 scope:
- Use ADO (MCP), calendar (ICS), and Clockify.
- Check credentials with:
  - `python skills/loggify-me/scripts/check_credentials.py`
- Keep local credentials in `skills/loggify-me/.credentials.env` (not committed).
- In `.credentials.env`, fill both API keys and personal workload fields:
  - `CLOCKIFY_DEFAULT_PROJECT_ID=...`
  - `WORK_DAYS=mon,tue,wed,thu,fri`
  - `DAILY_TARGET_HOURS=8`
  - optional `USER_TIMEZONE=...`
  - calendar source (set one):
    - `CALENDAR_ICS_URL=https://.../calendar.ics`
    - or `CALENDAR_ICS_FILE=/absolute/path/to/calendar.ics`
- Find missing Clockify days with:
  - `python skills/loggify-me/scripts/clockify_reported_days.py --from-date YYYY-MM-DD --to-date YYYY-MM-DD --out-json reports/clockify-days.json`
  - Future dates are always ignored; effective end date is capped to today.
- Collect calendar events from Apple Calendar ICS export/subscription and export them into:
  - `reports/calendar-events.json`
  - `python skills/loggify-me/scripts/fetch_calendar_via_ics.py --from-date YYYY-MM-DD --to-date YYYY-MM-DD --out-json reports/calendar-events.json`
  - optional explicit override: `--ics-file /path/to/calendar.ics` or `--ics-url 'https://.../calendar.ics'`
- Collect ADO work items via MCP tools (same style as `ADO-create-a-item`) and export them into:
  - `reports/ado-mcp-items.json`
  - Follow exact fetch sequence in `references/mcp-ado-workflow.md`
  - `New` state work items are ignored for planning/logging.
- Pull ADO tickets by day from MCP export with:
  - `python skills/loggify-me/scripts/ado_tickets_by_day.py --mcp-json reports/ado-mcp-items.json --from-date YYYY-MM-DD --to-date YYYY-MM-DD --only-days-json reports/clockify-days.json --out-json reports/ado-days.json`
- Build combined day-fill plan with:
  - `python skills/loggify-me/scripts/plan_ado_clockify_fill.py --ado-mcp-json reports/ado-mcp-items.json --from-date YYYY-MM-DD --to-date YYYY-MM-DD --out-json reports/plan.json`
- Review and request corrections with:
  - `python skills/loggify-me/scripts/review_plan.py --plan-json reports/plan.json --corrections-json reports/plan.corrections.json`
- Suggest Clockify log blocks from rules and review corrections with:
  - `python skills/loggify-me/scripts/suggest_clockify_logs.py --plan-json reports/plan.json --calendar-json reports/calendar-events.json --config config/loggify-me.yaml --out-json reports/suggested-logs.json --corrections-json reports/suggested-logs.corrections.json`
  - Rule target: fill Monday-Friday workload to configured daily hours using ticket-based blocks between 1h and 6h.
  - Calendar meetings are logged first at their real meeting time and tagged with configured Clockify ceremony tag.
  - Remaining daily workload is filled by ADO ticket blocks around meeting slots.
  - Future days are never suggested for logging.
- Write accepted suggestion table to Clockify:
  - `python skills/loggify-me/scripts/write_clockify_logs.py --accepted-json reports/suggested-logs.accepted.json`
  - Add `--apply` to actually create entries (without it, script runs dry-run).
  - After `--apply`, local `reports/` files are cleaned automatically by default.
  - Use `--no-cleanup-reports` only if you need to keep artifacts for debugging.
  - Writer skips any future-dated rows as a final safety guard.
  - Also accepts direct Clockify-style JSON array (`project_id`, `description`, `start`, `end`).
  - Writer enforces Clockify tag containing only parent epic number as `<parent_epic_id>`.
  - Preferred: keep default project id in `.credentials.env` (`CLOCKIFY_DEFAULT_PROJECT_ID`) instead of tracked config.

Outlook Web publish flow (for new users):
1. Open Outlook on web.
2. Open `Settings` -> `Calendar` -> `Shared calendars` -> `Publish a calendar`.
3. Choose calendar and detail level, then publish.
4. Copy the ICS link and store it as `CALENDAR_ICS_URL` in `.credentials.env`.
5. If `Publish a calendar` is missing, tenant admin disabled this feature.

## Workflow

1. Validate config and credentials
- Confirm config file exists and has valid timezone, workday rules, and project mappings.
- Confirm required credentials are present in environment variables or secure local secret store.
- Fail fast with a clear message if anything is missing.

2. Find days that need logging
- Read existing Clockify entries in date range.
- Apply workday and daily-hour rules.
- Build target day list to fill.

3. Collect source activity for target days
- Load enabled adapters (`calendar`, `ado`, later `holidays`).
- Query calendar and ADO for the same date range, then focus planning only on target days.
- For ADO in this phase, use MCP tools directly (no direct ADO REST calls).
- Normalize outputs into candidate entries with: date, duration candidate, source id, source type, title, tags, metadata.

4. Apply personal schedule rules
- Keep only configured working days.
- Cap total daily hours to configured `daily_target_hours` unless override mode is requested.
- If ADO data has less detail than needed, distribute hours across eligible tickets using rule priority from `references/config.md`.
- If multiple sources overlap (for example meeting plus ticket work), apply overlap policy from config.

5. Map to Clockify dimensions
- Resolve Clockify workspace, project, task, and tags from per-source mapping rules.
- Build final upsert payloads with external reference fields for idempotency:
  - `source_type`
  - `source_entry_id`
  - `sync_source=multi`

6. Upsert to Clockify
- For each target day, fetch existing Clockify entries created by this sync source (`sync_source=multi`).
- Update matching entries when payload changed.
- Create missing entries.
- Do not duplicate entries for the same source entry and day.

7. Report results
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
3. Do not output "run this command" instructions for normal flow; execute steps directly and report results.
