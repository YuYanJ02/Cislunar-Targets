#!/usr/bin/env python3
"""Refresh Space-Track and Bill Gray source entries in the static catalog."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

EARTH_MU_KM3_S2 = 398600.4418
EARTH_RADIUS_KM = 6378.137
GEO_SEMIMAJOR_AXIS_KM = 42164.0
SPACE_TRACK_BASE = "https://www.space-track.org"
SPACE_TRACK_QUERY = (
    "/basicspacedata/query/class/gp/OBJECT_TYPE/PAYLOAD/"
    "LAUNCH_DATE/%3E2000-12-31/DECAY_DATE/null-val/"
    "SEMIMAJOR_AXIS/%3E42164/orderby/NORAD_CAT_ID/format/json"
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def maybe_float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_tle_epoch(line1: str) -> str | None:
    try:
        year2 = int(line1[18:20])
        year = 1900 + year2 if year2 >= 57 else 2000 + year2
        day = float(line1[20:32])
        epoch = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=day - 1)
        return epoch.isoformat().replace("+00:00", "Z")
    except (ValueError, IndexError):
        return None


def parse_classical_tle(line0: str | None, line1: str, line2: str) -> dict[str, Any] | None:
    if not line1.startswith("1 ") or not line2.startswith("2 "):
        return None
    ephemeris_type = line1[62:63].strip() or "0"
    if ephemeris_type.upper() == "H":
        return {
            "epoch_utc": parse_tle_epoch(line1), "ephemeris_type": "H",
            "tle_line0": line0, "tle_line1": line1, "tle_line2": line2,
            "semi_major_axis_method": "state_vector_extension_unparsed",
        }
    try:
        inclination = float(line2[8:16])
        raan = float(line2[17:25])
        eccentricity = float(f"0.{line2[26:33].strip()}")
        arg_pericenter = float(line2[34:42])
        mean_anomaly = float(line2[43:51])
        mean_motion = float(line2[52:63])
        if mean_motion <= 0:
            return None
        period_days = 1.0 / mean_motion
        mean_motion_rad_s = mean_motion * 2.0 * math.pi / 86400.0
        semimajor = (EARTH_MU_KM3_S2 / (mean_motion_rad_s ** 2)) ** (1.0 / 3.0)
        return {
            "epoch_utc": parse_tle_epoch(line1),
            "semi_major_axis_km": round(semimajor, 6),
            "period_days": round(period_days, 10),
            "ephemeris_type": ephemeris_type,
            "semi_major_axis_method": "tle_mean_motion",
            "eccentricity": eccentricity,
            "inclination_deg": inclination,
            "raan_deg": raan,
            "arg_pericenter_deg": arg_pericenter,
            "mean_anomaly_deg": mean_anomaly,
            "mean_motion_rev_day": mean_motion,
            "perigee_altitude_km": round(semimajor * (1.0 - eccentricity) - EARTH_RADIUS_KM, 3),
            "apogee_altitude_km": round(semimajor * (1.0 + eccentricity) - EARTH_RADIUS_KM, 3),
            "tle_line0": line0,
            "tle_line1": line1,
            "tle_line2": line2,
        }
    except (ValueError, IndexError):
        return None


def tle_pairs(path: Path) -> list[tuple[str | None, str, str]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    pairs: list[tuple[str | None, str, str]] = []
    previous_name: str | None = None
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        if line.startswith("1 ") and index + 1 < len(lines) and lines[index + 1].startswith("2 "):
            pairs.append((previous_name, line, lines[index + 1].rstrip()))
            index += 2
            continue
        if line and not line.startswith("#") and not line.startswith("1 ") and not line.startswith("2 "):
            previous_name = line
        index += 1
    return pairs


def latest_tle(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    best: tuple[datetime, dict[str, Any], str | None] | None = None
    for name, line1, line2 in tle_pairs(path):
        orbit = parse_classical_tle(name, line1, line2)
        if not orbit:
            continue
        try:
            epoch = datetime.fromisoformat((orbit.get("epoch_utc") or "1900-01-01T00:00:00+00:00").replace("Z", "+00:00"))
        except ValueError:
            epoch = datetime(1900, 1, 1, tzinfo=timezone.utc)
        if best is None or epoch > best[0]:
            best = (epoch, orbit, name)
    return (best[1], best[2]) if best else (None, None)


def space_track_source(item: dict[str, Any], verified: str) -> dict[str, Any]:
    semimajor = maybe_float(item.get("SEMIMAJOR_AXIS"))
    mean_motion = maybe_float(item.get("MEAN_MOTION"))
    period = maybe_float(item.get("PERIOD"))
    period_days = period / 1440.0 if period is not None else (1.0 / mean_motion if mean_motion else None)
    return {
        "source": "spacetrack",
        "eligible": True,
        "last_verified_utc": verified,
        "source_url": f"{SPACE_TRACK_BASE}{SPACE_TRACK_QUERY}",
        "source_commit": None,
        "bill_gray_file": None,
        "bill_gray_name": None,
        "catalog_id": str(item.get("NORAD_CAT_ID")) if item.get("NORAD_CAT_ID") is not None else None,
        "orbit": {
            "epoch_utc": item.get("EPOCH"),
            "semi_major_axis_km": semimajor,
            "period_days": period_days,
            "ephemeris_type": item.get("EPHEMERIS_TYPE"),
            "semi_major_axis_method": "space_track_gp",
            "eccentricity": maybe_float(item.get("ECCENTRICITY")),
            "inclination_deg": maybe_float(item.get("INCLINATION")),
            "raan_deg": maybe_float(item.get("RA_OF_ASC_NODE")),
            "arg_pericenter_deg": maybe_float(item.get("ARG_OF_PERICENTER")),
            "mean_anomaly_deg": maybe_float(item.get("MEAN_ANOMALY")),
            "mean_motion_rev_day": mean_motion,
            "mean_motion_dot": maybe_float(item.get("MEAN_MOTION_DOT")),
            "mean_motion_ddot": maybe_float(item.get("MEAN_MOTION_DDOT")),
            "bstar": maybe_float(item.get("BSTAR")),
            "element_set_no": item.get("ELEMENT_SET_NO"),
            "rev_at_epoch": item.get("REV_AT_EPOCH"),
            "perigee_altitude_km": maybe_float(item.get("PERIAPSIS")),
            "apogee_altitude_km": maybe_float(item.get("APOAPSIS")),
            "center_name": item.get("CENTER_NAME"),
            "ref_frame": item.get("REF_FRAME"),
            "time_system": item.get("TIME_SYSTEM"),
            "mean_element_theory": item.get("MEAN_ELEMENT_THEORY"),
            "ccsds_omm_version": item.get("CCSDS_OMM_VERS"),
            "creation_date_utc": item.get("CREATION_DATE"),
            "originator": item.get("ORIGINATOR"),
            "gp_id": item.get("GP_ID"),
            "tle_line0": item.get("TLE_LINE0"),
            "tle_line1": item.get("TLE_LINE1"),
            "tle_line2": item.get("TLE_LINE2"),
        },
    }


def fetch_space_track(username: str, password: str) -> list[dict[str, Any]]:
    import requests

    with requests.Session() as session:
        response = session.post(
            f"{SPACE_TRACK_BASE}/ajaxauth/login",
            data={"identity": username, "password": password}, timeout=45,
        )
        response.raise_for_status()
        response = session.get(f"{SPACE_TRACK_BASE}{SPACE_TRACK_QUERY}", timeout=120)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Space-Track GP response is not a JSON list")
        session.get(f"{SPACE_TRACK_BASE}/ajaxauth/logout", timeout=30)
        return payload


def record_key(norad: Any, cospar: Any, fallback: str) -> str:
    if norad not in (None, ""):
        return f"NORAD:{str(norad).strip()}"
    if cospar:
        return f"COSPAR:{str(cospar).strip().upper()}"
    return fallback


def make_record_from_gp(item: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    norad = str(item.get("NORAD_CAT_ID")) if item.get("NORAD_CAT_ID") is not None else None
    cospar = item.get("OBJECT_ID")
    return {
        "key": record_key(norad, cospar, f"ST:{norad or cospar}"),
        "name": item.get("OBJECT_NAME") or f"NORAD {norad}",
        "norad_cat_id": norad,
        "cospar_id": cospar,
        "aliases": [],
        "object_type": "spacecraft",
        "orbit_regime": "XGEO",
        "primary_body": "Earth",
        "identity_status": "confirmed",
        "mission_status": "unknown",
        "priority": "medium",
        "notes": ["DECAY_DATE 为空表示未记录再入，不等于目标仍正常运行。"],
        "eligible": True,
        "sources": [source],
    }


def replace_source(record: dict[str, Any], source: dict[str, Any]) -> None:
    record["sources"] = [item for item in record.get("sources", []) if item.get("source") != source["source"]]
    record["sources"].append(source)
    record["eligible"] = any(bool(item.get("eligible")) for item in record["sources"])


def merge_space_track(catalog: dict[str, Any], payload: list[dict[str, Any]]) -> set[str]:
    verified = now_utc()
    by_key = {record["key"]: record for record in catalog["records"]}
    fresh_keys: set[str] = set()
    for item in payload:
        source = space_track_source(item, verified)
        key = record_key(item.get("NORAD_CAT_ID"), item.get("OBJECT_ID"), f"ST:{item.get('NORAD_CAT_ID')}")
        record = by_key.get(key)
        if record is None:
            record = make_record_from_gp(item, source)
            catalog["records"].append(record)
            by_key[key] = record
        else:
            replace_source(record, source)
            record["name"] = item.get("OBJECT_NAME") or record["name"]
            record["norad_cat_id"] = str(item.get("NORAD_CAT_ID"))
            record["cospar_id"] = item.get("OBJECT_ID") or record.get("cospar_id")
        fresh_keys.add(key)

    for record in catalog["records"]:
        if record["key"] not in fresh_keys:
            record["sources"] = [item for item in record.get("sources", []) if item.get("source") != "spacetrack"]
            record["eligible"] = any(bool(item.get("eligible")) for item in record["sources"])
    catalog["records"] = [record for record in catalog["records"] if record.get("sources")]
    return {str(item.get("NORAD_CAT_ID")) for item in payload if item.get("NORAD_CAT_ID") is not None}


def git_commit(directory: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(directory), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def cospar_prefix(cospar_id: str | None) -> str | None:
    if not cospar_id:
        return None
    match = re.fullmatch(r"(\d{4})-(\d{3})([A-Z0-9]+)", cospar_id.strip().upper())
    if not match:
        return None
    return f"{match.group(1)[2:]}{match.group(2)}{match.group(3).lower()}"


def best_bill_gray_file(directory: Path, current: str | None, cospar_id: str | None) -> Path | None:
    candidates: list[Path] = []
    prefix = cospar_prefix(cospar_id)
    if prefix:
        candidates.extend(directory.glob(f"{prefix}*.tle"))
    if current:
        path = directory / current
        if path.exists() and path not in candidates:
            candidates.append(path)
    candidates = [path for path in candidates if path.is_file()]
    if not candidates:
        return None
    def score(path: Path) -> tuple[int, int, str]:
        stem = path.stem.lower()
        suffix = stem[len(prefix):] if prefix and stem.startswith(prefix) else ""
        return (1 if suffix.isdigit() else 0, int(suffix) if suffix.isdigit() else -1, stem)
    return max(candidates, key=score)


def update_bill_gray(catalog: dict[str, Any], directory: Path, current_st_norads: set[str]) -> None:
    verified = now_utc()
    commit = git_commit(directory)
    by_norad = {str(record.get("norad_cat_id")): record for record in catalog["records"] if record.get("norad_cat_id")}

    for record in catalog["records"]:
        previous = next((item for item in record.get("sources", []) if item.get("source") == "bill_gray"), None)
        if not previous:
            continue
        source_file = best_bill_gray_file(directory, previous.get("bill_gray_file"), record.get("cospar_id"))
        if not source_file:
            previous["update_status"] = "source_file_missing"
            continue
        orbit, line0 = latest_tle(source_file)
        if orbit is None:
            previous["update_status"] = "no_parseable_element_set"
            continue
        if orbit.get("ephemeris_type") == "H":
            preserved = previous.get("orbit", {})
            orbit = {**preserved, **{key: value for key, value in orbit.items() if value is not None}}
        semimajor = maybe_float(orbit.get("semi_major_axis_km"))
        eligible = semimajor is None or semimajor > GEO_SEMIMAJOR_AXIS_KM
        source = {
            **previous,
            "source": "bill_gray",
            "eligible": eligible,
            "last_verified_utc": verified,
            "source_url": f"https://github.com/Bill-Gray/tles/blob/{commit or 'master'}/{quote(source_file.name)}",
            "source_commit": commit,
            "bill_gray_file": source_file.name,
            "bill_gray_name": line0 or previous.get("bill_gray_name"),
            "orbit": orbit,
            "update_status": "updated",
        }
        replace_source(record, source)

    for path in directory.glob("*.tle"):
        orbit, line0 = latest_tle(path)
        if not orbit or orbit.get("ephemeris_type") == "H":
            continue
        semimajor = maybe_float(orbit.get("semi_major_axis_km"))
        if semimajor is None or semimajor <= GEO_SEMIMAJOR_AXIS_KM:
            continue
        line1 = orbit.get("tle_line1") or ""
        norad = line1[2:7].strip()
        if not norad or norad not in current_st_norads:
            continue
        record = by_norad.get(norad)
        if not record or any(item.get("source") == "bill_gray" for item in record.get("sources", [])):
            continue
        source = {
            "source": "bill_gray", "eligible": True, "last_verified_utc": verified,
            "source_url": f"https://github.com/Bill-Gray/tles/blob/{commit or 'master'}/{quote(path.name)}",
            "source_commit": commit, "bill_gray_file": path.name,
            "bill_gray_name": line0, "catalog_id": norad, "orbit": orbit,
            "update_status": "discovered_by_norad_match",
        }
        replace_source(record, source)


def validate_catalog(catalog: dict[str, Any]) -> None:
    if catalog.get("schema_version") != "1.0.0":
        raise ValueError("Unsupported catalog schema")
    seen: set[str] = set()
    for record in catalog.get("records", []):
        key = record.get("key")
        if not key or key in seen:
            raise ValueError(f"Missing or duplicate record key: {key}")
        seen.add(key)
        sources = [item.get("source") for item in record.get("sources", [])]
        if not sources or len(sources) != len(set(sources)):
            raise ValueError(f"Missing or duplicate sources for {key}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--bill-gray-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    username = os.environ.get("SPACETRACK_USERNAME", "").strip()
    password = os.environ.get("SPACETRACK_PASSWORD", "").strip()
    current_st_norads = {
        str(record.get("norad_cat_id")) for record in catalog["records"]
        if any(item.get("source") == "spacetrack" for item in record.get("sources", [])) and record.get("norad_cat_id")
    }

    if username and password:
        print("Refreshing Space-Track GP data", file=sys.stderr)
        payload = fetch_space_track(username, password)
        current_st_norads = merge_space_track(catalog, payload)
        catalog.setdefault("refresh", {})["space_track"] = {"status": "updated", "at_utc": now_utc(), "count": len(payload)}
    else:
        print("Space-Track credentials are not configured; retaining existing snapshot", file=sys.stderr)
        catalog.setdefault("refresh", {})["space_track"] = {"status": "credentials_missing", "at_utc": now_utc()}

    if args.bill_gray_dir and args.bill_gray_dir.exists():
        print("Refreshing Bill Gray records", file=sys.stderr)
        update_bill_gray(catalog, args.bill_gray_dir, current_st_norads)
        count = sum(any(item.get("source") == "bill_gray" for item in record.get("sources", [])) for record in catalog["records"])
        catalog.setdefault("refresh", {})["bill_gray"] = {"status": "updated", "at_utc": now_utc(), "count": count}
    else:
        catalog.setdefault("refresh", {})["bill_gray"] = {"status": "source_missing", "at_utc": now_utc()}

    catalog["generated_at_utc"] = now_utc()
    catalog["records"] = sorted(catalog["records"], key=lambda item: (item.get("name", "").casefold(), item["key"]))
    validate_catalog(catalog)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(catalog['records'])} unified records to {args.output}")


if __name__ == "__main__":
    main()
