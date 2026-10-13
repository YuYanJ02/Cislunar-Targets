#!/usr/bin/env python3
"""Validate history manifests and the most recent immutable shards."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from history_store import HISTORY_SCHEMA_VERSION, entry_fingerprint, iter_shard


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("history_root", type=Path)
    parser.add_argument("--recent", type=int, default=5)
    args = parser.parse_args()

    manifest_path = args.history_root / "manifest.json"
    fingerprints_path = args.history_root / "fingerprints.log"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("schema_version") == HISTORY_SCHEMA_VERSION, "unexpected history schema"
    shards = manifest.get("shards")
    assert isinstance(shards, list) and shards, "history manifest has no shards"

    known = [
        line.split("\t", 1)[0]
        for line in fingerprints_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(known) == len(set(known)), "duplicate fingerprints in history index"
    indexed = set(known)

    checked_rows = 0
    for shard in shards[-args.recent :] if args.recent else shards:
        relative = Path(shard["path"])
        path = (args.history_root / relative).resolve()
        assert path.is_relative_to(args.history_root.resolve()), f"shard outside history root: {relative}"
        compressed = path.read_bytes()
        assert hashlib.sha256(compressed).hexdigest() == shard["sha256"], f"SHA mismatch: {relative}"
        entries = list(iter_shard(path))
        assert len(entries) == shard["record_count"], f"record count mismatch: {relative}"
        local: set[str] = set()
        for entry in entries:
            fingerprint = entry.get("fingerprint")
            assert fingerprint == entry_fingerprint(entry), f"fingerprint mismatch: {relative}"
            assert fingerprint in indexed, f"unindexed fingerprint: {relative}"
            assert fingerprint not in local, f"duplicate row in shard: {relative}"
            local.add(fingerprint)
        checked_rows += len(entries)
    print(f"History valid: {len(shards)} shards, {len(indexed)} indexed rows, {checked_rows} rows checked")


if __name__ == "__main__":
    main()

