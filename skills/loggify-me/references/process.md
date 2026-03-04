# Process Sketch (Phase 1: ADO + Clockify)

## Goal

Create a reliable plan of what days need filling in Clockify, then list ADO tickets worked on for those days.

## End-to-end flow

1. Credential check
- Verify `CLOCKIFY_WORKSPACE_ID`, `CLOCKIFY_API_KEY`, `WORK_DAYS`, `DAILY_TARGET_HOURS`.
- Fail early with clear missing keys list.

2. Clockify coverage scan
- Read existing Clockify time entries for the date range.
- Apply personal working-day rules from config.
- Cap effective end date to today (never plan future days).
- Compute which workdays are below target hours.

3. Calendar activity collection
- Use Apple Calendar ICS export/subscription to get meetings in range.
- Preferred source: Outlook Web published ICS URL stored in `CALENDAR_ICS_URL`.
- If publish option is unavailable in Outlook Web, export `.ics` manually and use `CALENDAR_ICS_FILE`.
- Export normalized events to `reports/calendar-events.json`.
- Identify ceremony meetings using configured keywords.

4. ADO activity collection
- Use MCP ADO tools to collect assigned/touched work items in the date range.
- Export normalized result to `reports/ado-mcp-items.json`.
- Enrich each ticket with description, comments, and parent epic.
- Group tickets by touched day.
- Exclude items with state `New`.
- This step follows the same MCP-first behavior as `ADO-create-a-item` (no direct ADO API calls).

5. Plan build
- Keep only missing Clockify days.
- Attach grouped ADO tickets and ceremony meetings to those days.
- Output readable plan and JSON artifact.

6. Review and corrections
- Show generated plan to user.
- Ask if corrections are needed.
- Save corrections to a separate file.
- Only continue to apply step after plan is accepted.

7. Rule-based log suggestion
- Apply planning rules (for example max single block 6h).
- Insert calendar meetings first using actual meeting start/end slots.
- Enforce block sizes between 1h and 6h.
- Fill remaining target minutes with ADO blocks around occupied meeting slots.
- Generate suggested Clockify log blocks in table and JSON.
- Create one-sentence descriptions per ticket/day.
- If same ticket spans multiple days, generate varied descriptions by day.
- Ask for corrections and store them.
- Carry `parent_epic_id` into each suggested row for downstream Clockify tagging.

8. Later (next phases)
- Allocation logic for exact minutes per ticket.
- Write accepted suggestions to Clockify with API payload validation.
- Add calendar and holiday adapters.
- Ensure each written Clockify entry has tag `<parent_epic_id>` (epic number only).

## Script boundaries

- `check_credentials.py`: validate required secrets.
- `clockify_reported_days.py`: days-to-fill from Clockify + schedule config.
- `ado_tickets_by_day.py`: ticket details grouped by day from MCP-exported ADO JSON.
- `plan_ado_clockify_fill.py`: combine Clockify output + MCP ADO output into one plan.
- `fetch_calendar_via_ics.py`: fetch calendar JSON from ICS file or URL.
- `review_plan.py`: interactive review and correction capture.
- `suggest_clockify_logs.py`: enforce block rules and propose final log rows.
- `write_clockify_logs.py`: dry-run/apply writer for accepted suggestion table.
