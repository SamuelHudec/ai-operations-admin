---
name: ado-create-a-item
description: Create or update Azure DevOps work items with clean ticket content and correct hierarchy links (Epic/Feature/Story/Task). Use when the user asks to draft fields, list candidate parent epics, create an item, or link an existing item under a parent. Exclude MCP setup and focus on the delivery workflow.
---

# ADO Create A Item

Use this workflow to create ADO items reliably and avoid orphan tickets.
Use [references/work-item-hierarchy.md](references/work-item-hierarchy.md) as the strict source of truth for allowed work item types and parent-child relationships in this project.

## Fixed Defaults (Always Apply)
- Project: `Dynamic Pricing`
- Area Path: `Dynamic Pricing\Dynamic Pricing Solution Team`
- Iteration Path: `Dynamic Pricing\DP Solution\FLO_Backlog`
- Assigned To: ticket author (creator) by default

Only change these if the user explicitly asks for an override.
Before any create/update, always ask whether the user wants to use the latest sprint iteration instead of backlog:
- Sprint pattern: `Dynamic Pricing\DP Solution\20xx_CWxx`
- Determine the latest sprint at the beginning of the workflow before drafting fields.
- If user says `yes`, set Iteration Path to the latest existing sprint matching that pattern.
- If user says `no`, keep default `Dynamic Pricing\DP Solution\FLO_Backlog`.

## Required Inputs
- Work item type (only supported types from `references/work-item-hierarchy.md`)
- Title
- State and Priority
- Parent item ID (if hierarchy is required)
- Iteration choice confirmation (`latest sprint` vs `FLO_Backlog`)
- Explicit user confirmation that all mandatory fields are correct before create/update

If parent is not provided, list active epics first and ask user to pick one before creation.

## Type-Based Field Rules
Ask only the fields required for the selected type:

- `User Story` and `Improvement Story`
  - Require `Description`
  - Require `Acceptance Criteria`
- `Task`
  - Require `Description`
  - Do not require `Acceptance Criteria`
- `Data Incident`
  - Require `Description`
  - Require `Resolution`
  - Do not require `Acceptance Criteria` unless user explicitly asks
- `Epic` and `Improvement Epic`
  - Require `Description`
  - `Acceptance Criteria` optional

## Standard Workflow
1. Load and follow `references/work-item-hierarchy.md`. Never use unsupported work item types.
2. At the beginning, list iterations and detect the latest sprint matching `Dynamic Pricing\DP Solution\20xx_CWxx` (for example `Dynamic Pricing\DP Solution\2026_CW10`). Keep this exact value for later confirmation.
3. List active epics first and ask which epic should be the parent of the new work item.
4. If the requested work item type is `Task`, ask an optional follow-up: whether to place the task under a specific `User Story` instead of directly under the epic.
5. Ask for mandatory fields based on the selected work item type and draft the ticket content for user review:
- Work item type
- Title
- State
- Priority
- Iteration choice: ask `Do you want to add this to the latest sprint (<detected sprint path>)?`
- Description (all supported types)
- Acceptance Criteria (mandatory only for `User Story` and `Improvement Story`)
- Resolution (mandatory for `Data Incident`)
6. Show the drafted ticket and allow corrections before creating anything.
7. Mandatory confirmation gate: stop and ask the user to confirm that all mandatory fields are correct and aligned with their work. Do not continue until the user gives explicit approval.
8. Echo the final confirmed field values (type, title, state, priority, parent, iteration, and required text fields) and ask for a final `yes` before any write action.
9. Validate hierarchy before create:
- `User Story` and `Data Incident` must have a parent (`Epic` or `Improvement Epic`).
- `Task` must have a parent (`User Story` or `Improvement Story`).
- `Improvement Story` must have parent `Improvement Epic`.
- Do not create non-root items without parent.
10. Create the ticket with the agreed fields.
11. Add parent link according to the hierarchy rules.
12. Verify parent link exists on the created item.
13. Return a concise confirmation with work item ID and direct edit path.

## Output Format
Return:
1. Created/updated work item ID
2. Direct edit path/URL
3. Parent link status (`added`, `unchanged`, or `not requested`)
4. Any field mismatch detected after verification

## Content Templates
Use these defaults when the user asks for suggestions.

### Description
```markdown
## Goal
<one clear outcome statement>

## Scope
- <scope item 1>
- <scope item 2>
- <scope item 3>
```

### Acceptance Criteria
```markdown
1. <verifiable outcome 1>
2. <verifiable outcome 2>
3. <verifiable outcome 3>
4. <verifiable outcome 4>
```

## Guardrails
- Never proceed with sensitive secrets pasted in chat; ask user to rotate/revoke if exposed.
- Never assume parent hierarchy; confirm or list valid parent candidates first.
- Never leave non-root items orphaned. Every `User Story`, `Improvement Story`, `Task`, and `Data Incident` must belong to the hierarchy.
- Never create unsupported item types or unsupported parent-child links.
- Never create or update any work item without explicit user approval that all mandatory fields are correct.
- Always set project/area/iteration to fixed defaults unless user explicitly overrides.
- Default `Assigned To` to author/creator for simple ticket creation.
- Keep updates concise and actionable.
