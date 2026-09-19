from __future__ import annotations

import json
from pathlib import Path

from tools.build_provenance_manifest import build, canonical_hash


ROOT = Path(__file__).resolve().parents[1]


def test_manifest_covers_every_published_area() -> None:
    manifest = build()
    payload = json.loads((ROOT / "app/src/data/case-data.json").read_text(encoding="utf-8"))
    expected = {area["aoi_id"] for area in payload["areas"]}
    actual = {area["aoi_id"] for area in manifest["areas"]}
    assert actual == expected


def test_manifest_result_hashes_match_published_payload() -> None:
    manifest = build()
    payload = json.loads((ROOT / "app/src/data/case-data.json").read_text(encoding="utf-8"))
    hashes = {area["aoi_id"]: area["published_result_sha256"] for area in manifest["areas"]}
    for area in payload["areas"]:
        assert hashes[area["aoi_id"]] == canonical_hash(area)


def test_derived_and_case_areas_are_not_confused() -> None:
    manifest = build()
    origins = {area["aoi_id"]: area["origin"] for area in manifest["areas"]}
    assert origins["RU_TVER_01"] == "provided_case_area"
    assert origins["RU_TVER_05"] == "team_derived_area_from_open_tiles"
