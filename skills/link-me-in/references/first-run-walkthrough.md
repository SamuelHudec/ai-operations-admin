# First-Run Walkthrough

## Use this reference when

Use this reference when setting up `link-me-in` for a new user or a fresh LinkedIn app.

## Goal

Get from zero to:
- a working LinkedIn developer app
- local credentials stored safely
- a verified `linkedin_get_me` response
- readiness to publish text posts through the official API
- optional lightweight profile context such as headline for better drafts

## Fast path

1. Create or open a LinkedIn Page.
2. Create a LinkedIn developer app tied to that Page.
3. Enable the required app products.
4. Configure the redirect URL.
5. Fill `skills/link-me-in/.credentials.env`.
6. Generate an auth URL.
7. Approve access in the browser.
8. Exchange the code and verify `linkedin_get_me`.

## Step 1: Create a LinkedIn Page

LinkedIn requires a Page to create a developer app, even for an individual developer.

Use a minimal personal-brand Page if needed:
- page name can be the user's name or solo brand
- organization size can be `Myself Only`
- type can be self-employed or similar if available

The Page is only needed to create the app. Posting can still happen as the authenticated member.

## Step 2: Create the developer app

In the LinkedIn Developer Portal:
- open `My Apps`
- click `Create app`
- select the Page from Step 1

After creation, open the app settings.

## Step 3: Enable required products

Enable both:
- `Share on LinkedIn`
- `Sign in with LinkedIn using OpenID Connect`

Why both are needed:
- `w_member_social` is required for posting
- `openid`, `profile`, and `email` are required for fetching "me" safely through the official userinfo flow

If `openid` is rejected during auth, the OpenID Connect product is not enabled yet.

Optional richer context product:
- `Verified on LinkedIn`

This is useful only if the user wants lightweight profile context like headline to help writing posts.

## Step 4: Configure redirect URL

Use an HTTPS redirect URL that exactly matches the app config.

Recommended quick test value:

```text
https://oauth.pstmn.io/v1/callback
```

Add the same exact value to:
- LinkedIn app `Auth` settings
- `LINKEDIN_REDIRECT_URI` in `skills/link-me-in/.credentials.env`

## Step 5: Fill local credentials

Edit:
- `skills/link-me-in/.credentials.env`

Required values:

```env
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
LINKEDIN_REDIRECT_URI=https://oauth.pstmn.io/v1/callback
```

This file is gitignored by the repo-wide `**/.credentials.env` rule.

## Step 6: Generate auth URL

Use the local MCP server tool:
- `linkedin_auth_url`

It requests these scopes by default:
- `openid`
- `profile`
- `email`
- `w_member_social`

Open the returned `authorization_url` in the browser.

If the user wants lightweight richer profile context, also request:
- `r_profile_basicinfo`

## Step 7: Complete consent

After approval, LinkedIn redirects to the configured callback URL with:
- `code`
- `state`

Example shape:

```text
https://oauth.pstmn.io/v1/callback?code=...&state=...
```

Capture both values.

## Step 8: Exchange code and verify member identity

Use either:
- MCP tool `linkedin_exchange_code`, then `linkedin_get_me`
- or helper script `skills/link-me-in/scripts/linkedin_exchange_and_me.py`

Example:

```bash
python3 skills/link-me-in/scripts/linkedin_exchange_and_me.py --code '...' --state '...'
```

Expected result:
- exchange stores a token locally, unless the code was already used
- `linkedin_get_me` returns the member identity and person URN

## Common issues

### `unauthorized_scope_error` for `openid`

Cause:
- `Sign in with LinkedIn using OpenID Connect` is missing

Fix:
- enable that product in the app

### `authorization code not found`

Cause:
- the code was already exchanged once or expired

Fix:
- generate a new auth URL and complete the consent flow again

### Profile fetch works after code exchange fails

Cause:
- a valid token is already stored locally from a previous successful run

Meaning:
- the server is already authenticated and usable until the token expires

## What success looks like

The setup is complete when:
- `linkedin_get_me` returns the user's name, email, and `person_urn`
- the user can approve a final post draft
- `linkedin_create_text_post` can publish a text post
- optionally, `linkedin_get_profile_context` returns the user's headline for more personalized drafts
