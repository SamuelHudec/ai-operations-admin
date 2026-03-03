#!/usr/bin/env python3
"""Collect ADO work items and group them by touched day."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from sync_common import (
    ado_headers,
    build_config,
    http_json,
    load_yaml,
    parse_env_file,
    parse_iso_datetime,
    require_credentials,
)


def fetch_ado_work_item_ids(
    org_url: str,
    project: str,
    token: str,
    start: dt.date,
    end: dt.date,
) -> list[int]:
    wiql_url = f"{org_url}/{project}/_apis/wit/wiql?api-version=7.1"
    query = (
        "SELECT [System.Id] FROM WorkItems "
        f"WHERE [System.TeamProject] = '{project}' "
        "AND [System.AssignedTo] = @Me "
        f"AND [System.ChangedDate] >= '{start.isoformat()}T00:00:00Z' "
        f"AND [System.ChangedDate] <= '{end.isoformat()}T23:59:59Z' "
        "ORDER BY [System.ChangedDate] DESC"
    )
    data = http_json("POST", wiql_url, ado_headers(token), {"query": query})
    items = data.get("workItems") or []
    return [int(it["id"]) for it in items if "id" in it]


def fetch_ado_work_items(org_url: str, token: str, ids: list[int]) -> list[dict[str, Any]]:
    if not ids:
        return []
    fields = [
        "System.Id",
        "System.Title",
        "System.State",
        "System.WorkItemType",
        "System.Tags",
        "System.Description",
        "System.ChangedDate",
        "System.AreaPath",
        "System.IterationPath",
    ]
    url = f"{org_url}/_apis/wit/workitemsbatch?api-version=7.1"
    payload = {"ids": ids, "fields": fields, "$expand": "Relations"}
    data = http_json("POST", url, ado_headers(token), payload)
    return data.get("value") or []


def extract_parent_ids(work_items: list[dict[str, Any]]) -> list[int]:
    ids: set[int] = set()
    for item in work_items:
        for rel in item.get("relations") or []:
            if rel.get("rel") != "System.LinkTypes.Hierarchy-Reverse":
                continue
            url = str(rel.get("url") or "")
            tail = url.rstrip("/").rsplit("/", 1)[-1]
            if tail.isdigit():
                ids.add(int(tail))
    return sorted(ids)


def fetch_comments(org_url: str, token: str, work_item_id: int) -> list[dict[str, Any]]:
    url = (
        f"{org_url}/_apis/wit/workItems/{work_item_id}/comments"
        "?api-version=7.1-preview.3"
    )
    data = http_json("GET", url, ado_headers(token))
    return data.get("comments") or []


def fetch_updates(org_url: str, token: str, work_item_id: int) -> list[dict[str, Any]]:
    url = (
        f"{org_url}/_apis/wit/workItems/{work_item_id}/updates"
        "?api-version=7.1-preview.3"
    )
    data = http_json("GET", url, ado_headers(token))
    return data.get("value") or []


def tickets_by_day(
    org_url: str,
    token: str,
    work_items: list[dict[str, Any]],
    days: set[dt.date] | None = None,
) -> dict[dt.date, list[dict[str, Any]]]:
    plan: dict[dt.date, list[dict[str, Any]]] = defaultdict(list)
    for item in work_items:
        wid = int(item.get("id"))
        fields = item.get("fields") or {}
        updates = fetch_updates(org_url, token, wid)
        touched: set[dt.date] = set()
        for update in updates:
            rev = update.get("revisedDate")
            if not rev:
                continue
            day = parse_iso_datetime(str(rev)).date()
            if days is None or day in days:
                touched.add(day)
        if not touched:
            changed = fields.get("System.ChangedDate")
            if changed:
                day = parse_iso_datetime(str(changed)).date()
                if days is None or day in days:
                    touched.add(day)

        compact = {
            "id": wid,
            "title": fields.get("System.Title", ""),
            "state": fields.get("System.State", ""),
            "type": fields.get("System.WorkItemType", ""),
            "description": fields.get("System.Description", ""),
            "comments": fetch_comments(org_url, token, wid),
            "tags": fields.get("System.Tags", ""),
            "area_path": fields.get("System.AreaPath", ""),
            "iteration_path": fields.get("System.IterationPath", ""),
        }
        for day in sorted(touched):
            plan[day].append(compact)
    return plan


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
    cfg = build_config(raw_cfg, creds)

    day_filter: set[dt.date] | None = None
    only_days = getattr(args, "only_days", None)
    if only_days:
        day_filter = {dt.date.fromisoformat(d) for d in only_days}
    elif args.only_days_json:
        data = json.loads(Path(args.only_days_json).read_text(encoding="utf-8"))
        day_filter = {
            dt.date.fromisoformat(day["date"]) for day in data.get("days_to_fill", [])
        }

    ado_ids = fetch_ado_work_item_ids(
        org_url=cfg.ado_org_url,
        project=cfg.ado_project,
        token=creds["ADO_TOKEN"],
        start=start_date,
        end=end_date,
    )[: args.max_items]

    work_items = fetch_ado_work_items(cfg.ado_org_url, creds["ADO_TOKEN"], ado_ids)
    parent_ids = extract_parent_ids(work_items)
    parent_items = fetch_ado_work_items(cfg.ado_org_url, creds["ADO_TOKEN"], parent_ids)
    parent_by_id = {
        int(it.get("id")): (it.get("fields") or {}).get("System.Title", "")
        for it in parent_items
    }

    by_day = tickets_by_day(
        org_url=cfg.ado_org_url,
        token=creds["ADO_TOKEN"],
        work_items=work_items,
        days=day_filter,
    )

    for item in work_items:
        wid = int(item.get("id"))
        parent_title = ""
        for rel in item.get("relations") or []:
            if rel.get("rel") == "System.LinkTypes.Hierarchy-Reverse":
                tail = str(rel.get("url", "")).rstrip("/").rsplit("/", 1)[-1]
                if tail.isdigit():
                    parent_title = parent_by_id.get(int(tail), "")
                    break
        for day_items in by_day.values():
            for entry in day_items:
                if entry["id"] == wid:
                    entry["parent_epic"] = parent_title

    return {
        "range": {"from": start_date.isoformat(), "to": end_date.isoformat()},
        "ado_item_count": len(work_items),
        "days_plan": {
            day.isoformat(): sorted(items, key=lambda x: x["id"])
            for day, items in sorted(by_day.items(), key=lambda kv: kv[0])
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/fill-clockify-from-sources.yaml")
    parser.add_argument(
        "--env-file",
        default="skills/fill-clockify-from-sources/.credentials.env",
    )
    parser.add_argument("--from-date", default=None)
    parser.add_argument("--to-date", default=dt.date.today().isoformat())
    parser.add_argument("--max-items", type=int, default=50)
    parser.add_argument(
        "--only-days-json",
        default=None,
        help="Optional JSON from clockify_reported_days.py to filter only missing days.",
    )
    parser.add_argument("--out-json", default=None)
    args = parser.parse_args()

    result = run(args)
    print(f"Range: {result['range']['from']} -> {result['range']['to']}")
    print(f"ADO items inspected: {result['ado_item_count']}")
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
