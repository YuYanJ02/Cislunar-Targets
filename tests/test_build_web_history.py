from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_web_history import build_web_history  # noqa: E402
from history_store import HistoryStore, history_entry  # noqa: E402


def entry(source: str, epoch: str) -> dict:
    record = {"key": "NORAD:12345", "name": "TEST", "norad_cat_id": "12345", "cospar_id": "2001-001A"}
    source_record = {"source": source, "catalog_id": "12345", "orbit": {"epoch_utc": epoch, "semi_major_axis_km": 50000}}
    return history_entry(record, source_record, "2026-10-13T00:00:00Z")


class WebHistoryTests(unittest.TestCase):
    def test_builds_target_chunks_and_excludes_incomplete_spacetrack_month(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "history"
            output = Path(temporary) / "web"
            store = HistoryStore(root, "2026-10-13T00:00:00Z")
            store.extend([
                entry("spacetrack", "2026-09-15T00:00:00Z"),
                entry("spacetrack", "2026-10-12T00:00:00Z"),
                entry("bill_gray", "2026-10-12T00:00:00Z"),
            ])
            store.commit()
            (root / "gp_history_months.json").write_text(
                json.dumps({"months": [{"month": "2026-09", "status": "complete"}]}), encoding="utf-8"
            )

            index = build_web_history(root, output, bucket_count=4)
            target = index["targets"]["NORAD:12345"]
            self.assertEqual(target["count"], 2)
            self.assertEqual(target["source_counts"], {"bill_gray": 1, "spacetrack": 1})
            rows = []
            for chunk in target["chunks"]:
                with gzip.open(output / chunk["path"], "rt", encoding="utf-8") as stream:
                    rows.extend(json.load(stream)["records"])
            self.assertEqual({row["epoch_utc"] for row in rows}, {
                "2026-09-15T00:00:00Z", "2026-10-12T00:00:00Z"
            })


if __name__ == "__main__":
    unittest.main()

