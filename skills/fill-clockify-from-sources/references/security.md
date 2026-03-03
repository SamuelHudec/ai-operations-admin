# Security Reference

This skill needs credentials for Clockify and any enabled source adapter.

Typical credentials:
- ADO PAT or OAuth token
- Calendar provider token (for example Microsoft Graph)
- Clockify API key
- Personal planning settings (`WORK_DAYS`, `DAILY_TARGET_HOURS`, optional `USER_TIMEZONE`)

## Storage policy

- Keep credentials out of git-tracked files.
- Prefer environment variables or OS keychain-based secret tools.
- Redact values in logs and command output.
- For this repo, store local secrets in `skills/fill-clockify-from-sources/.credentials.env`.

## Recommended environment variables

```bash
export ADO_TOKEN="***"
export CALENDAR_TOKEN="***"
export CLOCKIFY_API_KEY="***"
export WORK_DAYS="mon,tue,wed,thu,fri"
export DAILY_TARGET_HOURS="8"
```

Optional non-secret variables:

```bash
export ADO_ORG_URL="https://dev.azure.com/your-org"
export CLOCKIFY_WORKSPACE_ID="workspace-id"
```

## Local development options

1. `.env` file for local-only usage (must be gitignored).
2. `1Password` or system keychain CLI injected at runtime.
3. CI secret store for automated runs.
4. Skill-local `.credentials.env` copied from `.credentials.env.example`.

## Logging and error handling

- Never print raw token values.
- Do not include auth headers in exception traces.
- If auth fails, return a concise message indicating which provider failed and the HTTP status.

## Rotation guidance

- Rotate tokens immediately if exposed.
- Keep separate tokens per environment (dev/staging/prod).
- Prefer least-privilege scopes:
  - ADO: read work items only (plus fields required for effort extraction)
  - Calendar: read events only in selected calendar scope
  - Clockify: read/write time entries in target workspace
