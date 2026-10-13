#!/usr/bin/env python3
"""Query compressed orbit-history shards without a database server."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from history_store import iter_shard, parse_utc


def matches(entry: dict[str, Any], args: argparse.Namespace) -> bool:
    if args.source and entry.get("source") != args.source:
        return False
    if args.norad and str(entry.get("norad_cat_id") or "") != args.norad:
        return False
    if args.cospar and str(entry.get("cospar_id") or "").upper() != args.cospar.upper():
        return False
    epoch = parse_utc((entry.get("orbit") or {}).get("epoch_utc"))
    if args.start and (epoch is None or epoch < args.start):
        return False
    if args.end and (epoch is None or epoch > args.end):
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history-root", type=Path, default=Path("data/history"))
    parser.add_argument("--norad")
    parser.add_argument("--cospar")
    parser.add_argument("--source", choices=("spacetrack", "bill_gray"))
    parser.add_argument("--start", help="Earliest epoch, ISO 8601 UTC")
    parser.add_argument("--end", help="Latest epoch, ISO 8601 UTC")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    args.start = parse_utc(args.start)
    args.end = parse_utc(args.end)
    if args.limit <= 0:
        raise ValueError("--limit must be positive")

    manifest_path = args.history_root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"History manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    for shard in manifest.get("shards", []):
        if args.source and not (shard.get("source_counts") or {}).get(args.source):
            continue
        for entry in iter_shard(args.history_root / shard["path"]):
            if matches(entry, args):
                results.append(entry)

    results.sort(
        key=lambda entry: (
            str((entry.get("orbit") or {}).get("epoch_utc") or ""),
            str(entry.get("recorded_at_utc") or ""),
        )
    )
    results = results[-args.limit :]
    text = json.dumps(results, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {len(results)} rows to {args.output}")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()

