#!/usr/bin/env python3
"""Fetch calendar events from an ICS file or URL and normalize them to JSON."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib import request

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

WEEKDAY_INDEX = {
    "MO": 0,
    "TU": 1,
    "WE": 2,
    "TH": 3,
    "FR": 4,
    "SA": 5,
    "SU": 6,
}


def _read_ics(file_path: str | None, ics_url: str | None) -> str:
    if bool(file_path) == bool(ics_url):
        raise ValueError("Provide exactly one of --ics-file or --ics-url.")
    if file_path:
        return Path(file_path).read_text(encoding="utf-8")
    normalized_url = ics_url.replace("webcal://", "https://", 1)
    with request.urlopen(normalized_url) as resp:  # nosec B310
        return resp.read().decode("utf-8")


def _parse_env_file(path: Path) -> dict[str, str]:
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


def _unfold_lines(raw_text: str) -> list[str]:
    unfolded: list[str] = []
    for raw_line in raw_text.splitlines():
        line = raw_line.rstrip("\r")
        if (line.startswith(" ") or line.startswith("\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def _parse_content_lines(lines: list[str]) -> list[dict[str, list[tuple[dict[str, str], str]]]]:
    events: list[dict[str, list[tuple[dict[str, str], str]]]] = []
    current: dict[str, list[tuple[dict[str, str], str]]] | None = None

    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue

        left, value = line.split(":", 1)
        parts = left.split(";")
        key = parts[0].upper()
        params: dict[str, str] = {}
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                params[k.upper()] = v
        current.setdefault(key, []).append((params, value))
    return events


def _unescape_ics_text(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def _resolve_tz(tz_name: str | None, fallback: dt.tzinfo) -> dt.tzinfo:
    if not tz_name or ZoneInfo is None:
        return fallback
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return fallback


def _parse_dt(
    prop: tuple[dict[str, str], str] | None,
    fallback_tz: dt.tzinfo,
) -> tuple[dt.datetime | None, bool]:
    if prop is None:
        return None, False

    params, raw_value = prop
    value = raw_value.strip()
    value_type = params.get("VALUE", "").upper()
    is_all_day = value_type == "DATE" or (len(value) == 8 and value.isdigit())

    if is_all_day:
        parsed_date = dt.datetime.strptime(value[:8], "%Y%m%d").date()
        return dt.datetime.combine(parsed_date, dt.time(0, 0), tzinfo=fallback_tz), True

    fmt = "%Y%m%dT%H%M%S" if len(value.rstrip("Z")) == 15 else "%Y%m%dT%H%M"
    if value.endswith("Z"):
        parsed = dt.datetime.strptime(value[:-1], fmt).replace(tzinfo=dt.timezone.utc)
        return parsed, False

    parsed = dt.datetime.strptime(value, fmt)
    tz_name = params.get("TZID")
    parsed = parsed.replace(tzinfo=_resolve_tz(tz_name, fallback_tz))
    return parsed, False


def _parse_multi_dt_values(
    prop: tuple[dict[str, str], str] | None,
    fallback_tz: dt.tzinfo,
) -> list[dt.datetime]:
    if prop is None:
        return []
    params, raw_values = prop
    values = [v.strip() for v in raw_values.split(",") if v.strip()]
    parsed: list[dt.datetime] = []
    for value in values:
        parsed_value, _ = _parse_dt((params, value), fallback_tz)
        if parsed_value is not None:
            parsed.append(parsed_value)
    return parsed


def _extract_email(raw_value: str) -> str:
    value = raw_value.strip()
    if value.lower().startswith("mailto:"):
        return value[7:]
    return value


def _event_common_fields(
    ev: dict[str, list[tuple[dict[str, str], str]]],
) -> dict[str, Any]:
    uid = (ev.get("UID") or [({}, "")])[0][1]
    summary = _unescape_ics_text((ev.get("SUMMARY") or [({}, "")])[0][1])
    location = _unescape_ics_text((ev.get("LOCATION") or [({}, "")])[0][1])
    description = _unescape_ics_text((ev.get("DESCRIPTION") or [({}, "")])[0][1])

    organizer_prop = (ev.get("ORGANIZER") or [({}, "")])[0]
    organizer = _extract_email(organizer_prop[1])
    if not organizer:
        organizer = organizer_prop[0].get("CN", "")

    attendees: list[str] = []
    for attendee_prop in ev.get("ATTENDEE") or []:
        attendee_email = _extract_email(attendee_prop[1])
        if attendee_email:
            attendees.append(attendee_email)

    categories_raw = (ev.get("CATEGORIES") or [({}, "")])[0][1]
    categories = [c.strip() for c in categories_raw.split(",") if c.strip()]

    return {
        "id": uid,
        "subject": summary,
        "organizer": organizer,
        "categories": categories,
        "attendees": attendees,
        "location": location,
        "bodyPreview": description.replace("\n", " ").strip(),
    }


def _overlaps_range(
    event_start: dt.datetime,
    event_end: dt.datetime,
    range_start: dt.datetime,
    range_end: dt.datetime,
) -> bool:
    return event_start < range_end and event_end > range_start


def _parse_rrule(raw_rule: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in raw_rule.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        result[key.strip().upper()] = value.strip()
    return result


def _rrule_until(
    rrule: dict[str, str],
    fallback_tz: dt.tzinfo,
) -> dt.datetime | None:
    until_raw = rrule.get("UNTIL")
    if not until_raw:
        return None
    until_value, _ = _parse_dt(({}, until_raw), fallback_tz)
    if until_value is None:
        return None
    return until_value.astimezone(dt.timezone.utc)


def _expand_rrule_starts(
    start: dt.datetime,
    rrule_raw: str,
    fallback_tz: dt.tzinfo,
    range_end: dt.datetime,
) -> list[dt.datetime]:
    rrule = _parse_rrule(rrule_raw)
    freq = (rrule.get("FREQ") or "").upper()
    interval = max(1, int(rrule.get("INTERVAL") or "1"))
    count = int(rrule.get("COUNT") or "0")
    until_utc = _rrule_until(rrule, fallback_tz)
    limit_utc = min(until_utc, range_end) if until_utc else range_end

    starts: list[dt.datetime] = []
    emitted = 0

    def can_emit(candidate: dt.datetime) -> bool:
        nonlocal emitted
        if count and emitted >= count:
            return False
        candidate_utc = candidate.astimezone(dt.timezone.utc)
        if candidate_utc > limit_utc:
            return False
        emitted += 1
        starts.append(candidate)
        return True

    if freq == "DAILY":
        current = start
        while True:
            if not can_emit(current):
                break
            current = current + dt.timedelta(days=interval)
        return starts

    if freq == "WEEKLY":
        byday_raw = rrule.get("BYDAY")
        byday = [d.strip().upper() for d in byday_raw.split(",")] if byday_raw else []
        weekdays = sorted(
            WEEKDAY_INDEX[d]
            for d in byday
            if d in WEEKDAY_INDEX
        )
        if not weekdays:
            weekdays = [start.weekday()]

        week_anchor = start.date() - dt.timedelta(days=start.weekday())
        week_offset = 0
        while True:
            base = week_anchor + dt.timedelta(weeks=week_offset)
            emitted_any = False
            for weekday in weekdays:
                occurrence_date = base + dt.timedelta(days=weekday)
                occurrence = dt.datetime.combine(
                    occurrence_date,
                    start.timetz().replace(tzinfo=None),
                    tzinfo=start.tzinfo,
                )
                if occurrence < start:
                    continue
                if not can_emit(occurrence):
                    return starts
                emitted_any = True
            if not emitted_any and count and emitted >= count:
                return starts
            week_offset += interval
        return starts

    return [start]


def _expand_event_instances(
    ev: dict[str, list[tuple[dict[str, str], str]]],
    fallback_tz: dt.tzinfo,
    range_start: dt.datetime,
    range_end: dt.datetime,
) -> list[dict[str, Any]]:
    common = _event_common_fields(ev)
    uid = str(common.get("id") or "")

    start, all_day = _parse_dt((ev.get("DTSTART") or [None])[0], fallback_tz)
    if start is None:
        return []
    end, _ = _parse_dt((ev.get("DTEND") or [None])[0], fallback_tz)
    if end is None:
        end = start + (dt.timedelta(days=1) if all_day else dt.timedelta(hours=1))
    duration = end - start

    rrule_raw = (ev.get("RRULE") or [({}, "")])[0][1].strip()
    has_recurrence_id = bool((ev.get("RECURRENCE-ID") or [({}, "")])[0][1].strip())

    starts: list[dt.datetime]
    if rrule_raw and not has_recurrence_id:
        starts = _expand_rrule_starts(start, rrule_raw, fallback_tz, range_end)
    else:
        starts = [start]

    for rdate_prop in ev.get("RDATE") or []:
        starts.extend(_parse_multi_dt_values(rdate_prop, fallback_tz))

    excluded = {
        ex.astimezone(dt.timezone.utc)
        for ex_prop in (ev.get("EXDATE") or [])
        for ex in _parse_multi_dt_values(ex_prop, fallback_tz)
    }

    unique_starts: dict[str, dt.datetime] = {}
    for occurrence_start in starts:
        key = occurrence_start.astimezone(dt.timezone.utc).isoformat()
        if key not in unique_starts:
            unique_starts[key] = occurrence_start

    normalized: list[dict[str, Any]] = []
    for occurrence_start in sorted(unique_starts.values()):
        occurrence_start_utc = occurrence_start.astimezone(dt.timezone.utc)
        if occurrence_start_utc in excluded:
            continue
        occurrence_end = occurrence_start + duration
        if not _overlaps_range(
            occurrence_start_utc,
            occurrence_end.astimezone(dt.timezone.utc),
            range_start,
            range_end,
        ):
            continue
        event_id = uid or "calendar-event"
        instance_id = f"{event_id}#{occurrence_start_utc.strftime('%Y%m%dT%H%M%SZ')}"
        event = dict(common)
        event.update(
            {
                "id": instance_id,
                "seriesId": uid or instance_id,
                "start": occurrence_start.isoformat(),
                "end": occurrence_end.isoformat(),
                "isAllDay": all_day,
            }
        )
        normalized.append(event)

    return normalized


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--to-date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--env-file",
        default=str(Path(__file__).resolve().parent.parent / ".credentials.env"),
        help="Path to env file with CALENDAR_ICS_URL/CALENDAR_ICS_FILE.",
    )
    parser.add_argument(
        "--ics-file",
        default=None,
        help="Path to an .ics file (overrides env values).",
    )
    parser.add_argument(
        "--ics-url",
        default=None,
        help="URL to an .ics feed (overrides env values).",
    )
    parser.add_argument("--out-json", default="reports/calendar-events.json")
    parser.add_argument(
        "--timezone",
        default=os.environ.get("USER_TIMEZONE", "UTC"),
        help="Fallback timezone for ICS values without TZID (default USER_TIMEZONE or UTC).",
    )
    args = parser.parse_args()

    start_date = dt.date.fromisoformat(args.from_date)
    end_date = dt.date.fromisoformat(args.to_date)
    if start_date > end_date:
        raise ValueError("--from-date must be <= --to-date")

    file_values = _parse_env_file(Path(args.env_file))
    if args.ics_file is not None:
        ics_file = args.ics_file
        ics_url = None
    elif args.ics_url is not None:
        ics_file = None
        ics_url = args.ics_url
    else:
        ics_file = os.environ.get("CALENDAR_ICS_FILE") or file_values.get("CALENDAR_ICS_FILE")
        ics_url = os.environ.get("CALENDAR_ICS_URL") or file_values.get("CALENDAR_ICS_URL")

    if ZoneInfo is None:
        fallback_tz = dt.timezone.utc
    else:
        fallback_tz = _resolve_tz(args.timezone, dt.timezone.utc)

    range_start = dt.datetime.combine(
        start_date, dt.time(0, 0), tzinfo=fallback_tz
    ).astimezone(dt.timezone.utc)
    range_end = (
        dt.datetime.combine(end_date, dt.time(23, 59, 59), tzinfo=fallback_tz)
        .astimezone(dt.timezone.utc)
        + dt.timedelta(seconds=1)
    )

    raw_ics = _read_ics(ics_file, ics_url)
    lines = _unfold_lines(raw_ics)
    parsed_events = _parse_content_lines(lines)
    filtered: list[dict[str, Any]] = []
    for ev in parsed_events:
        filtered.extend(_expand_event_instances(ev, fallback_tz, range_start, range_end))

    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(filtered, indent=2), encoding="utf-8")

    print(f"Events parsed: {len(parsed_events)}")
    print(f"Events in range: {len(filtered)}")
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
