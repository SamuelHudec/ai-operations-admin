---
name: loggify-me
description: Use this skill when the user wants to fill or backfill Clockify time entries from ADO work items and calendar meetings using the configured personal schedule, stored credentials, and Clockify mappings.
---

# Loggify Me

Use this skill to generate and optionally write Clockify entries for a date range.

Typical requests:
- "Fill Clockify for this week from ADO and meetings."
- "Backfill last month."
- "Sync missing days only."

## Execution mode

- Run the workflow directly as the agent.
- Do not ask the user to run commands in the normal flow.
- Ask only for missing credentials, missing source data, plan corrections, or final apply confirmation.

## What to load

Read only what is needed:
- [references/config.md](references/config.md) for config and mapping behavior
- [references/security.md](references/security.md) for credential handling
- [references/process.md](references/process.md) for workflow boundaries
- [references/mcp-ado-workflow.md](references/mcp-ado-workflow.md) when fetching ADO items through MCP
- [references/mcp-ado-format.md](references/mcp-ado-format.md) when validating or normalizing MCP ADO export
- [assets/config.template.yaml](assets/config.template.yaml) when creating or repairing config

## Required inputs

Before syncing, confirm:
- date range
- `config/loggify-me.yaml` exists or can be created
- `skills/loggify-me/.credentials.env` has required Clockify and calendar values
- ADO activity can be exported to `reports/ado-mcp-items.json`

Important local values:
- `CLOCKIFY_DEFAULT_PROJECT_ID`
- `WORK_DAYS`
- `DAILY_TARGET_HOURS`
- optional `USER_TIMEZONE`
- one calendar source:
  - `CALENDAR_ICS_URL`
  - or `CALENDAR_ICS_FILE`

## Workflow

1. Validate credentials and config.
2. Find missing Clockify days in the requested range.
3. Fetch calendar events for that range.
4. Fetch ADO work items through MCP and save normalized export.
5. Build the fill plan for missing days only.
6. Suggest Clockify log rows from meetings plus ADO work.
7. Always list the suggested logs in the response for inspection before any apply step.
8. Run a dry-run writer and show the final table.
9. Ask for confirmation before `--apply`.

## Current behavior

- Scope is ADO via MCP, calendar via ICS, and Clockify.
- Future dates are ignored.
- Personal logging plans must include only items assigned to the user.
- Personal logging plans must include only active items in the requested period. Do not log closed, done, or resolved items.
- Prefer child work items for ADO logging. Never log epics. Exclude user stories and other parent planning items from personal logging plans unless the user explicitly asks to include them.
- Daily logged time must reach the configured target for each missing workday whenever there is at least one eligible ADO child work item in the requested range.
- If a missing day has no same-day eligible ADO touch, reuse the eligible ticket pool from the requested range before leaving the day underfilled.
- Calendar meetings are logged first at their real time.
- Remaining time is filled with ADO blocks around meetings.
- Repeated logs for the same ADO ticket should prefer larger available blocks when possible.
- ADO log description should use only the work item ID, for example `205015`.
- ADO log rows must carry `parent_epic_id`.
- Clockify tag for ADO rows should be the parent epic ID only.
- Always dry-run before apply.
- Always list the suggested logs explicitly so the user can inspect them before apply.

## Main scripts

- `scripts/check_credentials.py`
- `scripts/clockify_reported_days.py`
- `scripts/fetch_calendar_via_ics.py`
- `scripts/plan_ado_clockify_fill.py`
- `scripts/suggest_clockify_logs.py`
- `scripts/write_clockify_logs.py`

Use the scripts instead of re-implementing the workflow.

## Guardrails

- Never print full secrets.
- Never store credentials in tracked files.
- Never write future-dated entries.
- If an ADO row is missing `parent_epic_id`, stop and report it.
- If data is missing or ambiguous, report the issue instead of guessing.

## Output contract

When using this skill, return:
1. A short execution summary.
2. Any unresolved items needing user action.
3. The suggested logs listed explicitly for inspection.
4. The dry-run or apply result, including visible Clockify tag output for ADO rows.
