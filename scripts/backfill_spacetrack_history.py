#!/usr/bin/env python3
"""One-time, bounded Space-Track GP_HISTORY backfill into the append-only store."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import requests

from history_store import HistoryStore, history_entry, now_utc
from update_catalog import SPACE_TRACK_BASE, space_track_source


def batches(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def query_path(norad_ids: list[str], start: str, end: str) -> str:
    identifiers = ",".join(norad_ids)
    return (
        "/basicspacedata/query/class/gp_history/"
        f"NORAD_CAT_ID/{identifiers}/EPOCH/{start}--{end}/"
        "orderby/NORAD_CAT_ID,EPOCH/format/json"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download each requested GP_HISTORY interval once and retain it locally."
    )
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument("--start", required=True, help="UTC date/time accepted by Space-Track")
    parser.add_argument("--end", required=True, help="UTC date/time accepted by Space-Track")
    parser.add_argument("--norad-csv", help="Comma-separated NORAD IDs")
    parser.add_argument("--all-catalog-targets", action="store_true")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--sleep-seconds", type=float, default=3.2)
    args = parser.parse_args()
    if bool(args.norad_csv) == bool(args.all_catalog_targets):
        raise ValueError("Choose exactly one of --norad-csv or --all-catalog-targets")
    if not 1 <= args.batch_size <= 50:
        raise ValueError("--batch-size must be between 1 and 50")

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    records_by_norad = {
        str(record["norad_cat_id"]): record
        for record in catalog.get("records", [])
        if record.get("norad_cat_id")
    }
    if args.norad_csv:
        norad_ids = sorted({item.strip() for item in args.norad_csv.split(",") if item.strip()})
    else:
        norad_ids = sorted(records_by_norad, key=lambda value: int(value))
    unknown = [value for value in norad_ids if value not in records_by_norad]
    if unknown:
        raise ValueError(f"NORAD IDs are not in the current catalog: {', '.join(unknown)}")

    username = os.environ.get("SPACETRACK_USERNAME", "").strip()
    password = os.environ.get("SPACETRACK_PASSWORD", "").strip()
    if not username or not password:
        raise RuntimeError("SPACETRACK_USERNAME and SPACETRACK_PASSWORD are required")

    recorded_at = now_utc()
    store = HistoryStore(args.history_root, recorded_at)
    response_rows = 0
    added_rows = 0
    with requests.Session() as session:
        login = session.post(
            f"{SPACE_TRACK_BASE}/ajaxauth/login",
            data={"identity": username, "password": password},
            timeout=45,
        )
        login.raise_for_status()
        id_batches = batches(norad_ids, args.batch_size)
        for number, identifiers in enumerate(id_batches, 1):
            path = query_path(identifiers, args.start, args.end)
            response = session.get(f"{SPACE_TRACK_BASE}{path}", timeout=180)
            response.raise_for_status()
            payload: Any = response.json()
            if not isinstance(payload, list):
                raise RuntimeError("Space-Track GP_HISTORY response is not a JSON list")
            response_rows += len(payload)
            for item in payload:
                norad = str(item.get("NORAD_CAT_ID"))
                record = records_by_norad.get(norad)
                if not record:
                    continue
                source = space_track_source(item, recorded_at)
                source["source_url"] = f"{SPACE_TRACK_BASE}{path}"
                added_rows += int(store.add(history_entry(record, source, recorded_at)))
            print(f"Batch {number}/{len(id_batches)}: received {len(payload)} rows")
            if number < len(id_batches):
                time.sleep(args.sleep_seconds)
        session.get(f"{SPACE_TRACK_BASE}/ajaxauth/logout", timeout=30)

    shard = store.commit()
    location = shard["path"] if shard else "no new shard"
    print(f"Received {response_rows} rows; archived {added_rows} unseen rows; {location}")


if __name__ == "__main__":
    main()

