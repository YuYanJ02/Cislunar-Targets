#!/usr/bin/env python3
"""Validate the checked-in web catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.catalog.read_text(encoding="utf-8"))
    assert payload.get("schema_version") == "1.0.0", "unexpected schema version"
    records = payload.get("records")
    assert isinstance(records, list) and records, "catalog has no records"
    keys: set[str] = set()
    for record in records:
        key = record.get("key")
        assert key and key not in keys, f"duplicate or missing key: {key}"
        keys.add(key)
        assert record.get("name"), f"missing name: {key}"
        sources = record.get("sources", [])
        assert sources, f"missing sources: {key}"
        names = [source.get("source") for source in sources]
        assert len(names) == len(set(names)), f"duplicate source: {key}"
        assert set(names) <= {"spacetrack", "bill_gray"}, f"unknown source: {key}"
    print(f"Catalog valid: {len(records)} records, {len(keys)} unique keys")


if __name__ == "__main__":
    main()

