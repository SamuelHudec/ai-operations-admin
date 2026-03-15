# Profile Context

## Use this reference when

Use this reference when a LinkedIn post should reflect the user's real identity, current role, or professional positioning.

## Purpose

This skill is still posting-first. Profile context is used only to improve post quality, not to support full profile editing.

Good uses:
- align post tone with the user's current professional identity
- mention the user's role accurately
- avoid drafting posts that contradict the visible LinkedIn headline

## Safe official context

Start with:
- `linkedin_get_me` for name and basic identity

If available for the user's app and token:
- `linkedin_get_profile_context` for lightweight richer context such as headline

## What to use from profile context

Use profile context to improve:
- how the user is introduced
- the level of technicality in the post
- the framing of accomplishments or lessons
- the match between the post and the user's current headline

## Guardrails

- Do not invent profile fields that were not returned.
- Do not turn missing profile data into assumptions.
- Do not expand this into profile editing.
- Treat headline as helpful context, not as a constraint that blocks good writing.

## Output

If profile context was used, mention it briefly in the summary, for example:
- "Draft aligned to your current LinkedIn headline."
