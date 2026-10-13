#!/usr/bin/env python3
"""Archive one missing complete calendar month of Space-Track GP_HISTORY."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MONTHLY_SCHEMA_VERSION = "1.0.0"
DEFAULT_START_MONTH = "2026-09"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_month(value: str) -> date:
    try:
        parsed = datetime.strptime(value, "%Y-%m").date()
    except ValueError as exc:
        raise ValueError(f"Invalid month {value!r}; expected YYYY-MM") from exc
    return parsed.replace(day=1)


def next_month(value: date) -> date:
    return date(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1)


def complete_months(start_month: str, as_of: date, completed: set[str]) -> list[tuple[str, str, str]]:
    month = parse_month(start_month)
    current_month = as_of.replace(day=1)
    result: list[tuple[str, str, str]] = []
    while month < current_month:
        label = month.strftime("%Y-%m")
        following = next_month(month)
        if label not in completed:
            result.append((label, month.isoformat(), (following - timedelta(days=1)).isoformat()))
        month = following
    return result


def load_state(path: Path, start_month: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": MONTHLY_SCHEMA_VERSION,
            "start_month": start_month,
            "updated_at_utc": None,
            "months": [],
        }
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != MONTHLY_SCHEMA_VERSION:
        raise ValueError("Unsupported monthly history state schema")
    if state.get("start_month") != start_month:
        raise ValueError(
            f"Configured start month {start_month} does not match stored {state.get('start_month')}"
        )
    if not isinstance(state.get("months"), list):
        raise ValueError("Monthly history state months must be a list")
    return state


def catalog_target_count(path: Path) -> int:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    return sum(1 for record in catalog.get("records", []) if record.get("norad_cat_id"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument("--start-month", default=DEFAULT_START_MONTH)
    parser.add_argument("--as-of", help="UTC date used for planning/testing; defaults to today")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of) if args.as_of else datetime.now(timezone.utc).date()
    state_path = args.history_root / "gp_history_months.json"
    state = load_state(state_path, args.start_month)
    completed = {str(item.get("month")) for item in state["months"] if item.get("status") == "complete"}
    due = complete_months(args.start_month, as_of, completed)
    if not due:
        print("No complete unarchived Space-Track month is due")
        return

    month, start, end = due[0]
    if args.plan_only:
        print(json.dumps({"month": month, "start": start, "end": end}, ensure_ascii=False))
        return

    command = [
        sys.executable,
        str(Path(__file__).with_name("backfill_spacetrack_history.py")),
        "--catalog",
        str(args.catalog),
        "--history-root",
        str(args.history_root),
        "--start",
        start,
        "--end",
        end,
        "--all-catalog-targets",
        "--batch-size",
        "50",
    ]
    print(f"Archiving Space-Track calendar month {month}: {start} through {end}")
    subprocess.run(command, check=True)

    state["months"].append(
        {
            "month": month,
            "start_epoch": start,
            "end_epoch": end,
            "completed_at_utc": now_utc(),
            "target_count": catalog_target_count(args.catalog),
            "status": "complete",
        }
    )
    state["updated_at_utc"] = now_utc()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Marked {month} complete in {state_path}")


if __name__ == "__main__":
    main()

