#!/usr/bin/env python3
"""Collect Clockify reported minutes per day and identify missing workdays."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib import parse

from sync_common import (
    build_config,
    clockify_headers,
    http_json,
    load_yaml,
    parse_env_file,
    parse_iso8601_duration_to_minutes,
    parse_iso_datetime,
    require_credentials,
    working_days,
)


def clockify_reported_minutes(
    api_key: str,
    workspace_id: str,
    start: dt.date,
    end: dt.date,
) -> dict[dt.date, int]:
    headers = clockify_headers(api_key)
    me = http_json("GET", "https://api.clockify.me/api/v1/user", headers)
    user_id = me.get("id")
    if not user_id:
        raise RuntimeError("Could not resolve Clockify user id from /api/v1/user")

    base_url = (
        "https://api.clockify.me/api/v1/workspaces/"
        f"{workspace_id}/user/{user_id}/time-entries"
    )
    all_items: list[dict[str, Any]] = []
    page = 1
    page_size = 100
    while True:
        q = parse.urlencode(
            {
                "start": f"{start.isoformat()}T00:00:00.000Z",
                "end": f"{end.isoformat()}T23:59:59.999Z",
                "page": str(page),
                "page-size": str(page_size),
            }
        )
        items = http_json("GET", f"{base_url}?{q}", headers)
        if not isinstance(items, list):
            raise RuntimeError("Unexpected Clockify response for time entries.")
        all_items.extend(items)
        if len(items) < page_size:
            break
        page += 1

    totals: dict[dt.date, int] = defaultdict(int)
    for entry in all_items:
        interval = entry.get("timeInterval") or {}
        start_raw = interval.get("start")
        if not start_raw:
            continue
        duration_raw = interval.get("duration")
        minutes = (
            parse_iso8601_duration_to_minutes(duration_raw)
            if isinstance(duration_raw, str)
            else None
        )
        if minutes is None:
            end_raw = interval.get("end")
            if not end_raw:
                continue
            start_dt = parse_iso_datetime(start_raw)
            end_dt = parse_iso_datetime(end_raw)
            minutes = int((end_dt - start_dt).total_seconds() // 60)
        day = parse_iso_datetime(start_raw).date()
        if minutes > 0:
            totals[day] += minutes
    return totals


def run(args: argparse.Namespace) -> dict[str, Any]:
    requested_end_date = dt.date.fromisoformat(args.to_date)
    today = dt.date.today()
    end_date = min(requested_end_date, today)
    start_date = (
        dt.date.fromisoformat(args.from_date)
        if args.from_date
        else end_date.replace(day=1)
    )
    if start_date > end_date:
        raise ValueError("--from-date cannot be after --to-date.")

    env_values = parse_env_file(Path(args.env_file))
    creds = require_credentials(env_values)
    raw_cfg = load_yaml(Path(args.config))
    cfg = build_config(raw_cfg, creds)

    reported = clockify_reported_minutes(
        api_key=creds["CLOCKIFY_API_KEY"],
        workspace_id=cfg.workspace_id,
        start=start_date,
        end=end_date,
    )
    work_days = working_days(start_date, end_date, cfg)
    target_minutes = int(cfg.daily_target_hours * 60)

    days_to_fill = []
    for day in work_days:
        existing = reported.get(day, 0)
        if existing < target_minutes:
            days_to_fill.append(
                {
                    "date": day.isoformat(),
                    "reported_minutes": existing,
                    "target_minutes": target_minutes,
                    "missing_minutes": target_minutes - existing,
                }
            )

    return {
        "range": {"from": start_date.isoformat(), "to": end_date.isoformat()},
        "requested_to_date": requested_end_date.isoformat(),
        "workday_count": len(work_days),
        "days_to_fill": days_to_fill,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/loggify-me.yaml")
    parser.add_argument(
        "--env-file",
        default="skills/loggify-me/.credentials.env",
    )
    parser.add_argument("--from-date", default=None)
    parser.add_argument("--to-date", default=dt.date.today().isoformat())
    parser.add_argument("--out-json", default=None)
    args = parser.parse_args()

    result = run(args)
    print(f"Range: {result['range']['from']} -> {result['range']['to']}")
    if result["range"]["to"] != result.get("requested_to_date"):
        print(
            f"Requested to-date {result['requested_to_date']} is in the future; "
            f"capped to today {result['range']['to']}."
        )
    print(f"Working days in range: {result['workday_count']}")
    print(f"Days to fill: {len(result['days_to_fill'])}")
    for day in result["days_to_fill"]:
        rep = day["reported_minutes"] // 60
        miss = day["missing_minutes"] // 60
        print(f"- {day['date']}: reported={rep}h missing={miss}h")

    if args.out_json:
        out = Path(args.out_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Saved JSON: {out}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
