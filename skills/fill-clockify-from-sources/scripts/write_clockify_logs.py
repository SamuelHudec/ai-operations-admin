#!/usr/bin/env python3
"""Write accepted suggested logs to Clockify time entries."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from sync_common import (
    build_config,
    clockify_headers,
    http_json,
    load_yaml,
    parse_env_file,
    require_credentials,
)

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


def _to_utc_iso(local_dt: dt.datetime, tz_name: str) -> str:
    if ZoneInfo is None:
        raise RuntimeError("Python zoneinfo is unavailable. Use Python 3.9+.")
    aware = local_dt.replace(tzinfo=ZoneInfo(tz_name))
    return aware.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _group_by_day(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        day = str(row["date"])
        out.setdefault(day, []).append(row)
    return out


def _validate_rows(rows: list[dict[str, Any]]) -> None:
    required = ("date", "ticket_id", "minutes", "description")
    for idx, row in enumerate(rows):
        missing = [k for k in required if k not in row]
        if missing:
            raise ValueError(f"Row {idx} missing keys: {missing}")
        minutes = int(row["minutes"])
        if minutes <= 0:
            raise ValueError(f"Row {idx} has non-positive minutes: {minutes}")


def _make_payloads(
    rows: list[dict[str, Any]],
    tz_name: str,
    project_id: str,
    task_id: str | None,
    billable: bool,
    workday_start_hour: int,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    by_day = _group_by_day(rows)
    for day, day_rows in sorted(by_day.items()):
        current = dt.datetime.fromisoformat(day).replace(
            hour=workday_start_hour, minute=0, second=0, microsecond=0
        )
        for row in day_rows:
            minutes = int(row["minutes"])
            start_iso = _to_utc_iso(current, tz_name)
            end_iso = _to_utc_iso(current + dt.timedelta(minutes=minutes), tz_name)
            payload: dict[str, Any] = {
                "billable": billable,
                "description": str(row["description"])[:3000],
                "start": start_iso,
                "end": end_iso,
                "projectId": str(row.get("project_id") or project_id),
                "type": "REGULAR",
            }
            row_task_id = row.get("task_id") or task_id
            if row_task_id:
                payload["taskId"] = str(row_task_id)
            if row.get("tag_ids"):
                payload["tagIds"] = list(row["tag_ids"])
            payloads.append(payload)
            current = current + dt.timedelta(minutes=minutes)
    return payloads


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-json", default="reports/suggested-logs.accepted.json")
    parser.add_argument("--fallback-json", default="reports/suggested-logs.json")
    parser.add_argument("--config", default="config/fill-clockify-from-sources.yaml")
    parser.add_argument(
        "--env-file",
        default="skills/fill-clockify-from-sources/.credentials.env",
    )
    parser.add_argument(
        "--workday-start-hour",
        type=int,
        default=9,
        help="Local start hour for placing generated blocks in a day.",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    accepted_path = Path(args.accepted_json)
    source_path = accepted_path if accepted_path.exists() else Path(args.fallback_json)
    if not source_path.exists():
        raise FileNotFoundError(
            f"Accepted plan not found: {accepted_path} (and fallback missing: {args.fallback_json})"
        )
    source = json.loads(source_path.read_text(encoding="utf-8"))
    rows = list(source.get("suggested_logs") or [])
    _validate_rows(rows)

    env_values = parse_env_file(Path(args.env_file))
    creds = require_credentials(env_values)
    raw_cfg = load_yaml(Path(args.config))
    cfg = build_config(raw_cfg, creds)

    clockify_cfg = raw_cfg.get("clockify") or {}
    project_id = str(clockify_cfg.get("default_project_id") or "").strip()
    if not project_id:
        raise ValueError("Missing clockify.default_project_id in config.")
    task_id = clockify_cfg.get("default_task_id")
    billable = bool(clockify_cfg.get("billable", True))

    payloads = _make_payloads(
        rows=rows,
        tz_name=cfg.timezone,
        project_id=project_id,
        task_id=str(task_id) if task_id else None,
        billable=billable,
        workday_start_hour=args.workday_start_hour,
    )

    print(f"Source file: {source_path}")
    print(f"Rows to write: {len(payloads)}")
    print(f"Workspace: {cfg.workspace_id}")
    print(f"Apply mode: {'ON' if args.apply else 'OFF (dry-run)'}")
    print("")
    for i, payload in enumerate(payloads[:20], start=1):
        print(
            f"{i}. {payload['start']} -> {payload['end']} | "
            f"{payload['projectId']} | {payload['description'][:80]}"
        )
    if len(payloads) > 20:
        print(f"... and {len(payloads) - 20} more rows")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to write to Clockify.")
        return 0

    headers = clockify_headers(creds["CLOCKIFY_API_KEY"])
    endpoint = f"https://api.clockify.me/api/v1/workspaces/{cfg.workspace_id}/time-entries"
    created = 0
    errors: list[str] = []
    for idx, payload in enumerate(payloads, start=1):
        try:
            http_json("POST", endpoint, headers, payload)
            created += 1
        except Exception as exc:
            errors.append(f"row {idx}: {exc}")

    print("")
    print(f"Created: {created}")
    print(f"Failed: {len(errors)}")
    for err in errors[:20]:
        print(f"- {err}")
    return 0 if not errors else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
