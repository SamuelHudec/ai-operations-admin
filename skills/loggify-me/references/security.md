# Security Reference

This skill needs credentials for Clockify and personal workload settings.
ADO is fetched via MCP; calendar is fetched from an ICS file/URL.

Typical credentials:
- Clockify API key
- Personal planning settings (`WORK_DAYS`, `DAILY_TARGET_HOURS`, optional `USER_TIMEZONE`)

## Storage policy

- Keep credentials out of git-tracked files.
- Prefer environment variables or OS keychain-based secret tools.
- Redact values in logs and command output.
- For this repo, store local secrets in `skills/loggify-me/.credentials.env`.

## Recommended environment variables

```bash
export CLOCKIFY_API_KEY="***"
export CLOCKIFY_DEFAULT_PROJECT_ID="***"
export WORK_DAYS="mon,tue,wed,thu,fri"
export DAILY_TARGET_HOURS="8"
export CALENDAR_ICS_URL="https://.../calendar.ics"
```

Optional non-secret variables:

```bash
export CLOCKIFY_WORKSPACE_ID="workspace-id"
# Alternative to CALENDAR_ICS_URL:
export CALENDAR_ICS_FILE="/absolute/path/to/calendar.ics"
```

## Local development options

1. `.env` file for local-only usage (must be gitignored).
2. `1Password` or system keychain CLI injected at runtime.
3. CI secret store for automated runs.
4. Skill-local `.credentials.env` copied from `.credentials.env.example`.

## Logging and error handling

- Never print raw token values.
- Do not include auth headers in exception traces.
- If calendar feed access fails, return a concise message indicating whether file read or URL download failed.

## Rotation guidance

- Rotate tokens immediately if exposed.
- Keep separate tokens per environment (dev/staging/prod).
- Prefer least-privilege scopes:
  - Clockify: read/write time entries in target workspace
