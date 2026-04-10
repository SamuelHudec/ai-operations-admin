#!/usr/bin/env python3
"""Shared helpers for ADO/Clockify planning scripts."""

from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


REQUIRED_CREDENTIALS = (
    "CLOCKIFY_WORKSPACE_ID",
    "CLOCKIFY_API_KEY",
    "WORK_DAYS",
    "DAILY_TARGET_HOURS",
)
WEEKDAY_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


@dataclass
class Config:
    timezone: str
    workdays: list[str]
    daily_target_hours: float
    exclude_dates: set[dt.date]
    include_dates: set[dt.date]
    ado_project: str
    ado_org_url: str
    workspace_id: str


PLACEHOLDER_VALUES = {
    "",
    "name@company.com",
    "user@example.com",
    "your@email.com",
    "yourproject",
    "workspace-id",
    "project-id-default",
    "https://dev.azure.com/your-org",
    "/path/to/calendar.ics",
}


def parse_env_file(path: Path) -> dict[str, str]:
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


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    if yaml is None:
        raise RuntimeError("PyYAML is required. Install with: pip install pyyaml")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("Config root must be an object/map.")
    return data


def get_value(name: str, env_file_values: dict[str, str]) -> str:
    return os.environ.get(name, "").strip() or env_file_values.get(name, "").strip()


def is_placeholder_value(value: str) -> bool:
    normalized = value.strip().strip('"').strip("'")
    lowered = normalized.lower()
    return lowered in PLACEHOLDER_VALUES or lowered.endswith("@example.com")


def runtime_date_range(
    *,
    from_date: str | None,
    to_date: str | None,
    today: dt.date | None = None,
) -> tuple[dt.date, dt.date, dt.date]:
    current_day = today or dt.date.today()
    requested_end_date = dt.date.fromisoformat(to_date) if to_date else current_day
    end_date = min(requested_end_date, current_day)
    if from_date:
        start_date = dt.date.fromisoformat(from_date)
    else:
        start_date = end_date - dt.timedelta(days=end_date.weekday())
    if start_date > end_date:
        raise ValueError("--from-date cannot be after --to-date.")
    return start_date, end_date, requested_end_date


def require_credentials(env_file_values: dict[str, str]) -> dict[str, str]:
    creds: dict[str, str] = {}
    missing: list[str] = []
    for key in REQUIRED_CREDENTIALS:
        value = get_value(key, env_file_values)
        if not value:
            missing.append(key)
        else:
            creds[key] = value
    if missing:
        names = "\n".join(f"- {name}" for name in missing)
        raise RuntimeError(
            "Missing credentials:\n"
            f"{names}\n"
            "Set them in environment or skill-local .credentials.env."
        )
    return creds


def _parse_dates(values: list[str]) -> set[dt.date]:
    out: set[dt.date] = set()
    for raw in values:
        out.add(dt.date.fromisoformat(str(raw)))
    return out


def build_config(raw: dict[str, Any], creds: dict[str, str]) -> Config:
    user = raw.get("user") or {}
    schedule = raw.get("schedule") or {}
    sources = raw.get("sources") or {}
    ado = sources.get("ado") or {}

    env_work_days = creds.get("WORK_DAYS", "")
    if env_work_days:
        workdays = [d.strip().lower() for d in env_work_days.split(",") if d.strip()]
    else:
        workdays = schedule.get("workdays") or ["mon", "tue", "wed", "thu", "fri"]
    for day in workdays:
        if day not in WEEKDAY_INDEX:
            raise ValueError(f"Invalid weekday in schedule.workdays: {day}")

    env_daily_hours = creds.get("DAILY_TARGET_HOURS", "")
    if env_daily_hours:
        daily_target_hours = float(env_daily_hours)
    else:
        daily_target_hours = float(schedule.get("daily_target_hours") or 8)

    env_timezone = creds.get("USER_TIMEZONE", "")
    timezone = env_timezone or str(user.get("timezone") or "UTC")

    ado_project = str(creds.get("ADO_PROJECT") or ado.get("project") or "").strip()
    if is_placeholder_value(ado_project):
        ado_project = ""

    ado_org_url = str(creds.get("ADO_ORG_URL") or ado.get("org_url") or "").strip().rstrip("/")
    if is_placeholder_value(ado_org_url):
        ado_org_url = ""

    return Config(
        timezone=timezone,
        workdays=list(workdays),
        daily_target_hours=daily_target_hours,
        exclude_dates=_parse_dates(schedule.get("exclude_dates") or []),
        include_dates=_parse_dates(schedule.get("include_dates") or []),
        ado_project=ado_project,
        ado_org_url=ado_org_url,
        workspace_id=creds["CLOCKIFY_WORKSPACE_ID"],
    )


def http_json(
    method: str, url: str, headers: dict[str, str], payload: dict[str, Any] | None = None
) -> Any:
    body = None
    merged_headers = dict(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        merged_headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, method=method, headers=merged_headers)
    try:
        with request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {url}\n{detail}") from exc


def daterange(start: dt.date, end: dt.date) -> list[dt.date]:
    days: list[dt.date] = []
    cur = start
    while cur <= end:
        days.append(cur)
        cur += dt.timedelta(days=1)
    return days


def working_days(start: dt.date, end: dt.date, config: Config) -> list[dt.date]:
    workday_indexes = {WEEKDAY_INDEX[d] for d in config.workdays}
    out: list[dt.date] = []
    for day in daterange(start, end):
        if day in config.exclude_dates and day not in config.include_dates:
            continue
        if day in config.include_dates or day.weekday() in workday_indexes:
            out.append(day)
    return out


def parse_iso_datetime(value: str) -> dt.datetime:
    normalized = value.replace("Z", "+00:00")
    return dt.datetime.fromisoformat(normalized)


def parse_iso8601_duration_to_minutes(raw: str) -> int | None:
    if not raw.startswith("PT"):
        return None
    value = raw[2:]
    num = ""
    hours = 0
    minutes = 0
    seconds = 0
    for ch in value:
        if ch.isdigit():
            num += ch
            continue
        if not num:
            return None
        if ch == "H":
            hours = int(num)
        elif ch == "M":
            minutes = int(num)
        elif ch == "S":
            seconds = int(num)
        else:
            return None
        num = ""
    return hours * 60 + minutes + int(seconds / 60)


def clockify_headers(api_key: str) -> dict[str, str]:
    return {"X-Api-Key": api_key}
