#!/usr/bin/env python3
"""Append-only compressed history storage for normalized orbit-source records."""

from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

HISTORY_SCHEMA_VERSION = "1.0.0"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def history_entry(record: dict[str, Any], source: dict[str, Any], recorded_at_utc: str) -> dict[str, Any]:
    """Convert a current source record into the stable history row schema."""
    entry = {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "recorded_at_utc": recorded_at_utc,
        "target_key": record.get("key"),
        "name": record.get("name"),
        "norad_cat_id": record.get("norad_cat_id"),
        "cospar_id": record.get("cospar_id"),
        "source": source.get("source"),
        "eligible": source.get("eligible"),
        "catalog_id": source.get("catalog_id"),
        "source_url": source.get("source_url"),
        "source_commit": source.get("source_commit"),
        "bill_gray_file": source.get("bill_gray_file"),
        "bill_gray_name": source.get("bill_gray_name"),
        "orbit": source.get("orbit") or {},
    }
    entry["fingerprint"] = entry_fingerprint(entry)
    return entry


def entry_fingerprint(entry: dict[str, Any]) -> str:
    """Hash only orbital identity fields so verification-time changes do not duplicate rows."""
    stable = {
        "target_key": entry.get("target_key"),
        "source": entry.get("source"),
        "catalog_id": entry.get("catalog_id"),
        "bill_gray_file": entry.get("bill_gray_file"),
        "orbit": entry.get("orbit") or {},
    }
    payload = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def iter_shard(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON in {path}:{line_number}") from exc


class HistoryStore:
    """Collect unseen rows and write one immutable gzip JSONL shard per run."""

    def __init__(self, root: Path, recorded_at_utc: str | None = None) -> None:
        self.root = root
        self.recorded_at_utc = recorded_at_utc or now_utc()
        self.fingerprint_path = root / "fingerprints.log"
        self.manifest_path = root / "manifest.json"
        self.known = self._load_fingerprints()
        self.pending_fingerprints: set[str] = set()
        self.pending: list[dict[str, Any]] = []

    def _load_fingerprints(self) -> set[str]:
        if not self.fingerprint_path.exists():
            return set()
        return {
            line.strip().split("\t", 1)[0]
            for line in self.fingerprint_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

    def add(self, entry: dict[str, Any]) -> bool:
        fingerprint = entry.get("fingerprint") or entry_fingerprint(entry)
        entry["fingerprint"] = fingerprint
        if fingerprint in self.known or fingerprint in self.pending_fingerprints:
            return False
        self.pending.append(entry)
        self.pending_fingerprints.add(fingerprint)
        return True

    def extend(self, entries: Iterable[dict[str, Any]]) -> int:
        return sum(1 for entry in entries if self.add(entry))

    def _manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"schema_version": HISTORY_SCHEMA_VERSION, "updated_at_utc": None, "shards": []}
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != HISTORY_SCHEMA_VERSION:
            raise ValueError("Unsupported history manifest schema")
        if not isinstance(manifest.get("shards"), list):
            raise ValueError("History manifest shards must be a list")
        return manifest

    def commit(self) -> dict[str, Any] | None:
        if not self.pending:
            return None

        self.pending.sort(
            key=lambda entry: (
                str(entry.get("source") or ""),
                str(entry.get("target_key") or ""),
                str((entry.get("orbit") or {}).get("epoch_utc") or ""),
                entry["fingerprint"],
            )
        )
        raw = "".join(
            json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for entry in self.pending
        ).encode("utf-8")
        compressed = gzip.compress(raw, compresslevel=9, mtime=0)
        payload_hash = hashlib.sha256(compressed).hexdigest()

        instant = parse_utc(self.recorded_at_utc) or datetime.now(timezone.utc)
        relative = Path("shards") / instant.strftime("%Y") / instant.strftime("%m")
        filename = f"history-{instant.strftime('%Y%m%dT%H%M%SZ')}-{payload_hash[:10]}.jsonl.gz"
        shard_path = self.root / relative / filename
        shard_path.parent.mkdir(parents=True, exist_ok=True)
        if shard_path.exists() and shard_path.read_bytes() != compressed:
            raise FileExistsError(f"Refusing to overwrite history shard: {shard_path}")
        shard_path.write_bytes(compressed)

        epochs = [
            (entry.get("orbit") or {}).get("epoch_utc")
            for entry in self.pending
            if (entry.get("orbit") or {}).get("epoch_utc")
        ]
        source_counts = dict(sorted(Counter(str(entry.get("source")) for entry in self.pending).items()))
        shard_info = {
            "path": shard_path.relative_to(self.root).as_posix(),
            "created_at_utc": self.recorded_at_utc,
            "record_count": len(self.pending),
            "source_counts": source_counts,
            "min_epoch_utc": min(epochs) if epochs else None,
            "max_epoch_utc": max(epochs) if epochs else None,
            "sha256": payload_hash,
            "uncompressed_bytes": len(raw),
            "compressed_bytes": len(compressed),
        }

        self.root.mkdir(parents=True, exist_ok=True)
        with self.fingerprint_path.open("a", encoding="utf-8", newline="\n") as stream:
            for entry in self.pending:
                stream.write(f"{entry['fingerprint']}\t{shard_info['path']}\n")

        manifest = self._manifest()
        manifest["updated_at_utc"] = self.recorded_at_utc
        manifest["shards"].append(shard_info)
        self.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self.known.update(self.pending_fingerprints)
        self.pending.clear()
        self.pending_fingerprints.clear()
        return shard_info

