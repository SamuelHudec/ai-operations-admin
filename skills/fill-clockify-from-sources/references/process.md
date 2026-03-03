# Process Sketch (Phase 1: ADO + Clockify)

## Goal

Create a reliable plan of what days need filling in Clockify, then list ADO tickets worked on for those days.

## End-to-end flow

1. Credential check
- Verify `ADO_ORG_URL`, `ADO_TOKEN`, `CLOCKIFY_WORKSPACE_ID`, `CLOCKIFY_API_KEY`.
- Fail early with clear missing keys list.

2. Clockify coverage scan
- Read existing Clockify time entries for the date range.
- Apply personal working-day rules from config.
- Compute which workdays are below target hours.

3. ADO activity collection
- Query assigned/touched work items in the date range.
- Enrich each ticket with description, comments, and parent epic.
- Group tickets by touched day.

4. Plan build
- Keep only missing Clockify days.
- Attach grouped ADO tickets to those days.
- Output readable plan and JSON artifact.

5. Review and corrections
- Show generated plan to user.
- Ask if corrections are needed.
- Save corrections to a separate file.
- Only continue to apply step after plan is accepted.

6. Rule-based log suggestion
- Apply planning rules (for example max single block 6h).
- Enforce block sizes between 1h and 6h.
- Generate suggested Clockify log blocks in table and JSON.
- Create one-sentence descriptions per ticket/day.
- If same ticket spans multiple days, generate varied descriptions by day.
- Ask for corrections and store them.

7. Later (next phases)
- Allocation logic for exact minutes per ticket.
- Write accepted suggestions to Clockify with API payload validation.
- Add calendar and holiday adapters.

## Script boundaries

- `check_credentials.py`: validate required secrets.
- `clockify_reported_days.py`: days-to-fill from Clockify + schedule config.
- `ado_tickets_by_day.py`: ticket details grouped by day from ADO.
- `plan_ado_clockify_fill.py`: combine both outputs into one plan.
- `review_plan.py`: interactive review and correction capture.
- `suggest_clockify_logs.py`: enforce block rules and propose final log rows.
- `write_clockify_logs.py`: dry-run/apply writer for accepted suggestion table.
