#!/usr/bin/env python3
"""Build target-addressable history bundles for the static GitHub Pages app."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from history_store import iter_shard, parse_utc

WEB_HISTORY_SCHEMA_VERSION = "1.0.0"
DEFAULT_BUCKET_COUNT = 64


def target_bucket(target_key: str, bucket_count: int) -> int:
    return int.from_bytes(hashlib.sha256(target_key.encode("utf-8")).digest()[:2], "big") % bucket_count


def load_completed_months(history_root: Path) -> set[str]:
    path = history_root / "gp_history_months.json"
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(item.get("month"))
        for item in payload.get("completed", [])
        if isinstance(item, dict) and item.get("month")
    }


def public_row(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_key": entry.get("target_key"),
        "source": entry.get("source"),
        "epoch_utc": (entry.get("orbit") or {}).get("epoch_utc"),
        "recorded_at_utc": entry.get("recorded_at_utc"),
        "source_url": entry.get("source_url"),
        "source_commit": entry.get("source_commit"),
        "bill_gray_file": entry.get("bill_gray_file"),
        "fingerprint": entry.get("fingerprint"),
        "orbit": entry.get("orbit") or {},
    }


def build_web_history(history_root: Path, output_root: Path, bucket_count: int = DEFAULT_BUCKET_COUNT) -> dict[str, Any]:
    manifest_path = history_root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"History manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    completed_months = load_completed_months(history_root)

    groups: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    targets: dict[str, dict[str, Any]] = {}
    target_group_counts: dict[str, Counter[tuple[str, str, int]]] = defaultdict(Counter)
    seen: set[str] = set()
    skipped = 0

    for shard in manifest.get("shards", []):
        for entry in iter_shard(history_root / shard["path"]):
            target_key = str(entry.get("target_key") or "")
            source = str(entry.get("source") or "")
            epoch = (entry.get("orbit") or {}).get("epoch_utc")
            instant = parse_utc(epoch)
            fingerprint = str(entry.get("fingerprint") or "")
            if not target_key or source not in {"spacetrack", "bill_gray"} or not instant:
                skipped += 1
                continue
            if fingerprint and fingerprint in seen:
                continue
            if fingerprint:
                seen.add(fingerprint)

            if source == "spacetrack":
                period = instant.strftime("%Y-%m")
                if period not in completed_months:
                    continue
            else:
                period = instant.strftime("%Y")

            bucket = target_bucket(target_key, bucket_count)
            group_key = (source, period, bucket)
            row = public_row(entry)
            groups[group_key].append(row)
            target_group_counts[target_key][group_key] += 1

            target = targets.setdefault(target_key, {
                "name": entry.get("name"),
                "norad_cat_id": entry.get("norad_cat_id"),
                "cospar_id": entry.get("cospar_id"),
                "count": 0,
                "earliest_epoch_utc": epoch,
                "latest_epoch_utc": epoch,
                "source_counts": Counter(),
            })
            target["count"] += 1
            target["earliest_epoch_utc"] = min(target["earliest_epoch_utc"], epoch)
            target["latest_epoch_utc"] = max(target["latest_epoch_utc"], epoch)
            target["source_counts"][source] += 1

    output_root.mkdir(parents=True, exist_ok=True)
    group_paths: dict[tuple[str, str, int], str] = {}
    for group_key, rows in sorted(groups.items()):
        source, period, bucket = group_key
        rows.sort(key=lambda row: (row.get("epoch_utc") or "", row.get("target_key") or "", row.get("fingerprint") or ""))
        relative = Path("chunks") / source / period / f"bucket-{bucket:02d}.json.gz"
        path = output_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": WEB_HISTORY_SCHEMA_VERSION,
            "source": source,
            "period": period,
            "bucket": bucket,
            "records": rows,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        path.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
        group_paths[group_key] = relative.as_posix()

    indexed_targets: dict[str, dict[str, Any]] = {}
    for target_key, target in sorted(targets.items()):
        target["source_counts"] = dict(sorted(target["source_counts"].items()))
        target["chunks"] = [
            {
                "path": group_paths[group_key],
                "source": group_key[0],
                "period": group_key[1],
                "count": count,
            }
            for group_key, count in sorted(target_group_counts[target_key].items())
        ]
        indexed_targets[target_key] = target

    index = {
        "schema_version": WEB_HISTORY_SCHEMA_VERSION,
        "generated_at_utc": manifest.get("updated_at_utc"),
        "bucket_count": bucket_count,
        "completed_spacetrack_months": sorted(completed_months),
        "target_count": len(indexed_targets),
        "record_count": sum(target["count"] for target in indexed_targets.values()),
        "skipped_record_count": skipped,
        "targets": indexed_targets,
    }
    (output_root / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-root", type=Path, default=Path("data/history"))
    parser.add_argument("--output", type=Path, default=Path("public/data/history"))
    parser.add_argument("--bucket-count", type=int, default=DEFAULT_BUCKET_COUNT)
    args = parser.parse_args()
    if args.bucket_count < 1:
        parser.error("--bucket-count must be positive")
    index = build_web_history(args.history_root, args.output, args.bucket_count)
    print(f"Built web history: {index['record_count']} rows for {index['target_count']} targets")


if __name__ == "__main__":
    main()

