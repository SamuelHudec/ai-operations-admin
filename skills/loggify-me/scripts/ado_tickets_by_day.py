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

from sync_common import (
    build_config,
    load_yaml,
    parse_env_file,
    require_credentials,
    runtime_date_range,
)


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


def _normalized_type(value: Any) -> str:
    return str(value or "").strip().lower()


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
        "assigned_to": str(
            item.get("assigned_to")
            or item.get("assigned_to_name")
            or item.get("assigned_to_display_name")
            or ""
        ),
        "assigned_to_email": str(
            item.get("assigned_to_email")
            or item.get("assigned_to_unique_name")
            or ""
        ),
        "parent_epic": _normalize_parent_epic(item.get("parent_epic")),
        "parent_epic_id": parent_id,
    }


def _normalized_identity(value: str) -> str:
    return value.strip().lower()


def _is_placeholder_identity(value: str) -> bool:
    normalized = _normalized_identity(value)
    if not normalized:
        return True
    placeholders = {
        "name@company.com",
        "user@example.com",
        "your@email.com",
    }
    return normalized in placeholders or normalized.endswith("@example.com")


def _item_matches_owner(
    item: dict[str, Any],
    owner_email: str,
    owner_name: str,
) -> bool:
    if not owner_email and not owner_name:
        return True

    assigned_email = _normalized_identity(
        str(
            item.get("assigned_to_email")
            or item.get("assigned_to_unique_name")
            or ""
        )
    )
    assigned_name = _normalized_identity(
        str(
            item.get("assigned_to")
            or item.get("assigned_to_name")
            or item.get("assigned_to_display_name")
            or ""
        )
    )

    if not assigned_email and not assigned_name:
        return True
    if owner_email and assigned_email:
        return assigned_email == owner_email
    if owner_name and assigned_name:
        return assigned_name == owner_name
    return False


def run(args: argparse.Namespace) -> dict[str, Any]:
    start_date, end_date, _ = runtime_date_range(
        from_date=args.from_date,
        to_date=args.to_date,
    )

    env_values = parse_env_file(Path(args.env_file))
    creds = require_credentials(env_values)
    raw_cfg = load_yaml(Path(args.config))
    cfg = build_config(raw_cfg, creds)
    owner_email = _normalized_identity(
        str(
            getattr(args, "owner_email", None)
            or env_values.get("ADO_USER_EMAIL")
            or ((raw_cfg.get("user") or {}).get("email") or "")
        )
    )
    owner_name = _normalized_identity(
        str(
            getattr(args, "owner_name", None)
            or env_values.get("ADO_USER_NAME")
            or ""
        )
    )
    if _is_placeholder_identity(owner_email):
        owner_email = ""
    if _is_placeholder_identity(owner_name):
        owner_name = ""
    if getattr(args, "only_assigned_to_me", False) and not (owner_email or owner_name):
        raise ValueError(
            "Assigned-only filtering requires owner identity. "
            "Set ADO_USER_EMAIL or ADO_USER_NAME in skills/loggify-me/.credentials.env, "
            "or pass --owner-email/--owner-name."
        )

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
    excluded_types = {
        _normalized_type(s)
        for s in (getattr(args, "exclude_types", None) or "").split(",")
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
        item_type = _normalized_type(item.get("type") or item.get("work_item_type"))
        if item_type in excluded_types:
            continue
        if getattr(args, "only_assigned_to_me", False) and not _item_matches_owner(
            item,
            owner_email=owner_email,
            owner_name=owner_name,
        ):
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
        "--exclude-types",
        default="",
        help="Comma-separated work item types to exclude from planning.",
    )
    parser.add_argument(
        "--only-days-json",
        default=None,
        help="Optional JSON from clockify_reported_days.py to filter only missing days.",
    )
    parser.add_argument(
        "--only-assigned-to-me",
        action="store_true",
        help="Exclude items assigned to someone else when assignee fields are present in MCP JSON.",
    )
    parser.add_argument(
        "--owner-email",
        default=None,
        help="Owner email used with --only-assigned-to-me. Defaults to ADO_USER_EMAIL or config user.email.",
    )
    parser.add_argument(
        "--owner-name",
        default=None,
        help="Optional owner display name fallback used with --only-assigned-to-me.",
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
