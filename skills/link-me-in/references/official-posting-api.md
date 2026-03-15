# Official LinkedIn Posting API

## Use this reference when

Use this reference when a request involves live LinkedIn posting through the official API.

## Supported safe scope

This skill supports the official member-posting path only:
- member-auth OAuth flow
- `w_member_social` permission
- post creation on behalf of the authenticated member

Do not assume official support for automated profile editing in this skill.

## Required app setup

Before live posting, confirm:
- a LinkedIn developer app exists
- the app has the `Share on LinkedIn` product enabled
- the OAuth scopes include `w_member_social`
- the app can authenticate the member through 3-legged OAuth

Helpful companion permissions:
- `openid`
- `profile`
- `email`

These help identify the authenticated member in a supported way, but posting still requires `w_member_social`.

## Required API details

- Authorization URL base: `https://www.linkedin.com/oauth/v2/authorization`
- Token URL: `https://www.linkedin.com/oauth/v2/accessToken`
- Posting endpoint: `POST https://api.linkedin.com/v2/ugcPosts`
- Required header: `X-Restli-Protocol-Version: 2.0.0`

## Required post fields

For a basic member post, prepare:
- `author`: member person URN such as `urn:li:person:{id}`
- `lifecycleState`: `PUBLISHED`
- `specificContent.com.linkedin.ugc.ShareContent.shareCommentary.text`
- `specificContent.com.linkedin.ugc.ShareContent.shareMediaCategory`
- `visibility.com.linkedin.ugc.MemberNetworkVisibility`

Common values:
- text-only post: `shareMediaCategory` = `NONE`
- article link post: `shareMediaCategory` = `ARTICLE`
- image post: `shareMediaCategory` = `IMAGE`
- public visibility: `PUBLIC`

## Safe execution workflow

1. Draft and approve the final post text.
2. Confirm the app has `w_member_social`.
3. Authenticate the member through OAuth and obtain an access token.
4. Retrieve or confirm the member person URN for the `author` field.
5. Build the `ugcPosts` payload.
6. Ask for final publish confirmation.
7. Submit the request and report the exact API result.

## Failure handling

- If app permissions are missing, stop and report the missing product or scope.
- If the member URN is unavailable, stop and report that the author URN is required before posting.
- If the API responds with an authorization or permission error, do not guess; surface the status code and message.
- If official live posting is blocked, fall back to returning final post text for manual paste.
