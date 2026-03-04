#!/usr/bin/env python3
"""Write accepted suggested logs to Clockify time entries."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from sync_common import (
    build_config,
    clockify_headers,
    http_json,
    load_yaml,
    parse_env_file,
    require_credentials,
)

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


def _to_utc_iso(local_dt: dt.datetime, tz_name: str) -> str:
    if ZoneInfo is None:
        raise RuntimeError("Python zoneinfo is unavailable. Use Python 3.9+.")
    aware = local_dt.replace(tzinfo=ZoneInfo(tz_name))
    return aware.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _group_by_day(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        day = str(row["date"])
        out.setdefault(day, []).append(row)
    return out


def _validate_rows(rows: list[dict[str, Any]]) -> None:
    required = ("date", "ticket_id", "minutes", "description")
    for idx, row in enumerate(rows):
        missing = [k for k in required if k not in row]
        if missing:
            raise ValueError(f"Row {idx} missing keys: {missing}")
        minutes = int(row["minutes"])
        if minutes <= 0:
            raise ValueError(f"Row {idx} has non-positive minutes: {minutes}")


def _validate_direct_entries(rows: list[dict[str, Any]]) -> None:
    for idx, row in enumerate(rows):
        if not row.get("description"):
            raise ValueError(f"Direct row {idx} missing description")
        if not row.get("start"):
            raise ValueError(f"Direct row {idx} missing start")
        if not row.get("end"):
            raise ValueError(f"Direct row {idx} missing end")
        if not (row.get("project_id") or row.get("projectId")):
            raise ValueError(f"Direct row {idx} missing project_id/projectId")


def _make_payloads(
    rows: list[dict[str, Any]],
    tz_name: str,
    project_id: str,
    task_id: str | None,
    billable: bool,
    workday_start_hour: int,
    epic_tag_prefix: str,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    by_day = _group_by_day(rows)
    for day, day_rows in sorted(by_day.items()):
        current = dt.datetime.fromisoformat(day).replace(
            hour=workday_start_hour, minute=0, second=0, microsecond=0
        )
        for row in day_rows:
            minutes = int(row["minutes"])
            slot_start = row.get("slot_start")
            slot_end = row.get("slot_end")
            if isinstance(slot_start, str) and isinstance(slot_end, str) and ":" in slot_start and ":" in slot_end:
                sh, sm = slot_start.split(":", 1)
                eh, em = slot_end.split(":", 1)
                start_dt = dt.datetime.fromisoformat(day).replace(
                    hour=int(sh), minute=int(sm), second=0, microsecond=0
                )
                end_dt = dt.datetime.fromisoformat(day).replace(
                    hour=int(eh), minute=int(em), second=0, microsecond=0
                )
                if end_dt <= start_dt:
                    end_dt = start_dt + dt.timedelta(minutes=minutes)
            else:
                start_dt = current
                end_dt = current + dt.timedelta(minutes=minutes)
            start_iso = _to_utc_iso(start_dt, tz_name)
            end_iso = _to_utc_iso(end_dt, tz_name)
            payload: dict[str, Any] = {
                "billable": billable,
                "description": str(row["description"])[:3000],
                "start": start_iso,
                "end": end_iso,
                "projectId": str(row.get("project_id") or project_id),
                "type": "REGULAR",
            }
            row_task_id = row.get("task_id") or task_id
            if row_task_id:
                payload["taskId"] = str(row_task_id)
            if row.get("tag_ids"):
                payload["tagIds"] = list(row["tag_ids"])
            if row.get("tag_names"):
                payload["tagNames"] = [str(x) for x in row["tag_names"] if str(x).strip()]
            epic_id = row.get("parent_epic_id")
            if epic_id is not None:
                payload["epicTagName"] = f"{epic_tag_prefix}{epic_id}"
            payloads.append(payload)
            current = end_dt
    return payloads


def _make_payloads_from_direct(rows: list[dict[str, Any]], billable: bool) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for row in rows:
        payload: dict[str, Any] = {
            "billable": billable,
            "description": str(row["description"])[:3000],
            "start": str(row["start"]),
            "end": str(row["end"]),
            "projectId": str(row.get("projectId") or row.get("project_id")),
            "type": "REGULAR",
        }
        if row.get("taskId") or row.get("task_id"):
            payload["taskId"] = str(row.get("taskId") or row.get("task_id"))
        if row.get("tagIds") or row.get("tag_ids"):
            payload["tagIds"] = list(row.get("tagIds") or row.get("tag_ids"))
        payloads.append(payload)
    return payloads


def _load_workspace_tags(headers: dict[str, str], workspace_id: str) -> dict[str, str]:
    url = f"https://api.clockify.me/api/v1/workspaces/{workspace_id}/tags?page-size=5000"
    data = http_json("GET", url, headers)
    if not isinstance(data, list):
        return {}
    out: dict[str, str] = {}
    for t in data:
        name = str(t.get("name") or "")
        tid = str(t.get("id") or "")
        if name and tid:
            out[name] = tid
    return out


def _ensure_tag(headers: dict[str, str], workspace_id: str, name: str) -> str:
    tags = _load_workspace_tags(headers, workspace_id)
    existing = tags.get(name)
    if existing:
        return existing
    created = http_json(
        "POST",
        f"https://api.clockify.me/api/v1/workspaces/{workspace_id}/tags",
        headers,
        {"name": name},
    )
    tag_id = str(created.get("id") or "")
    if not tag_id:
        raise RuntimeError(f"Failed to create/find Clockify tag: {name}")
    return tag_id


def _cleanup_reports_dir(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    deleted = 0
    for item in sorted(path.rglob("*"), reverse=True):
        if item.is_file():
            item.unlink(missing_ok=True)
            deleted += 1
        elif item.is_dir():
            try:
                item.rmdir()
            except OSError:
                pass
    return deleted


def _filter_out_future_payloads(payloads: list[dict[str, Any]], tz_name: str) -> tuple[list[dict[str, Any]], int]:
    if ZoneInfo is None:
        return payloads, 0
    today_local = dt.datetime.now(ZoneInfo(tz_name)).date()
    kept: list[dict[str, Any]] = []
    skipped = 0
    for payload in payloads:
        start_raw = str(payload.get("start") or "")
        try:
            start_dt = dt.datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
            if start_dt.astimezone(ZoneInfo(tz_name)).date() > today_local:
                skipped += 1
                continue
        except ValueError:
            pass
        kept.append(payload)
    return kept, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-json", default="reports/suggested-logs.accepted.json")
    parser.add_argument("--fallback-json", default="reports/suggested-logs.json")
    parser.add_argument("--config", default="config/loggify-me.yaml")
    parser.add_argument(
        "--env-file",
        default="skills/loggify-me/.credentials.env",
    )
    parser.add_argument(
        "--workday-start-hour",
        type=int,
        default=9,
        help="Local start hour for placing generated blocks in a day.",
    )
    parser.add_argument(
        "--epic-tag-prefix",
        default="",
        help="Optional prefix for Clockify tags carrying parent epic number (default: none).",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first API write error.",
    )
    parser.add_argument(
        "--cleanup-reports",
        dest="cleanup_reports",
        action="store_true",
        help="Delete files under reports directory after --apply run (default: enabled).",
    )
    parser.add_argument(
        "--no-cleanup-reports",
        dest="cleanup_reports",
        action="store_false",
        help="Keep reports files after --apply run.",
    )
    parser.add_argument(
        "--cleanup-dir",
        default="reports",
        help="Directory to clean after --apply (default: reports).",
    )
    parser.add_argument("--apply", action="store_true")
    parser.set_defaults(cleanup_reports=True)
    args = parser.parse_args()

    accepted_path = Path(args.accepted_json)
    source_path = accepted_path if accepted_path.exists() else Path(args.fallback_json)
    if not source_path.exists():
        raise FileNotFoundError(
            f"Accepted plan not found: {accepted_path} (and fallback missing: {args.fallback_json})"
        )
    source = json.loads(source_path.read_text(encoding="utf-8"))

    env_values = parse_env_file(Path(args.env_file))
    creds = require_credentials(env_values)
    raw_cfg = load_yaml(Path(args.config))
    cfg = build_config(raw_cfg, creds)

    clockify_cfg = raw_cfg.get("clockify") or {}
    project_id = (
        (env_values.get("CLOCKIFY_DEFAULT_PROJECT_ID") or "").strip()
        or str(clockify_cfg.get("default_project_id") or "").strip()
    )
    if not project_id:
        raise ValueError(
            "Missing default project id. Set CLOCKIFY_DEFAULT_PROJECT_ID in "
            ".credentials.env or clockify.default_project_id in config."
        )
    task_id = clockify_cfg.get("default_task_id")
    billable = bool(clockify_cfg.get("billable", True))

    if isinstance(source, dict):
        rows = list(source.get("suggested_logs") or [])
        _validate_rows(rows)
        payloads = _make_payloads(
            rows=rows,
            tz_name=cfg.timezone,
            project_id=project_id,
            task_id=str(task_id) if task_id else None,
            billable=billable,
            workday_start_hour=args.workday_start_hour,
            epic_tag_prefix=args.epic_tag_prefix,
        )
    elif isinstance(source, list):
        rows = [r for r in source if isinstance(r, dict)]
        _validate_direct_entries(rows)
        payloads = _make_payloads_from_direct(rows, billable=billable)
    else:
        raise ValueError("Accepted JSON must be object (suggested_logs) or array (direct).")

    payloads, skipped_future = _filter_out_future_payloads(payloads, cfg.timezone)

    print(f"Source file: {source_path}")
    print(f"Rows to write: {len(payloads)}")
    if skipped_future:
        print(f"Skipped future rows: {skipped_future}")
    print(f"Workspace: {cfg.workspace_id}")
    print(f"Apply mode: {'ON' if args.apply else 'OFF (dry-run)'}")
    print("")
    for i, payload in enumerate(payloads[:20], start=1):
        print(
            f"{i}. {payload['start']} -> {payload['end']} | "
            f"{payload['projectId']} | {payload['description'][:80]}"
        )
    if len(payloads) > 20:
        print(f"... and {len(payloads) - 20} more rows")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to write to Clockify.")
        return 0

    headers = clockify_headers(creds["CLOCKIFY_API_KEY"])
    tag_cache = _load_workspace_tags(headers, cfg.workspace_id)
    endpoint = f"https://api.clockify.me/api/v1/workspaces/{cfg.workspace_id}/time-entries"
    created = 0
    errors: list[str] = []
    for idx, payload in enumerate(payloads, start=1):
        try:
            epic_tag = payload.pop("epicTagName", None)
            tag_names = list(payload.pop("tagNames", []) or [])
            existing_ids = list(payload.get("tagIds") or [])
            for tag_name in tag_names:
                tag_id = tag_cache.get(tag_name)
                if not tag_id:
                    tag_id = _ensure_tag(headers, cfg.workspace_id, tag_name)
                    tag_cache[tag_name] = tag_id
                if tag_id not in existing_ids:
                    existing_ids.append(tag_id)
            if epic_tag:
                tag_id = tag_cache.get(epic_tag)
                if not tag_id:
                    tag_id = _ensure_tag(headers, cfg.workspace_id, epic_tag)
                    tag_cache[epic_tag] = tag_id
                if tag_id not in existing_ids:
                    existing_ids.append(tag_id)
            if existing_ids:
                payload["tagIds"] = existing_ids
            http_json("POST", endpoint, headers, payload)
            created += 1
        except Exception as exc:
            errors.append(f"row {idx}: {exc}")
            if args.fail_fast:
                break

    print("")
    print(f"Created: {created}")
    print(f"Failed: {len(errors)}")
    for err in errors[:20]:
        print(f"- {err}")

    if args.cleanup_reports:
        deleted = _cleanup_reports_dir(Path(args.cleanup_dir))
        print(f"Cleanup: deleted {deleted} file(s) from {args.cleanup_dir}")

    return 0 if not errors else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
