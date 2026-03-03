# Project Work Item Hierarchy (Mandatory)

Use only these work item types and parent-child relationships.

## Supported Types
- `Epic`
- `User Story`
- `Task`
- `Data Incident`
- `Improvement Epic`
- `Improvement Story`

## Standard Delivery Structure
- `Epic`
  - `User Story`
    - `Task`
  - `Data Incident`

Notes:
- `Epic` represents a business-related delivery or larger initiative.
- `User Story` represents a small valuable increment that can fit in one sprint.
- `Task` is used when a `User Story` is too complex and must be split.
- `Data Incident` is a production issue/defect (not infrastructure issues).

## Improvement Structure
- `Improvement Epic`
  - `Improvement Story`
    - `Task`
  - `Data Incident`

Notes:
- `Improvement Epic` is used for non-business-requested value work (technical debt, refactoring, process improvements).

## Enforcement Rules
- Do not create any type outside the supported list.
- Do not create links outside the allowed parent-child relationships above.
- If a requested structure conflicts with these rules, ask the user to choose a valid parent/type before creating the item.
