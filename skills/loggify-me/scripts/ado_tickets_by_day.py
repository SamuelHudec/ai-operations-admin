#!/usr/bin/env python3
"""Collect ADO work items grouped by day from MCP-exported JSON."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from sync_common import build_config, load_yaml, parse_env_file, require_credentials


def _load_mcp_items(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"MCP export file not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        if isinstance(raw.get("work_items"), list):
            items = raw["work_items"]
        elif isinstance(raw.get("items"), list):
            items = raw["items"]
        else:
            raise ValueError("MCP JSON must contain list in root, work_items, or items.")
    else:
        raise ValueError("MCP JSON root must be object or array.")
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            out.append(item)
    return out


def _normalize_touched_dates(item: dict[str, Any]) -> list[str]:
    if isinstance(item.get("touched_dates"), list):
        return [str(d) for d in item["touched_dates"] if d]
    if isinstance(item.get("activity_dates"), list):
        return [str(d) for d in item["activity_dates"] if d]
    if item.get("changed_date"):
        return [str(item["changed_date"])[:10]]
    return []


def _normalize_parent_epic(value: Any) -> str:
    if isinstance(value, dict):
        title = value.get("title")
        wid = value.get("id")
        if title and wid:
            return f"{title} ({wid})"
        if title:
            return str(title)
        if wid:
            return str(wid)
    return str(value or "")


def _compact(item: dict[str, Any]) -> dict[str, Any]:
    parent = item.get("parent_epic")
    parent_id = None
    raw_parent_id = item.get("parent_epic_id")
    if raw_parent_id is None and isinstance(parent, dict):
        raw_parent_id = parent.get("id")
    if raw_parent_id is not None:
        try:
            parent_id = int(raw_parent_id)
        except (TypeError, ValueError):
            parent_id = None
    return {
        "id": int(item.get("id")),
        "title": str(item.get("title") or ""),
        "state": str(item.get("state") or ""),
        "type": str(item.get("type") or item.get("work_item_type") or "WorkItem"),
        "description": str(item.get("description") or ""),
        "comments": list(item.get("comments") or []),
        "tags": str(item.get("tags") or ""),
        "area_path": str(item.get("area_path") or ""),
        "iteration_path": str(item.get("iteration_path") or ""),
        "parent_epic": _normalize_parent_epic(item.get("parent_epic")),
        "parent_epic_id": parent_id,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    end_date = dt.date.fromisoformat(args.to_date)
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
    build_config(raw_cfg, creds)

    day_filter: set[str] | None = None
    only_days = getattr(args, "only_days", None)
    if only_days:
        day_filter = {str(d) for d in only_days}
    elif args.only_days_json:
        data = json.loads(Path(args.only_days_json).read_text(encoding="utf-8"))
        day_filter = {str(day["date"]) for day in data.get("days_to_fill", [])}

    items = _load_mcp_items(Path(args.mcp_json))
    allowed_states = {
        s.strip().lower()
        for s in (args.states or "Active,Closed,Done,Resolved,In Review").split(",")
        if s.strip()
    }
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        if "id" not in item:
            continue
        state = str(item.get("state") or "").strip().lower()
        # Never plan/log items that are still in "New" state.
        if state == "new":
            continue
        if allowed_states and state not in allowed_states:
            continue
        compact = _compact(item)
        touched_dates = _normalize_touched_dates(item)
        unique_days = {
            raw_day[:10]
            for raw_day in touched_dates
            if isinstance(raw_day, str) and len(raw_day) >= 10
        }
        for day in sorted(unique_days):
            try:
                parsed = dt.date.fromisoformat(day)
            except ValueError:
                continue
            if parsed < start_date or parsed > end_date:
                continue
            if day_filter is not None and day not in day_filter:
                continue
            by_day[day].append(compact)

    for day in by_day:
        by_day[day] = sorted(by_day[day], key=lambda x: x["id"])

    return {
        "range": {"from": start_date.isoformat(), "to": end_date.isoformat()},
        "ado_item_count": len(items),
        "days_plan": dict(sorted(by_day.items(), key=lambda kv: kv[0])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/loggify-me.yaml")
    parser.add_argument(
        "--env-file",
        default="skills/loggify-me/.credentials.env",
    )
    parser.add_argument("--mcp-json", default="reports/ado-mcp-items.json")
    parser.add_argument("--from-date", default=None)
    parser.add_argument("--to-date", default=dt.date.today().isoformat())
    parser.add_argument(
        "--states",
        default="Active,Closed,Done,Resolved,In Review",
        help="Comma-separated allowed ADO states (state 'New' is always excluded).",
    )
    parser.add_argument(
        "--only-days-json",
        default=None,
        help="Optional JSON from clockify_reported_days.py to filter only missing days.",
    )
    parser.add_argument("--out-json", default=None)
    args = parser.parse_args()

    result = run(args)
    print(f"Range: {result['range']['from']} -> {result['range']['to']}")
    print(f"MCP ADO items inspected: {result['ado_item_count']}")
    print("Ticket plan by day:")
    if not result["days_plan"]:
        print("- No ADO ticket activity in selected range/filter.")
    else:
        for day, items in result["days_plan"].items():
            print(f"- {day}")
            for it in items:
                parent = f" | epic: {it.get('parent_epic')}" if it.get("parent_epic") else ""
                print(
                    f"  - #{it['id']} [{it['type']}] {it['title']} "
                    f"({it['state']}){parent}"
                )

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
