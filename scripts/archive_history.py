#!/usr/bin/env python3
"""Archive unseen current and Bill Gray historical element sets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from history_store import HistoryStore, history_entry
from update_catalog import cospar_prefix, git_commit, parse_classical_tle, tle_pairs


def current_entries(catalog: dict[str, Any], recorded_at_utc: str) -> Iterable[dict[str, Any]]:
    for record in catalog.get("records", []):
        for source in record.get("sources", []):
            yield history_entry(record, source, recorded_at_utc)


def bill_gray_paths(record: dict[str, Any], source: dict[str, Any], directory: Path) -> list[Path]:
    paths: set[Path] = set()
    prefix = cospar_prefix(record.get("cospar_id"))
    if prefix:
        paths.update(path for path in directory.glob(f"{prefix}*.tle") if path.is_file())
    current = source.get("bill_gray_file")
    if current and (directory / current).is_file():
        paths.add(directory / current)
    return sorted(paths, key=lambda path: path.name.casefold())


def bill_gray_entries(
    catalog: dict[str, Any], directory: Path, recorded_at_utc: str
) -> Iterable[dict[str, Any]]:
    commit = git_commit(directory)
    for record in catalog.get("records", []):
        base = next(
            (source for source in record.get("sources", []) if source.get("source") == "bill_gray"),
            None,
        )
        if not base:
            continue
        for path in bill_gray_paths(record, base, directory):
            for line0, line1, line2 in tle_pairs(path):
                orbit = parse_classical_tle(line0, line1, line2)
                if not orbit:
                    continue
                source = {
                    **base,
                    "source": "bill_gray",
                    "source_url": (
                        f"https://github.com/Bill-Gray/tles/blob/{commit or 'master'}/"
                        f"{quote(path.name)}"
                    ),
                    "source_commit": commit,
                    "bill_gray_file": path.name,
                    "bill_gray_name": line0 or base.get("bill_gray_name"),
                    "orbit": orbit,
                }
                yield history_entry(record, source, recorded_at_utc)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument("--bill-gray-dir", type=Path)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    recorded_at = catalog.get("generated_at_utc")
    if not recorded_at:
        raise ValueError("Catalog is missing generated_at_utc")

    store = HistoryStore(args.history_root, recorded_at)
    current_count = store.extend(current_entries(catalog, recorded_at))
    bill_gray_count = 0
    if args.bill_gray_dir and args.bill_gray_dir.exists():
        bill_gray_count = store.extend(bill_gray_entries(catalog, args.bill_gray_dir, recorded_at))
    shard = store.commit()
    if shard:
        print(
            f"Archived {shard['record_count']} unique rows to {shard['path']} "
            f"(current={current_count}, Bill Gray history={bill_gray_count})"
        )
    else:
        print("No unseen historical rows; history store unchanged")


if __name__ == "__main__":
    main()

