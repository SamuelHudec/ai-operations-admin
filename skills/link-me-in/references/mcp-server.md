# LinkedIn MCP Server

## Use this reference when

Use this reference when setting up or running the local LinkedIn MCP server for official auth and posting.

## Server location

- Script: `skills/link-me-in/scripts/linkedin_mcp_server.py`
- Transport: stdio
- Implementation: pure Python, no extra dependencies required

## Supported tools

- `linkedin_auth_url`
- `linkedin_exchange_code`
- `linkedin_get_me`
- `linkedin_get_profile_context`
- `linkedin_create_text_post`

## Required environment variables

- `LINKEDIN_CLIENT_ID`
- `LINKEDIN_CLIENT_SECRET`
- `LINKEDIN_REDIRECT_URI`

Optional:
- `LINKEDIN_MCP_TOKEN_STORE`

Default token store:
- `~/.codex/memories/link-me-in/linkedin_tokens.json`

## Local credentials file

For this repo, keep local LinkedIn secrets in:
- `skills/link-me-in/.credentials.env`

Safe template:
- `skills/link-me-in/.credentials.env.example`

Load the file into your shell before starting the MCP server:

```bash
set -a
source skills/link-me-in/.credentials.env
set +a
python3 skills/link-me-in/scripts/linkedin_mcp_server.py
```

## Expected safe workflow

1. Start the MCP server from the script.
2. Call `linkedin_auth_url`.
3. Open the returned authorization URL in a browser.
4. Complete LinkedIn consent and copy the returned `code`.
5. Call `linkedin_exchange_code` with the code.
6. Call `linkedin_get_me` to verify the authenticated member and cache the person URN.
7. Optionally call `linkedin_get_profile_context` to capture lightweight posting context such as headline.
8. Call `linkedin_create_text_post` only after the final post text is approved.

## Example MCP client command

Example stdio server command:

```bash
python3 skills/link-me-in/scripts/linkedin_mcp_server.py
```

## Notes

- The server currently creates text-only posts through `ugcPosts`.
- The server fetches "me" data from LinkedIn's official `userinfo` endpoint.
- The server can optionally fetch lightweight profile context such as headline for better post drafting.
- The server does not edit the live profile.
- The server stores OAuth tokens outside tracked repo files by default.
