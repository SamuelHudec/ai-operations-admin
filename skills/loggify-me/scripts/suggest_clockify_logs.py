#!/usr/bin/env python3
"""Generate suggested Clockify log blocks from plan.json and planning rules."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from sync_common import load_yaml


def _strip_html(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _short_text(raw: str, max_words: int = 12, max_chars: int = 96) -> str:
    text = _strip_html(raw)
    if not text:
        return ""
    text = " ".join(text.split()[:max_words])
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _clean_ticket_title(raw: str) -> str:
    text = _strip_html(raw)
    if not text:
        return ""
    text = re.sub(r"https?://\S+", "", text)
    text = re.split(r",\s*focusing on\b", text, maxsplit=1, flags=re.IGNORECASE)[0]
    text = re.sub(
        r"^(Reviewed and clarified|Implemented and progressed|Validated and refined|"
        r"Coordinated and resolved follow-up on|Finalized and documented)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip(" ,.;:-")
    return text


def _sentence_for_ticket(ticket: dict[str, Any], occurrence: int, fallback_text: str) -> str:
    ticket_id = ticket.get("id")
    suffix = f" (part {occurrence})" if occurrence > 1 else ""
    if ticket_id not in (None, ""):
        return f"{ticket_id}{suffix}"
    title = _short_text(_clean_ticket_title(str(ticket.get("title") or "")))
    if not title:
        title = _short_text(fallback_text)
    if not title:
        title = "Work item"
    return f"{title}{suffix}"


def _print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No suggested logs.")
        return
    header = ["Date", "Start", "End", "Description", "Tag"]
    widths = [10, 5, 5, 78, 18]
    print(f"{header[0]:<{widths[0]}}  {header[1]:<{widths[1]}}  {header[2]:<{widths[2]}}  {header[3]:<{widths[3]}}  {header[4]}")
    print("-" * (sum(widths) + 12))
    for row in rows:
        source_type = str(row.get("source_type") or "")
        if source_type == "calendar":
            tag = ",".join(str(x) for x in (row.get("tag_names") or []) if str(x).strip()) or "-"
        else:
            epic = row.get("parent_epic_id")
            tag = str(epic) if epic is not None else "-"
        print(
            f"{row['date']:<{widths[0]}}  "
            f"{str(row.get('slot_start', '--:--')):<{widths[1]}}  "
            f"{str(row.get('slot_end', '--:--')):<{widths[2]}}  "
            f"{str(row.get('description', ''))[:widths[3]]:<{widths[3]}}  "
            f"{tag[:widths[4]]}"
        )


def _parse_csv(text: str) -> list[str]:
    return [x.strip() for x in text.split(",") if x.strip()]


def _minutes_from_hhmm(value: str) -> int:
    h, m = value.split(":", 1)
    return int(h) * 60 + int(m)


def _hhmm_from_minutes(value: int) -> str:
    h, m = divmod(value, 60)
    return f"{h:02d}:{m:02d}"


def _event_to_local_minutes(event: dict[str, Any], day: str) -> tuple[int, int] | None:
    start_raw = str(event.get("start") or "")
    end_raw = str(event.get("end") or "")
    if not start_raw or not end_raw:
        return None
    start_dt = dt.datetime.fromisoformat(start_raw)
    end_dt = dt.datetime.fromisoformat(end_raw)
    if end_dt <= start_dt:
        return None
    if start_dt.date().isoformat() != day and end_dt.date().isoformat() != day:
        return None
    day_date = dt.date.fromisoformat(day)
    if start_dt.tzinfo is not None:
        day_start = dt.datetime.combine(day_date, dt.time(0, 0), tzinfo=start_dt.tzinfo)
    else:
        day_start = dt.datetime.combine(day_date, dt.time(0, 0))
    start_minutes = int((start_dt - day_start).total_seconds() // 60)
    end_minutes = int((end_dt - day_start).total_seconds() // 60)
    start_minutes = max(0, start_minutes)
    end_minutes = min(24 * 60, end_minutes)
    if end_minutes <= start_minutes:
        return None
    return start_minutes, end_minutes


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not intervals:
        return []
    items = sorted(intervals)
    merged = [items[0]]
    for cur_s, cur_e in items[1:]:
        prev_s, prev_e = merged[-1]
        if cur_s <= prev_e:
            merged[-1] = (prev_s, max(prev_e, cur_e))
        else:
            merged.append((cur_s, cur_e))
    return merged


def _next_non_overlapping_start(
    start: int,
    block_minutes: int,
    occupied: list[tuple[int, int]],
) -> int:
    cur = start
    while True:
        shifted = False
        for occ_s, occ_e in occupied:
            if cur < occ_e and cur + block_minutes > occ_s:
                cur = occ_e
                shifted = True
                break
        if not shifted:
            return cur


def _next_occupied_interval(start: int, occupied: list[tuple[int, int]]) -> tuple[int, int] | None:
    for occ_s, occ_e in sorted(occupied):
        if occ_e <= start:
            continue
        return occ_s, occ_e
    return None


def _free_windows(day_start: int, day_end: int, occupied: list[tuple[int, int]]) -> list[tuple[int, int]]:
    windows: list[tuple[int, int]] = []
    cursor = day_start
    for occ_s, occ_e in _merge_intervals(occupied):
        if occ_e <= day_start:
            continue
        if occ_s >= day_end:
            break
        clipped_s = max(day_start, occ_s)
        clipped_e = min(day_end, occ_e)
        if cursor < clipped_s:
            windows.append((cursor, clipped_s))
        cursor = max(cursor, clipped_e)
    if cursor < day_end:
        windows.append((cursor, day_end))
    return [(s, e) for s, e in windows if e > s]


def _pick_block_minutes(
    day: str,
    index: int,
    remaining: int,
    window_len: int,
    min_block_minutes: int,
    max_block_minutes: int,
    prefer_large_block: bool = False,
) -> int:
    cap = min(remaining, window_len, max_block_minutes)
    if cap <= 0:
        return 0
    if prefer_large_block:
        return cap
    if remaining <= min_block_minutes:
        return cap
    pattern = [60, 90, 120, 150, 180]
    seed = sum(ord(c) for c in day) + index * 7
    preferred = pattern[seed % len(pattern)]
    if preferred < min_block_minutes:
        preferred = min_block_minutes
    if preferred > cap:
        return cap
    return preferred


def _pick_window(
    windows: list[tuple[int, int]],
    min_block_minutes: int,
    min_entry_minutes: int,
    prefer_large_block: bool = False,
) -> tuple[int, int] | None:
    usable = [
        window
        for window in windows
        if (window[1] - window[0]) >= min_block_minutes
        or (window[1] - window[0]) >= min_entry_minutes
    ]
    if not usable:
        return None
    if prefer_large_block:
        return max(usable, key=lambda window: window[1] - window[0])
    return usable[0]


def generate_suggestions(
    plan: dict[str, Any],
    cfg: dict[str, Any],
    calendar_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    planning = (cfg.get("clockify_planning") or {}) if isinstance(cfg, dict) else {}
    allocation = (cfg.get("allocation") or {}) if isinstance(cfg, dict) else {}
    clockify_cfg = (cfg.get("clockify") or {}) if isinstance(cfg, dict) else {}

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
    min_entry_minutes = max(15, int(allocation.get("min_entry_minutes") or 15))
    workday_start_hour = int(planning.get("workday_start_hour") or 9)
    workday_end_hour = int(planning.get("workday_end_hour") or 18)
    ceremony_tag_name = str(clockify_cfg.get("ceremony_tag_name") or "ceremonies")
    min_meeting_minutes = int(((cfg.get("sources") or {}).get("calendar") or {}).get("min_minutes") or 15)
    day_start_minutes = workday_start_hour * 60
    day_end_minutes = workday_end_hour * 60
    if day_end_minutes <= day_start_minutes:
        day_end_minutes = day_start_minutes + 9 * 60

    today = dt.date.today()
    missing_by_day: dict[str, int] = {}
    for d in plan.get("days_to_fill", []):
        day_raw = str(d.get("date") or "")
        try:
            day_value = dt.date.fromisoformat(day_raw)
        except ValueError:
            continue
        if day_value <= today:
            missing_by_day[day_raw] = int(d.get("missing_minutes") or 0)
    days_plan = plan.get("days_plan") or {}
    calendar_by_day: dict[str, list[dict[str, Any]]] = {}
    for event in calendar_events or []:
        start_raw = str(event.get("start") or "")
        if not start_raw:
            continue
        try:
            day = dt.datetime.fromisoformat(start_raw).date().isoformat()
        except Exception:
            continue
        calendar_by_day.setdefault(day, []).append(event)
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

        day_rows: list[dict[str, Any]] = []
        day_ticket_counts: dict[int, int] = {}
        occupied: list[tuple[int, int]] = []

        # 1) Place meetings first in their real time windows.
        for event in calendar_by_day.get(day, []):
            slot = _event_to_local_minutes(event, day)
            if not slot:
                continue
            start_m, end_m = slot
            start_m = max(start_m, day_start_minutes)
            end_m = min(end_m, day_end_minutes)
            if end_m <= start_m:
                continue
            minutes = end_m - start_m
            if minutes < min_meeting_minutes:
                continue
            day_rows.append(
                {
                    "date": day,
                    "ticket_id": str(event.get("id") or "calendar"),
                    "title": str(event.get("subject") or "Meeting"),
                    "minutes": minutes,
                    "description": str(event.get("subject") or "Meeting"),
                    "slot_start": _hhmm_from_minutes(start_m),
                    "slot_end": _hhmm_from_minutes(end_m),
                    "source_type": "calendar",
                    "tag_names": [ceremony_tag_name],
                }
            )
            occupied.append((start_m, end_m))
        occupied = _merge_intervals(occupied)
        meetings_minutes = sum(int(r["minutes"]) for r in day_rows)

        # 2) Fill remaining target with ADO ticket blocks.
        if not tickets:
            if day_missing - meetings_minutes > 0:
                unresolved_days.append(day)
            suggested_rows.extend(sorted(day_rows, key=lambda r: r.get("slot_start", "")))
            continue

        remaining_missing = max(0, day_missing - meetings_minutes)
        if remaining_missing <= 0:
            suggested_rows.extend(sorted(day_rows, key=lambda r: r.get("slot_start", "")))
            continue

        _ = round_to  # kept for backward-compatible rules reporting
        remaining = remaining_missing
        i = 0
        while remaining > 0 and i < max_entries_per_day:
            windows = _free_windows(day_start_minutes, day_end_minutes, occupied)
            if not windows:
                break
            ticket = tickets[i % len(tickets)]
            tid = int(ticket["id"])
            prefer_large_block = len(tickets) == 1 or day_ticket_counts.get(tid, 0) > 0
            chosen_window = _pick_window(
                windows,
                min_block_minutes=min_block_minutes,
                min_entry_minutes=min_entry_minutes,
                prefer_large_block=prefer_large_block,
            )
            if chosen_window is None:
                break

            start_m = chosen_window[0]
            window_len = chosen_window[1] - chosen_window[0]
            occurrences[tid] = occurrences.get(tid, 0) + 1
            block_minutes = _pick_block_minutes(
                day=day,
                index=i,
                remaining=remaining,
                window_len=window_len,
                min_block_minutes=min_block_minutes,
                max_block_minutes=max_block_minutes,
                prefer_large_block=prefer_large_block,
            )
            if block_minutes < min_entry_minutes:
                break

            end_m = start_m + int(block_minutes)
            occupied.append((start_m, end_m))
            occupied = _merge_intervals(occupied)
            day_ticket_counts[tid] = day_ticket_counts.get(tid, 0) + 1
            day_rows.append(
                {
                    "date": day,
                    "ticket_id": tid,
                    "title": str(ticket.get("title") or ""),
                    "parent_epic_id": ticket.get("parent_epic_id"),
                    "minutes": block_minutes,
                    "description": _sentence_for_ticket(
                        ticket, occurrences[tid], fallback_text
                    ),
                    "slot_start": _hhmm_from_minutes(start_m),
                    "slot_end": _hhmm_from_minutes(end_m),
                    "source_type": "ado",
                }
            )
            remaining -= int(block_minutes)
            i += 1

        if remaining > 0:
            unresolved_days.append(day)
        suggested_rows.extend(sorted(day_rows, key=lambda r: r.get("slot_start", "")))

    return {
        "range": plan.get("range") or {},
        "source_plan_file": "reports/plan.json",
        "source_calendar_file": "reports/calendar-events.json",
        "rules_used": {
            "max_block_hours": max_block_hours,
            "min_block_minutes": min_block_minutes,
            "max_entries_per_day": max_entries_per_day,
            "round_to_minutes": round_to,
            "workday_start_hour": workday_start_hour,
            "calendar_meetings_first": True,
            "ceremony_tag_name": ceremony_tag_name,
        },
        "suggested_logs": suggested_rows,
        "unresolved_days_without_tickets": unresolved_days,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", default="reports/plan.json")
    parser.add_argument("--config", default="config/loggify-me.yaml")
    parser.add_argument("--calendar-json", default="reports/calendar-events.json")
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
    calendar_events: list[dict[str, Any]] = []
    calendar_path = Path(args.calendar_json)
    if calendar_path.exists():
        raw = json.loads(calendar_path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            calendar_events = [e for e in raw if isinstance(e, dict)]

    result = generate_suggestions(plan, cfg, calendar_events)
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
