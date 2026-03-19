# MCP ADO Input Format

`ado_tickets_by_day.py` reads ADO data from a JSON export produced by your MCP workflow.

Default path:
- `reports/ado-mcp-items.json`

Accepted root shapes:
1. Array of work items
2. Object with `work_items` array
3. Object with `items` array

## Required fields per item

- `id` (number)
- at least one day field:
  - `touched_dates` (array of `YYYY-MM-DD`)
  - OR `activity_dates` (array of `YYYY-MM-DD`)
  - OR `changed_date` (ISO date/datetime)

## Optional fields used for planning

- `title`
- `state`
- `type` or `work_item_type`
- `description`
- `comments` (array)
- `tags`
- `area_path`
- `iteration_path`
- `assigned_to`
- `assigned_to_email`
- `parent_epic`
- `parent_epic_id`
- `parent_id`
- `parent_type`
- `child_ids`

## Example

```json
{
  "work_items": [
    {
      "id": 12345,
      "title": "Fix auth timeout",
      "state": "Active",
      "type": "Task",
      "description": "Investigate retry strategy for token refresh.",
      "comments": [{"text": "Validated in staging"}],
      "tags": "auth;backend",
      "area_path": "Platform\\Identity",
      "iteration_path": "Sprint 45",
      "assigned_to": "Samuel EXT Hudec",
      "assigned_to_email": "extHudec@dr-max.global",
      "parent_epic": "Identity Reliability",
      "touched_dates": ["2026-03-02", "2026-03-03"]
    }
  ]
}
```

## Ownership filter

If assignee fields are present, `ado_tickets_by_day.py --only-assigned-to-me` can exclude
items assigned to someone else. This is the recommended mode for personal Clockify fill.

## Personal logging rules

For personal Clockify fill:
- include only items assigned to the user
- include only active items in the selected period
- exclude terminal states such as `Closed`, `Done`, and `Resolved`
- never log epics
- prefer child work items over parent planning items
- exclude user stories/features from personal logging plans unless explicitly requested
