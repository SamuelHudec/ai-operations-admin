---
name: pgrana-zapisy
description: >
  Use this skill when you need to generate and send post-meeting notes for
  PG Rana nonprofit organization. Trigger on any mention of "zápis", "schůze",
  "zápis ze schůze", "meeting notes", "post-meeting", or when the user says
  something like "napiš zápis", "odešli zápis", or "vygeneruj zápis ze schůze".
  This skill automatically fetches the latest tl;dv transcript, cross-references
  it with recent Trello changes on the vybor-rana board, generates structured
  Czech meeting minutes, and sends them via Gmail from vybor@pgkr.cz.
  Use this skill even if the user does not mention PG Rana explicitly — if
  they ask for meeting notes or zápis in this project context, this is the skill.
---

# PG Rana – Zápis ze schůze

Generates and sends post-meeting notes for the PG Rana board (výbor).

## Execution mode

- Run the workflow directly as the agent.
- Do not ask the user to run commands.
- Ask only when credentials are missing or when requesting send confirmation.
- Always show the draft to the user before sending.

## Required MCPs

| MCP | Purpose | Repo |
|-----|---------|------|
| tldv | Fetch meeting transcript | https://github.com/tldv-public/tldv-mcp-server |
| Trello | Fetch board card changes | https://github.com/delorenj/mcp-server-trello |
| Google Workspace | Send email via Gmail | https://github.com/taylorwilsdon/google_workspace_mcp |

Credentials are in `skills/pgrana-zapisy/.credentials.env`.

## Fixed configuration

- **Trello board ID:** `mqQag6De` (vybor-rana)
- **Send from:** vybor@pgkr.cz
- **Send to:** vybor@pgkr.cz
- **Language:** Czech throughout

## Workflow

1. **Fetch transcript** — use the tldv MCP to retrieve the most recent meeting recording/transcript. Extract: date, attendees, all discussed topics.

2. **Fetch Trello changes** — use the Trello MCP to list all cards on board `mqQag6De` that were created, moved, or updated since the previous meeting. Group cards by their current list/column name.

3. **Cross-reference** — match transcript topics to Trello card activity. For each Trello list that had activity or was mentioned in the transcript, create a section in the notes. Ignore lists with no activity and no transcript mention.

4. **Generate draft** — produce the full Czech notes using the template below.

5. **Show draft** — present the complete draft to the user for review. Wait for confirmation or corrections.

6. **Send email** — once confirmed, use the Google Workspace MCP to send the email from vybor@pgkr.cz to vybor@pgkr.cz.

## Output template

```
Předmět: Zápis ze schůze výboru PG Rana – [DD. MM. YYYY]

Účastní se: [jména z přepisu, oddělená čárkou]
Omluveni: [pokud zmíněno v přepisu, jinak vynechat]
Místo / forma: [z přepisu, např. online / sídlo oddílu]

---

[Pro každý Trello sloupec s aktivitou nebo zmínkou v přepisu:]

## [Název sloupce]

- [Shrnutí projednávaného bodu nebo změny karty]
- [další bod]

---

## Různé

[Ostatní body z přepisu, které nespadají do žádného Trello sloupce]

---

## Úkoly

| Úkol | Zodpovědný | Termín |
|------|-----------|--------|
| [z přepisu nebo Trello] | [jméno] | [datum nebo „neurčeno"] |

---

Zápis vygenerován automaticky ze záznamu schůze.
```

## Guardrails

- Never send without explicit user confirmation ("odešli", "ano", "send", or similar).
- Never print or log credential values.
- If tldv returns no recent meeting, report it and stop — do not fabricate content.
- If Trello MCP is unavailable, generate notes from transcript only and note the gap.
- If the transcript is in a language other than Czech, translate the output to Czech.
