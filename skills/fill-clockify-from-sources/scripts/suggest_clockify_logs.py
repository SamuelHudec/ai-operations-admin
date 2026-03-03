#!/usr/bin/env python3
"""Generate suggested Clockify log blocks from plan.json and planning rules."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from sync_common import load_yaml


def _strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_context(ticket: dict[str, Any]) -> str:
    candidates = [
        _strip_html(str(ticket.get("description") or "")),
        _strip_html(
            " ".join(
                _strip_html(str(c.get("text") or "")) for c in (ticket.get("comments") or [])
            )
        ),
        str(ticket.get("tags") or "").replace(";", ","),
        str(ticket.get("area_path") or "").split("\\")[-1],
    ]
    for item in candidates:
        if item:
            words = item.split()
            return " ".join(words[:8])
    return ""


def _sentence_for_ticket(ticket: dict[str, Any], occurrence: int, fallback_text: str) -> str:
    title = str(ticket.get("title") or f"ADO #{ticket.get('id')}")
    context = _extract_context(ticket) or fallback_text
    variants = [
        "Reviewed and clarified",
        "Implemented and progressed",
        "Validated and refined",
        "Coordinated and resolved follow-up on",
        "Finalized and documented",
    ]
    verb = variants[(occurrence - 1) % len(variants)]
    return f"{verb} {title}, focusing on {context}."


def _split_blocks(total_minutes: int, max_block_minutes: int, min_block_minutes: int) -> list[int]:
    blocks: list[int] = []
    remaining = total_minutes
    while remaining > 0:
        chunk = min(remaining, max_block_minutes)
        remainder = remaining - chunk
        if 0 < remainder < min_block_minutes:
            shift = min_block_minutes - remainder
            if chunk - shift >= min_block_minutes:
                chunk -= shift
        if chunk < min_block_minutes and blocks and blocks[-1] + chunk <= max_block_minutes:
            blocks[-1] += chunk
            remaining = 0
            break
        blocks.append(chunk)
        remaining -= chunk
    if blocks and blocks[-1] < min_block_minutes and len(blocks) > 1:
        deficit = min_block_minutes - blocks[-1]
        if blocks[-2] - deficit >= min_block_minutes:
            blocks[-2] -= deficit
            blocks[-1] += deficit
    return blocks


def _print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No suggested logs.")
        return
    header = ["Date", "Ticket", "Hours", "Description"]
    widths = [10, 36, 7, 90]
    print(
        f"{header[0]:<{widths[0]}}  {header[1]:<{widths[1]}}  "
        f"{header[2]:<{widths[2]}}  {header[3]}"
    )
    print("-" * (sum(widths) + 6))
    for row in rows:
        ticket = f"#{row['ticket_id']} {row['title']}"[: widths[1]]
        hours = f"{row['minutes'] / 60:.2f}"
        print(
            f"{row['date']:<{widths[0]}}  {ticket:<{widths[1]}}  "
            f"{hours:<{widths[2]}}  {row['description'][:widths[3]]}"
        )


def _parse_csv(text: str) -> list[str]:
    return [x.strip() for x in text.split(",") if x.strip()]


def generate_suggestions(
    plan: dict[str, Any],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    planning = (cfg.get("clockify_planning") or {}) if isinstance(cfg, dict) else {}
    allocation = (cfg.get("allocation") or {}) if isinstance(cfg, dict) else {}

    max_block_hours = float(planning.get("max_block_hours") or 6)
    max_block_minutes = max(60, int(max_block_hours * 60))
    min_block_minutes = max(60, int(planning.get("min_block_minutes") or 60))
    if max_block_minutes < min_block_minutes:
        max_block_minutes = min_block_minutes
    max_entries_per_day = int(planning.get("max_entries_per_day") or 8)
    fallback_text = str(
        planning.get("default_fallback_description") or "Operational and coordination work."
    )
    round_to = int(allocation.get("round_to_minutes") or 60)

    missing_by_day = {d["date"]: int(d["missing_minutes"]) for d in plan.get("days_to_fill", [])}
    days_plan = plan.get("days_plan") or {}
    ticket_pool: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for items in days_plan.values():
        for ticket in items:
            tid = int(ticket["id"])
            if tid not in seen_ids:
                ticket_pool.append(ticket)
                seen_ids.add(tid)
    occurrences: dict[int, int] = {}
    suggested_rows: list[dict[str, Any]] = []
    unresolved_days: list[str] = []

    for day in sorted(missing_by_day.keys()):
        tickets = list(days_plan.get(day) or ticket_pool)
        day_missing = missing_by_day[day]
        if day_missing <= 0:
            continue
        if not tickets:
            unresolved_days.append(day)
            continue

        rounded_total = max(
            min_block_minutes,
            int(math.ceil(day_missing / round_to) * round_to),
        )
        blocks = _split_blocks(rounded_total, max_block_minutes, min_block_minutes)
        if len(blocks) > max_entries_per_day:
            blocks = blocks[:max_entries_per_day]
            extra = rounded_total - sum(blocks)
            if extra > 0:
                blocks[-1] = min(max_block_minutes, blocks[-1] + extra)

        day_rows: list[dict[str, Any]] = []
        for i, block_minutes in enumerate(blocks):
            ticket = tickets[i % len(tickets)]
            tid = int(ticket["id"])
            occurrences[tid] = occurrences.get(tid, 0) + 1
            day_rows.append(
                {
                    "date": day,
                    "ticket_id": tid,
                    "title": str(ticket.get("title") or ""),
                    "minutes": block_minutes,
                    "description": _sentence_for_ticket(
                        ticket, occurrences[tid], fallback_text
                    ),
                }
            )
        suggested_rows.extend(day_rows)

    return {
        "range": plan.get("range") or {},
        "source_plan_file": "reports/plan.json",
        "rules_used": {
            "max_block_hours": max_block_hours,
            "min_block_minutes": min_block_minutes,
            "max_entries_per_day": max_entries_per_day,
            "round_to_minutes": round_to,
        },
        "suggested_logs": suggested_rows,
        "unresolved_days_without_tickets": unresolved_days,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", default="reports/plan.json")
    parser.add_argument("--config", default="config/fill-clockify-from-sources.yaml")
    parser.add_argument("--out-json", default="reports/suggested-logs.json")
    parser.add_argument(
        "--corrections-json",
        default="reports/suggested-logs.corrections.json",
    )
    parser.add_argument("--non-interactive", action="store_true")
    args = parser.parse_args()

    plan_path = Path(args.plan_json)
    if not plan_path.exists():
        raise FileNotFoundError(f"Plan file not found: {plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    cfg = load_yaml(Path(args.config))

    result = generate_suggestions(plan, cfg)
    rows = result["suggested_logs"]
    print(f"Range: {result['range'].get('from')} -> {result['range'].get('to')}")
    print(f"Suggested log blocks: {len(rows)}")
    print("")
    _print_table(rows)

    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("")
    print(f"Saved suggestions: {out}")

    if args.non_interactive:
        return 0

    ok = input("\nDo you want to keep this suggestion plan? [y/N]: ").strip().lower()
    if ok in {"y", "yes"}:
        print("Suggestion plan accepted.")
        return 0

    exclude_days = _parse_csv(
        input("Exclude dates (comma-separated YYYY-MM-DD, optional): ").strip()
    )
    remove_rows = _parse_csv(
        input(
            "Remove suggested rows (comma-separated DATE:TICKET_ID, optional): "
        ).strip()
    )
    notes = input("Correction notes (optional): ").strip()

    parsed_remove: list[dict[str, Any]] = []
    for pair in remove_rows:
        if ":" not in pair:
            continue
        day, raw_id = pair.split(":", 1)
        if raw_id.strip().isdigit():
            parsed_remove.append({"date": day.strip(), "ticket_id": int(raw_id.strip())})

    corrections = {
        "status": "needs_corrections",
        "exclude_days": exclude_days,
        "remove_suggestions": parsed_remove,
        "notes": notes,
    }
    corrections_path = Path(args.corrections_json)
    corrections_path.parent.mkdir(parents=True, exist_ok=True)
    corrections_path.write_text(json.dumps(corrections, indent=2), encoding="utf-8")
    print(f"Saved corrections: {corrections_path}")
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
