#!/usr/bin/env python3
"""Export the complete Space-Track GP_HISTORY series for DRO-A and DRO-B.

The script intentionally writes an Actions artifact instead of committing the
licensed Space-Track response to the public repository.
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import requests


BASE_URL = "https://www.space-track.org"
TARGETS = {"59228": "DRO-A", "60058": "DRO-B"}


def month_intervals(start: date, end_exclusive: date) -> Iterator[tuple[date, date]]:
    cursor = start
    while cursor < end_exclusive:
        _, days = calendar.monthrange(cursor.year, cursor.month)
        next_month = cursor.replace(day=days) + timedelta(days=1)
        stop = min(next_month, end_exclusive)
        yield cursor, stop
        cursor = stop


def query_path(norad_ids: str, start: date, end_exclusive: date) -> str:
    return (
        "/basicspacedata/query/class/gp_history/"
        f"NORAD_CAT_ID/{norad_ids}/"
        f"EPOCH/{start.isoformat()}--{end_exclusive.isoformat()}/"
        "orderby/NORAD_CAT_ID,EPOCH/format/json"
    )


def row_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("NORAD_CAT_ID", "")),
        str(row.get("EPOCH", "")),
        str(row.get("ELEMENT_SET_NO", "")),
        str(row.get("TLE_LINE1", "")),
        str(row.get("TLE_LINE2", "")),
    )


def write_outputs(output: Path, rows: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "space-track_gp_history_DRO-A_DRO-B.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for norad_id, name in TARGETS.items():
        target_rows = [row for row in rows if str(row.get("NORAD_CAT_ID")) == norad_id]
        (output / f"{name}_omm.json").write_text(
            json.dumps(target_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        tle_lines: list[str] = []
        for row in target_rows:
            line1 = str(row.get("TLE_LINE1", "")).strip()
            line2 = str(row.get("TLE_LINE2", "")).strip()
            if line1 and line2:
                tle_lines.extend([f"0 {name}", line1, line2])
        (output / f"{name}.tle").write_text(
            ("\n".join(tle_lines) + "\n") if tle_lines else "", encoding="utf-8"
        )
        manifest["targets"][name] = {
            "norad_cat_id": norad_id,
            "row_count": len(target_rows),
            "first_epoch": target_rows[0].get("EPOCH") if target_rows else None,
            "last_epoch": target_rows[-1].get("EPOCH") if target_rows else None,
            "tle_count": len(tle_lines) // 3,
        }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", default="2024-03-01")
    parser.add_argument(
        "--end-exclusive",
        default=(datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat(),
    )
    parser.add_argument("--sleep-seconds", type=float, default=3.2)
    args = parser.parse_args()

    username = os.environ.get("SPACETRACK_USERNAME", "").strip()
    password = os.environ.get("SPACETRACK_PASSWORD", "").strip()
    if not username or not password:
        raise RuntimeError("SPACETRACK_USERNAME and SPACETRACK_PASSWORD are required")

    start = date.fromisoformat(args.start)
    end_exclusive = date.fromisoformat(args.end_exclusive)
    if end_exclusive <= start:
        raise ValueError("--end-exclusive must be after --start")

    identifiers = ",".join(TARGETS)
    intervals = list(month_intervals(start, end_exclusive))
    all_rows: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    with requests.Session() as session:
        login = session.post(
            f"{BASE_URL}/ajaxauth/login",
            data={"identity": username, "password": password},
            timeout=45,
        )
        login.raise_for_status()
        for index, (left, right) in enumerate(intervals, 1):
            path = query_path(identifiers, left, right)
            response = session.get(f"{BASE_URL}{path}", timeout=180)
            response.raise_for_status()
            payload: Any = response.json()
            if not isinstance(payload, list):
                raise RuntimeError("Space-Track GP_HISTORY response is not a JSON list")
            all_rows.extend(item for item in payload if isinstance(item, dict))
            queries.append(
                {"start": left.isoformat(), "end_exclusive": right.isoformat(), "rows": len(payload)}
            )
            print(f"Interval {index}/{len(intervals)}: {left}--{right}, {len(payload)} rows")
            if index < len(intervals):
                time.sleep(args.sleep_seconds)
        session.get(f"{BASE_URL}/ajaxauth/logout", timeout=30)

    deduplicated = {row_key(row): row for row in all_rows}
    rows = sorted(
        deduplicated.values(),
        key=lambda row: (int(row.get("NORAD_CAT_ID", 0)), str(row.get("EPOCH", ""))),
    )
    manifest: dict[str, Any] = {
        "source": "Space-Track.org GP_HISTORY",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "query_start": start.isoformat(),
        "query_end_exclusive": end_exclusive.isoformat(),
        "raw_rows": len(all_rows),
        "deduplicated_rows": len(rows),
        "queries": queries,
        "targets": {},
    }
    write_outputs(args.output, rows, manifest)
    print(f"Wrote {len(rows)} unique rows to {args.output}")


if __name__ == "__main__":
    main()

