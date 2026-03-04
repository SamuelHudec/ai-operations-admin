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
- `parent_epic`

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
      "parent_epic": "Identity Reliability",
      "touched_dates": ["2026-03-02", "2026-03-03"]
    }
  ]
}
```
