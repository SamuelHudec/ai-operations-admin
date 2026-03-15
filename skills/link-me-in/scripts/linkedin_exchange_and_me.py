#!/usr/bin/env python3
"""
Exchange a LinkedIn OAuth code through the local MCP server and fetch "me".

Usage:
    python3 skills/link-me-in/scripts/linkedin_exchange_and_me.py --code <code> --state <state>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


SERVER_PATH = Path(__file__).with_name("linkedin_mcp_server.py")


def send(proc: subprocess.Popen[bytes], message: dict) -> dict:
    body = json.dumps(message).encode("utf-8")
    proc.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    proc.stdin.flush()

    header = b""
    while b"\r\n\r\n" not in header:
        chunk = proc.stdout.read(1)
        if not chunk:
            raise RuntimeError("MCP server exited before replying.")
        header += chunk

    lines = header.decode("utf-8").split("\r\n")
    length = None
    for line in lines:
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
            break
    if length is None:
        raise RuntimeError("MCP response missing Content-Length.")

    return json.loads(proc.stdout.read(length).decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", required=True)
    parser.add_argument("--state", required=True)
    args = parser.parse_args()

    proc = subprocess.Popen(
        [sys.executable, str(SERVER_PATH)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )

    try:
        send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})

        exchange = send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "linkedin_exchange_code",
                    "arguments": {"code": args.code, "state": args.state},
                },
            },
        )
        print("EXCHANGE_RESULT")
        print(json.dumps(exchange, indent=2))

        me = send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "linkedin_get_me", "arguments": {}},
            },
        )
        print("ME_RESULT")
        print(json.dumps(me, indent=2))
        return 0
    finally:
        proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
