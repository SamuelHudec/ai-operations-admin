---
name: link-me-in
description: Create, revise, and publish LinkedIn posts using LinkedIn's official member-posting API. Optionally use lightweight official LinkedIn profile context such as the user's name and headline to improve post tone and positioning. Use when the user wants help writing a LinkedIn post, reviewing post tone and claims, preparing a safe official-API posting workflow, fetching enough LinkedIn profile context to personalize a post, or publishing a final approved LinkedIn text post.
---

# Link Me In

Use this skill to prepare LinkedIn post content, optionally ground it in the user's official LinkedIn identity and headline, review it for clarity and credibility, and publish final approved text posts through LinkedIn's official API.

Typical requests:
- "Write a LinkedIn post about my new role."
- "Turn these notes into a LinkedIn post and publish it through the official API."

## Execution mode

- Run the workflow directly as the agent.
- Draft first, then publish or apply only after explicit confirmation.
- Prefer LinkedIn's official posting API for live posting.
- Ask only for missing facts, missing source material, or confirmation before any live change.

## What to load

Read only what is needed:
- [references/posting.md](references/posting.md) for post drafting, review, and publish workflow
- [references/official-posting-api.md](references/official-posting-api.md) when preparing or validating official API posting
- [references/profile-context.md](references/profile-context.md) when fetching lightweight official profile context to improve post drafting
- [references/mcp-server.md](references/mcp-server.md) when configuring or operating the local LinkedIn MCP server
- [references/first-run-walkthrough.md](references/first-run-walkthrough.md) for initial app setup, OAuth troubleshooting, and first successful posting setup

## Workflow decision

- If the request is about a feed post, use `references/posting.md` and `references/official-posting-api.md`.
- If profile context would improve the draft, use `references/profile-context.md`.
- If the request is not about LinkedIn posting, do not use this skill.

## Core workflow

1. Identify the target action: draft, revise, or publish.
2. Gather the minimum required facts, links, and tone goals.
3. If useful, fetch lightweight profile context such as name and headline.
4. Draft the content in a LinkedIn-appropriate voice.
5. Check factual claims, names, dates, links, and tone.
6. For posting, verify the official API prerequisites before any live action.
7. Show the exact final post text.
8. Ask for explicit confirmation before any live LinkedIn action.
9. If live posting is unavailable, return ready-to-paste post text plus concise manual steps.

## Guardrails

- Never fabricate achievements, metrics, employers, education, or endorsements.
- Never claim a LinkedIn action succeeded unless the tool output confirms it.
- Never use unofficial LinkedIn APIs or browser automation when the task can be completed through the official posting API or manual paste.
- Prefer concise, specific language over hype.
- Flag statements that may require proof, approval, or legal review.
- Preserve the user's voice unless asked to reposition it.

## Local resources

- Use `scripts/linkedin_mcp_server.py` for official OAuth, member verification, lightweight profile context fetch, and text post creation.
- Read `references/mcp-server.md` before wiring the server into an MCP client or setting environment variables.

## Output contract

When using this skill, return:
1. A short summary of the intended LinkedIn change.
2. The final draft post text.
3. Any factual items that still need confirmation.
4. Whether the action was completed live or prepared for manual paste.
