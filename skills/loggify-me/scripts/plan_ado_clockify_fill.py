#!/usr/bin/env python3
"""Combine Clockify missing days + ADO tickets into one fill plan."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from ado_tickets_by_day import run as run_ado
from clockify_reported_days import run as run_clockify


def _merge_days_with_fallback(
    days_to_fill: list[dict[str, object]],
    days_plan: dict[str, list[dict[str, object]]],
) -> tuple[dict[str, list[dict[str, object]]], list[str]]:
    fallback_pool: list[dict[str, object]] = []
    seen_ids: set[int] = set()
    for day in sorted(days_plan):
        for item in days_plan[day]:
            item_id = int(item["id"])
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            fallback_pool.append(item)

    merged = dict(days_plan)
    fallback_days: list[str] = []
    if not fallback_pool:
        return merged, fallback_days

    for day in days_to_fill:
        day_value = str(day["date"])
        if merged.get(day_value):
            continue
        merged[day_value] = [dict(item) for item in fallback_pool]
        fallback_days.append(day_value)
    return dict(sorted(merged.items(), key=lambda kv: kv[0])), fallback_days


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/loggify-me.yaml")
    parser.add_argument(
        "--env-file",
        default="skills/loggify-me/.credentials.env",
    )
    parser.add_argument("--from-date", default=None)
    parser.add_argument("--to-date", default=dt.date.today().isoformat())
    parser.add_argument(
        "--ado-mcp-json",
        default="reports/ado-mcp-items.json",
        help="MCP-exported ADO work item JSON input.",
    )
    parser.add_argument(
        "--owner-email",
        default=None,
        help="Owner email used for assigned-only filtering.",
    )
    parser.add_argument(
        "--owner-name",
        default=None,
        help="Optional owner display name fallback used for assigned-only filtering.",
    )
    parser.add_argument(
        "--include-team-items",
        dest="only_assigned_to_me",
        action="store_false",
        help="Include items assigned to others. By default, only items assigned to you are planned.",
    )
    parser.add_argument(
        "--states",
        default="Active,Review,In Review",
        help="Comma-separated ADO states allowed for personal logging plans.",
    )
    parser.add_argument(
        "--exclude-types",
        default="Epic,Feature,User Story",
        help="Comma-separated work item types excluded from personal logging plans.",
    )
    parser.add_argument("--out-json", default=None)
    parser.set_defaults(only_assigned_to_me=True)
    args = parser.parse_args()

    clockify_result = run_clockify(
        SimpleNamespace(
            config=args.config,
            env_file=args.env_file,
            from_date=args.from_date,
            to_date=args.to_date,
            out_json=None,
        )
    )

    ado_result = run_ado(
        SimpleNamespace(
            config=args.config,
            env_file=args.env_file,
            from_date=args.from_date,
            to_date=args.to_date,
            mcp_json=args.ado_mcp_json,
            states=args.states,
            exclude_types=args.exclude_types,
            only_days_json=None,
            only_days=[d["date"] for d in clockify_result["days_to_fill"]],
            only_assigned_to_me=args.only_assigned_to_me,
            owner_email=args.owner_email,
            owner_name=args.owner_name,
            out_json=None,
        )
    )

    merged_days_plan, fallback_days = _merge_days_with_fallback(
        clockify_result["days_to_fill"],
        ado_result["days_plan"],
    )

    output = {
        "range": clockify_result["range"],
        "workday_count": clockify_result["workday_count"],
        "days_to_fill": clockify_result["days_to_fill"],
        "days_plan": merged_days_plan,
        "ado_item_count": ado_result["ado_item_count"],
        "fallback_days_using_range_ticket_pool": fallback_days,
    }

    print(f"Range: {output['range']['from']} -> {output['range']['to']}")
    print(f"Working days in range: {output['workday_count']}")
    print(f"Days to fill: {len(output['days_to_fill'])}")
    print("")
    if not output["days_to_fill"]:
        print("No missing days based on daily target.")
    else:
        print("Days to fill:")
        for day in output["days_to_fill"]:
            rep = day["reported_minutes"] // 60
            miss = day["missing_minutes"] // 60
            print(f"- {day['date']}: reported={rep}h missing={miss}h")

    print("")
    if fallback_days:
        print(
            "Fallback ticket pool applied to days without same-day ADO touches: "
            + ", ".join(fallback_days)
        )
        print("")
    print("Ticket plan by day:")
    if not output["days_plan"]:
        print("- No ADO ticket activity mapped to missing days.")
    else:
        for day, items in output["days_plan"].items():
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
        out.write_text(json.dumps(output, indent=2), encoding="utf-8")
        print("")
        print(f"Full report saved to: {out}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
