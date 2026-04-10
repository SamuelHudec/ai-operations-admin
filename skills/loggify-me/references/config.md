# Config Reference

This file defines how to map multi-source activity into Clockify entries while respecting personal work schedule constraints.

## Suggested file path

Use a local config file at:
- `config/loggify-me.yaml`

Do not store secrets in this file. Keep only non-sensitive settings.
Personal schedule can also be provided in skill-local `.credentials.env` via:
- `WORK_DAYS` (comma separated)
- `DAILY_TARGET_HOURS`
- `USER_TIMEZONE` (optional)
These values override YAML when present.

Additional runtime overrides that may live in `skills/loggify-me/.credentials.env`:
- `ADO_ORG_URL`
- `ADO_PROJECT`
- `ADO_USER_EMAIL`
- `ADO_USER_NAME`
- `CLOCKIFY_WORKSPACE_ID`
- `CLOCKIFY_DEFAULT_PROJECT_ID`
- `CALENDAR_ICS_URL`
- `CALENDAR_ICS_FILE`

This allows `config/loggify-me.yaml` to remain mostly template-shaped as long as the runtime values are available from env.

## Schema

```yaml
version: 1
profile: default

user:
  email: "name@company.com"
  timezone: "Europe/Prague"
  country_code: "CZ"

schedule:
  workdays: ["mon", "tue", "wed", "thu", "fri"]
  daily_target_hours: 8
  exclude_dates: []
  include_dates: []

sources:
  ado:
    enabled: true
    org_url: "https://dev.azure.com/your-org"
    project: "YourProject"
    query_mode: "assigned_and_touched"
    states_done: ["Done", "Closed", "Resolved"]
    effort_field: "Microsoft.VSTS.Scheduling.CompletedWork"
  calendar:
    enabled: true
    provider: "ics"
    ics_file: "/path/to/calendar.ics"
    # alternatively: ics_url: "https://.../calendar.ics"
    include_event_types: ["meeting", "focus"]
    min_minutes: 15
  holidays:
    enabled: true
    provider: "public_holidays_api"
    region: "CZ"
    behavior: "block_workday" # block_workday | tag_day_only

clockify:
  workspace_id: "workspace-id"
  default_project_id: "project-id-default"
  default_task_id: null
  billable: true
  ceremony_tag_name: "ceremony"

mapping:
  by_source:
    ado:
      by_area_path:
        "Platform\\Identity":
          project_id: "clockify-project-id"
          task_id: "clockify-task-id"
          tags: ["identity", "platform"]
      by_tags:
        "incident":
          tags: ["support"]
    calendar:
      default:
        project_id: "project-id-meetings"
        task_id: null
        tags: ["meeting"]
    holidays:
      default:
        project_id: "project-id-admin"
        task_id: null
        tags: ["holiday"]
  fallback:
    project_id: "project-id-default"
    task_id: null
    tags: ["multi-source-sync"]

allocation:
  mode: "proportional" # proportional | equal | priority
  min_entry_minutes: 15
  round_to_minutes: 60
  overlap_policy: "calendar_precedence" # calendar_precedence | ado_precedence | split

clockify_planning:
  max_block_hours: 6
  min_block_minutes: 60
  max_entries_per_day: 8
  default_fallback_description: "Operational and coordination work."
  ceremony_keywords:
    - "standup"
    - "planning"
    - "review"
    - "retro"
    - "refinement"
```

Note:
- In MCP-first mode, ADO data is loaded from MCP export JSON (`reports/ado-mcp-items.json`).
- `sources.ado.*` is optional metadata and can stay minimal.

## Rule priority

Use the following priority to assign hours per day:
1. Explicit source durations (for example calendar event duration).
2. Explicit effort/time values from ADO updates in date range.
3. Completed work field delta (if configured and available).
4. Weighted split across active ADO tickets that day.
5. If still ambiguous, equal split and mark `warning=low_confidence`.

## Workday filtering

- Include only `schedule.workdays`.
- Exclude any date in `exclude_dates`.
- Always include any date in `include_dates` (useful for weekend overtime).
- If `holidays` source is enabled and `behavior=block_workday`, block holiday dates unless explicitly included.

## Daily cap behavior

Default behavior:
- Sum all candidate entries for a day.
- If total > `daily_target_hours`, scale down proportionally.
- Preserve entry ordering and minimum entry granularity.
- In planning mode, generate suggested entries to cover missing workload up to `daily_target_hours` for configured workdays.

Optional override:
- If override mode is explicitly set, allow totals over daily target and flag in summary.

## Mapping behavior

Mapping precedence:
1. Source-specific mapping under `mapping.by_source.<source_type>`
2. Source-specific default mapping
3. `mapping.fallback`

If fallback is missing or invalid, skip unresolved entries and report them.

## Clockify planning rules

- `max_block_hours`: maximum single Clockify entry size. If a ticket allocation exceeds this, split into multiple entries.
- `min_block_minutes`: smallest planned entry to generate.
- `max_entries_per_day`: safety cap for generated entries per day.
- `default_fallback_description`: used when ticket text has insufficient context.
