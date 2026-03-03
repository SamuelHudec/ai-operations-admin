#!/usr/bin/env python3
"""Review generated plan and capture correction requests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def print_plan(plan: dict[str, Any]) -> None:
    rng = plan.get("range", {})
    print(f"Range: {rng.get('from')} -> {rng.get('to')}")
    print(f"Days to fill: {len(plan.get('days_to_fill', []))}")
    print("")
    for day in plan.get("days_to_fill", []):
        print(
            f"- {day['date']}: reported={day['reported_minutes']//60}h "
            f"missing={day['missing_minutes']//60}h"
        )
    print("")
    print("Tickets by day:")
    for date, items in (plan.get("days_plan") or {}).items():
        print(f"- {date}")
        for it in items:
            print(f"  - #{it['id']} [{it['type']}] {it['title']} ({it['state']})")


def parse_csv(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", default="reports/plan.json")
    parser.add_argument("--corrections-json", default="reports/plan.corrections.json")
    parser.add_argument("--non-interactive", action="store_true")
    args = parser.parse_args()

    plan_path = Path(args.plan_json)
    if not plan_path.exists():
        raise FileNotFoundError(f"Plan file not found: {plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    print_plan(plan)

    if args.non_interactive:
        return 0

    ok = input("\nIs this plan ready to apply? [y/N]: ").strip().lower()
    if ok in {"y", "yes"}:
        print("Plan accepted.")
        return 0

    exclude_days = parse_csv(
        input("Dates to exclude (comma-separated YYYY-MM-DD, optional): ").strip()
    )
    remove_pairs = parse_csv(
        input(
            "Tickets to remove (comma-separated DATE:ID, optional; "
            "example 2026-03-02:12345): "
        ).strip()
    )
    notes = input("Correction notes (optional): ").strip()

    remove_tickets_by_day: dict[str, list[int]] = {}
    for pair in remove_pairs:
        if ":" not in pair:
            continue
        day, raw_id = pair.split(":", 1)
        raw_id = raw_id.strip()
        if raw_id.isdigit():
            remove_tickets_by_day.setdefault(day.strip(), []).append(int(raw_id))

    corrections = {
        "status": "needs_corrections",
        "exclude_days": exclude_days,
        "remove_tickets_by_day": remove_tickets_by_day,
        "notes": notes,
    }
    out = Path(args.corrections_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(corrections, indent=2), encoding="utf-8")
    print(f"Saved corrections: {out}")
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
