# MCP ADO Fetch Workflow

Use this workflow to fetch ADO activity exactly via MCP tools (no direct REST calls in this skill).

## Goal

Collect work items touched by the user in a date range and store a normalized snapshot at:
- `reports/ado-mcp-items.json`

## MCP tool flow

1. Call `wit_my_work_items`
- Parameters:
  - `type: "myactivity"`
  - `includeCompleted: true`
  - project identifier as used in your ADO environment
- Extract returned work item IDs.

2. Call `wit_get_work_items_batch_by_ids`
- Input: IDs from step 1
- Request fields at minimum:
  - `System.Id`
  - `System.Title`
  - `System.State`
  - `System.WorkItemType`
  - `System.ChangedDate`
  - `System.Tags`
  - `System.Description`
  - `System.AreaPath`
  - `System.IterationPath`

3. (Optional but recommended) enrich with comments/updates
- Fetch comments and update history per work item via available MCP tools.
- Build activity dates (`touched_dates`) from change/update timestamps in target date range.

4. Normalize and save
- Save JSON to `reports/ado-mcp-items.json`.
- Use format defined in `references/mcp-ado-format.md`.

## Required normalized fields per item

- `id`
- `title`
- `state`
- `type`
- one of:
  - `touched_dates` (recommended), or
  - `activity_dates`, or
  - `changed_date`

## Notes

- Keep this step MCP-native; do not use direct ADO REST calls from this skill workflow.
- Downstream scripts (`ado_tickets_by_day.py`, `plan_ado_clockify_fill.py`) consume the saved snapshot.
