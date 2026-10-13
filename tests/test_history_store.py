from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from archive_history import bill_gray_entries, current_entries  # noqa: E402
from history_store import HistoryStore, iter_shard  # noqa: E402


def sample_catalog(epoch: str = "2026-01-01T00:00:00Z") -> dict:
    return {
        "schema_version": "1.0.0",
        "generated_at_utc": "2026-01-02T00:00:00Z",
        "records": [
            {
                "key": "NORAD:12345",
                "name": "TEST TARGET",
                "norad_cat_id": "12345",
                "cospar_id": "2001-001A",
                "sources": [
                    {
                        "source": "spacetrack",
                        "eligible": True,
                        "catalog_id": "12345",
                        "last_verified_utc": "2026-01-02T00:00:00Z",
                        "orbit": {"epoch_utc": epoch, "gp_id": 99, "semi_major_axis_km": 50000.0},
                    }
                ],
            }
        ],
    }


class HistoryStoreTests(unittest.TestCase):
    def test_append_only_deduplication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "history"
            catalog = sample_catalog()
            first = HistoryStore(root, catalog["generated_at_utc"])
            self.assertEqual(first.extend(current_entries(catalog, catalog["generated_at_utc"])), 1)
            first_shard = first.commit()
            self.assertIsNotNone(first_shard)

            duplicate = HistoryStore(root, "2026-01-03T00:00:00Z")
            self.assertEqual(duplicate.extend(current_entries(catalog, "2026-01-03T00:00:00Z")), 0)
            self.assertIsNone(duplicate.commit())

            changed_catalog = sample_catalog("2026-01-02T00:00:00Z")
            changed = HistoryStore(root, "2026-01-03T00:00:00Z")
            self.assertEqual(changed.extend(current_entries(changed_catalog, "2026-01-03T00:00:00Z")), 1)
            changed.commit()

            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["shards"]), 2)
            rows = [
                row
                for shard in manifest["shards"]
                for row in iter_shard(root / shard["path"])
            ]
            self.assertEqual([row["orbit"]["epoch_utc"] for row in rows], [
                "2026-01-01T00:00:00Z",
                "2026-01-02T00:00:00Z",
            ])

    def test_bill_gray_file_keeps_every_tle_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            tle = """TEST TARGET
1 12345U 01001A   26001.00000000  .00000000  00000-0  00000-0 0  9999
2 12345  10.0000  20.0000 1000000  30.0000  40.0000  1.00000000    01
TEST TARGET
1 12345U 01001A   26002.00000000  .00000000  00000-0  00000-0 0  9990
2 12345  10.0000  21.0000 1000000  31.0000  41.0000  1.00000000    02
"""
            (directory / "01001a.tle").write_text(tle, encoding="utf-8")
            catalog = sample_catalog()
            catalog["records"][0]["sources"] = [
                {
                    "source": "bill_gray",
                    "eligible": True,
                    "bill_gray_file": "01001a.tle",
                    "catalog_id": "12345",
                    "orbit": {},
                }
            ]
            rows = list(bill_gray_entries(catalog, directory, "2026-01-03T00:00:00Z"))
            self.assertEqual(len(rows), 2)
            self.assertNotEqual(rows[0]["fingerprint"], rows[1]["fingerprint"])


if __name__ == "__main__":
    unittest.main()

