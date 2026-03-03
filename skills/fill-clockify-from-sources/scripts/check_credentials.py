#!/usr/bin/env python3
"""Check required credentials for ADO -> Clockify sync."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


REQUIRED_KEYS = (
    "ADO_ORG_URL",
    "ADO_TOKEN",
    "CLOCKIFY_WORKSPACE_ID",
    "CLOCKIFY_API_KEY",
    "WORK_DAYS",
    "DAILY_TARGET_HOURS",
)


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate required credentials for ADO and Clockify."
    )
    parser.add_argument(
        "--env-file",
        default=str(Path(__file__).resolve().parent.parent / ".credentials.env"),
        help="Path to skill-local credentials env file.",
    )
    args = parser.parse_args()

    env_file = Path(args.env_file)
    file_values = parse_env_file(env_file)

    missing: list[str] = []
    print(f"Credential source file: {env_file}")
    for key in REQUIRED_KEYS:
        value = os.environ.get(key) or file_values.get(key)
        status = "SET" if value else "MISSING"
        print(f"{key}: {status}")
        if not value:
            missing.append(key)

    if missing:
        print("\nMissing credentials:")
        for key in missing:
            print(f"- {key}")
        print(
            "\nAdd them to environment variables or "
            f"'{env_file}' (copied from '.credentials.env.example')."
        )
        return 1

    print("\nAll required credentials are available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
