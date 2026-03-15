#!/usr/bin/env python3
"""
Minimal LinkedIn MCP server using official LinkedIn OAuth and posting APIs.

Tools:
- linkedin_auth_url
- linkedin_exchange_code
- linkedin_get_me
- linkedin_create_text_post
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


SERVER_NAME = "linkedin-official-mcp"
SERVER_VERSION = "0.1.0"

AUTH_BASE_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
UGC_POSTS_URL = "https://api.linkedin.com/v2/ugcPosts"
IDENTITY_ME_URL = "https://api.linkedin.com/rest/identityMe"

DEFAULT_SCOPES = ["openid", "profile", "email", "w_member_social"]
RESTLI_PROTOCOL_VERSION = "2.0.0"
DEFAULT_LINKEDIN_VERSION = "202510"
DEFAULT_TOKEN_STORE = Path.home() / ".codex" / "memories" / "link-me-in" / "linkedin_tokens.json"
DEFAULT_CREDENTIALS_FILE = Path(__file__).resolve().parent.parent / ".credentials.env"


class McpError(Exception):
    """Expected error surfaced to the MCP client."""


def load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip()


def read_env(name: str, *, required: bool = True) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    if required:
        raise McpError(f"Missing required environment variable: {name}")
    return None


def token_store_path() -> Path:
    configured = os.getenv("LINKEDIN_MCP_TOKEN_STORE")
    return Path(configured).expanduser() if configured else DEFAULT_TOKEN_STORE


def load_store() -> dict[str, Any]:
    path = token_store_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise McpError(f"Token store is not valid JSON: {path}") from exc


def save_store(data: dict[str, Any]) -> None:
    path = token_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def redact_token(token: str | None) -> str | None:
    if not token:
        return None
    if len(token) <= 12:
        return "***"
    return f"{token[:6]}...{token[-4:]}"


def http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    form_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)

    data: bytes | None = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    elif form_body is not None:
        data = urllib.parse.urlencode(form_body).encode("utf-8")
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)

    try:
        with urllib.request.urlopen(request) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {"raw_body": body}
        raise McpError(
            f"LinkedIn API request failed with HTTP {exc.code}: {json.dumps(payload, ensure_ascii=True)}"
        ) from exc
    except urllib.error.URLError as exc:
        raise McpError(f"Network error while calling LinkedIn API: {exc.reason}") from exc


def decode_jwt_payload(id_token: str) -> dict[str, Any]:
    try:
        parts = id_token.split(".")
        if len(parts) != 3:
            raise ValueError("wrong JWT shape")
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8"))
    except Exception as exc:  # pragma: no cover - defensive parsing
        raise McpError("Could not decode id_token payload.") from exc


def build_auth_url(arguments: dict[str, Any]) -> dict[str, Any]:
    client_id = read_env("LINKEDIN_CLIENT_ID")
    redirect_uri = read_env("LINKEDIN_REDIRECT_URI")
    scopes = arguments.get("scopes") or DEFAULT_SCOPES
    if not isinstance(scopes, list) or not all(isinstance(item, str) for item in scopes):
        raise McpError("scopes must be a list of strings.")

    state = arguments.get("state") or secrets.token_urlsafe(24)
    prompt = arguments.get("prompt")

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
    }
    if prompt:
        params["prompt"] = str(prompt)

    store = load_store()
    store["pending_oauth"] = {
        "state": state,
        "scopes": scopes,
        "created_at": int(time.time()),
    }
    save_store(store)

    auth_url = f"{AUTH_BASE_URL}?{urllib.parse.urlencode(params)}"
    return {
        "authorization_url": auth_url,
        "state": state,
        "redirect_uri": redirect_uri,
        "scopes": scopes,
        "next_step": "Open the authorization_url, approve access, and pass the returned code to linkedin_exchange_code.",
    }


def exchange_code(arguments: dict[str, Any]) -> dict[str, Any]:
    client_id = read_env("LINKEDIN_CLIENT_ID")
    client_secret = read_env("LINKEDIN_CLIENT_SECRET")
    redirect_uri = read_env("LINKEDIN_REDIRECT_URI")

    code = arguments.get("code")
    if not code:
        raise McpError("code is required.")

    provided_state = arguments.get("state")
    store = load_store()
    expected_state = ((store.get("pending_oauth") or {}).get("state"))
    if expected_state and provided_state and expected_state != provided_state:
        raise McpError("OAuth state mismatch.")

    token_response = http_json(
        "POST",
        TOKEN_URL,
        form_body={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
    )

    access_token = token_response.get("access_token")
    if not access_token:
        raise McpError("LinkedIn token response did not include access_token.")

    id_token = token_response.get("id_token")
    id_claims = decode_jwt_payload(id_token) if id_token else {}
    expires_in = token_response.get("expires_in")
    expires_at = int(time.time()) + int(expires_in) if expires_in else None

    updated_store = load_store()
    updated_store["token"] = {
        "access_token": access_token,
        "id_token": id_token,
        "expires_in": expires_in,
        "expires_at": expires_at,
        "scope": token_response.get("scope"),
        "token_type": token_response.get("token_type"),
        "obtained_at": int(time.time()),
    }
    updated_store["pending_oauth"] = None
    updated_store["id_claims"] = id_claims
    save_store(updated_store)

    return {
        "stored": True,
        "token_type": token_response.get("token_type"),
        "expires_in": expires_in,
        "expires_at": expires_at,
        "scope": token_response.get("scope"),
        "access_token_preview": redact_token(access_token),
        "person_urn_hint": f"urn:li:person:{id_claims['sub']}" if id_claims.get("sub") else None,
    }


def require_access_token() -> str:
    store = load_store()
    token = ((store.get("token") or {}).get("access_token"))
    if not token:
        raise McpError("No stored access token. Run linkedin_auth_url and linkedin_exchange_code first.")
    return token


def fetch_me(arguments: dict[str, Any]) -> dict[str, Any]:
    del arguments
    access_token = require_access_token()
    userinfo = http_json(
        "GET",
        USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )

    sub = userinfo.get("sub")
    store = load_store()
    store["last_userinfo"] = userinfo
    if sub:
        store["person_urn"] = f"urn:li:person:{sub}"
    save_store(store)

    return {
        "sub": sub,
        "person_urn": f"urn:li:person:{sub}" if sub else None,
        "name": userinfo.get("name"),
        "given_name": userinfo.get("given_name"),
        "family_name": userinfo.get("family_name"),
        "email": userinfo.get("email"),
        "email_verified": userinfo.get("email_verified"),
        "locale": userinfo.get("locale"),
        "picture": userinfo.get("picture"),
        "raw": userinfo,
    }


def create_text_post(arguments: dict[str, Any]) -> dict[str, Any]:
    access_token = require_access_token()
    text = arguments.get("text")
    if not text or not isinstance(text, str):
        raise McpError("text is required and must be a string.")

    visibility = str(arguments.get("visibility") or "PUBLIC")
    author = arguments.get("author")

    store = load_store()
    if not author:
        author = store.get("person_urn")
    if not author:
        id_claims = store.get("id_claims") or {}
        if id_claims.get("sub"):
            author = f"urn:li:person:{id_claims['sub']}"
    if not author:
        userinfo = fetch_me({})
        author = userinfo.get("person_urn")
    if not author:
        raise McpError("Could not determine author person URN. Authenticate again and run linkedin_get_me.")

    payload = {
        "author": author,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": visibility,
        },
    }

    response = http_json(
        "POST",
        UGC_POSTS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Restli-Protocol-Version": RESTLI_PROTOCOL_VERSION,
        },
        json_body=payload,
    )

    return {
        "author": author,
        "visibility": visibility,
        "text_preview": text[:120],
        "response": response,
    }


def get_profile_context(arguments: dict[str, Any]) -> dict[str, Any]:
    access_token = require_access_token()
    linkedin_version = str(arguments.get("linkedin_version") or os.getenv("LINKEDIN_API_VERSION") or DEFAULT_LINKEDIN_VERSION)

    response = http_json(
        "GET",
        IDENTITY_ME_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "LinkedIn-Version": linkedin_version,
        },
    )

    basic = response.get("basicInfo") or {}
    result = {
        "id": response.get("id"),
        "first_name": basic.get("firstName"),
        "last_name": basic.get("lastName"),
        "headline": basic.get("headline"),
        "profile_url": basic.get("profileUrl"),
        "profile_picture": basic.get("profilePicture"),
        "raw": response,
    }
    store = load_store()
    store["last_profile_context"] = result
    save_store(store)
    return result


TOOLS = [
    {
        "name": "linkedin_auth_url",
        "description": "Create a LinkedIn OAuth authorization URL for the official member posting flow.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scopes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "OAuth scopes to request. Defaults to openid, profile, email, w_member_social.",
                },
                "state": {
                    "type": "string",
                    "description": "Optional state override. A secure random state is generated by default.",
                },
                "prompt": {
                    "type": "string",
                    "description": "Optional OAuth prompt parameter.",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "linkedin_exchange_code",
        "description": "Exchange an OAuth authorization code for a LinkedIn access token and store it locally.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "The OAuth authorization code returned by LinkedIn."},
                "state": {"type": "string", "description": "Optional returned OAuth state for validation."},
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    },
    {
        "name": "linkedin_get_me",
        "description": "Fetch the authenticated member's basic profile data using LinkedIn's official userinfo endpoint.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "linkedin_create_text_post",
        "description": "Create a text-only LinkedIn post for the authenticated member using the official UGC posts API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The final text to publish."},
                "visibility": {
                    "type": "string",
                    "description": "Member visibility value. Defaults to PUBLIC.",
                },
                "author": {
                    "type": "string",
                    "description": "Optional explicit author URN like urn:li:person:{id}. Defaults to the authenticated member.",
                },
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "linkedin_get_profile_context",
        "description": "Fetch lightweight official LinkedIn profile context like name and headline to inform post drafting.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "linkedin_version": {
                    "type": "string",
                    "description": "Optional LinkedIn-Version header value. Defaults to LINKEDIN_API_VERSION or 202510.",
                }
            },
            "additionalProperties": False,
        },
    },
]


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handlers = {
        "linkedin_auth_url": build_auth_url,
        "linkedin_exchange_code": exchange_code,
        "linkedin_get_me": fetch_me,
        "linkedin_create_text_post": create_text_post,
        "linkedin_get_profile_context": get_profile_context,
    }
    handler = handlers.get(name)
    if handler is None:
        raise McpError(f"Unknown tool: {name}")
    return handler(arguments)


def make_response(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def make_error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def write_message(payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("utf-8").strip()
        if ":" in decoded:
            name, value = decoded.split(":", 1)
            headers[name.strip().lower()] = value.strip()

    content_length = headers.get("content-length")
    if not content_length:
        raise McpError("Missing Content-Length header.")

    raw_body = sys.stdin.buffer.read(int(content_length))
    return json.loads(raw_body.decode("utf-8"))


def handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    message_id = message.get("id")

    if method == "notifications/initialized":
        return None

    if method == "initialize":
        return make_response(
            message_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )

    if method == "tools/list":
        return make_response(message_id, {"tools": TOOLS})

    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        result = call_tool(name, arguments)
        return make_response(
            message_id,
            {"content": [{"type": "text", "text": json.dumps(result, indent=2, sort_keys=True)}], "isError": False},
        )

    if method == "ping":
        return make_response(message_id, {})

    if message_id is None:
        return None
    return make_error(message_id, -32601, f"Method not found: {method}")


def main() -> int:
    load_dotenv_file(DEFAULT_CREDENTIALS_FILE)
    while True:
        try:
            message = read_message()
            if message is None:
                return 0
            response = handle_message(message)
            if response is not None:
                write_message(response)
        except McpError as exc:
            message_id = None
            try:
                message_id = message.get("id")  # type: ignore[name-defined]
            except Exception:
                pass
            if message_id is not None:
                write_message(make_error(message_id, -32000, str(exc)))
            else:
                print(str(exc), file=sys.stderr)
                return 1
        except Exception as exc:  # pragma: no cover - defensive
            message_id = None
            try:
                message_id = message.get("id")  # type: ignore[name-defined]
            except Exception:
                pass
            error_text = f"Unexpected server error: {exc}"
            if message_id is not None:
                write_message(make_error(message_id, -32603, error_text))
            else:
                print(error_text, file=sys.stderr)
                return 1


if __name__ == "__main__":
    raise SystemExit(main())
