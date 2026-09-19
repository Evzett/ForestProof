"""Build a deterministic audit manifest for every published area result.

The manifest does not claim that a hash validates scientific correctness. It
answers the narrower audit question: which geometry, baseline rows, generated
result, maps, methodology files and calculation code produced each published
area. Re-running this command after a data or code change makes that change
visible instead of silently retaining stale numbers.

    python tools/build_provenance_manifest.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_AREAS = {
    "RU_TVER_01",
    "RU_VOLOGDA_02",
    "RU_MORDOVIA_03",
    "RU_MORDOVIA_04",
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    return sha256_bytes(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def relative_file(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def build() -> dict[str, Any]:
    data_dir = ROOT / "data"
    payload_path = ROOT / "app" / "src" / "data" / "case-data.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    with (data_dir / "methodology" / "baseline.csv").open(encoding="utf-8-sig") as handle:
        baseline = list(csv.DictReader(handle))
    geometries = json.loads((data_dir / "areas.geojson").read_text(encoding="utf-8-sig"))
    geometry_by_id = {
        feature["properties"]["aoi_id"]: feature["geometry"]
        for feature in geometries["features"]
    }

    code_files = [
        ROOT / "forestproof_core" / "case_calculation.py",
        ROOT / "tools" / "extract_case_data.py",
        ROOT / "tools" / "geotiff.py",
    ]
    methodology_files = [
        data_dir / "methodology" / "parameters.csv",
        data_dir / "methodology" / "baseline.csv",
        data_dir / "sources.csv",
    ]

    areas = []
    for area in payload["areas"]:
        aoi_id = area["aoi_id"]
        area_baseline = [row for row in baseline if row["aoi_id"] == aoi_id]
        map_files = []
        for name in ("stock", "change", "loss"):
            path = ROOT / "app" / "public" / "maps" / f"{aoi_id}_{name}.png"
            if path.exists():
                map_files.append(relative_file(path))
        published_gfc = (area.get("maps") or {}).get("source_gfc")
        uses_legacy_gfc = bool(published_gfc and "v1.12" in published_gfc)
        areas.append(
            {
                "aoi_id": aoi_id,
                "origin": (
                    "provided_case_area"
                    if aoi_id in OFFICIAL_AREAS
                    else "team_derived_area_from_open_tiles"
                ),
                "geometry_sha256": canonical_hash(geometry_by_id[aoi_id]),
                "baseline_rows_sha256": canonical_hash(area_baseline),
                "published_result_sha256": canonical_hash(area),
                "years": [point["year"] for point in area["series"]],
                "maps": map_files,
                "source_products": [
                    "ESA CCI Biomass v7.0",
                    published_gfc or "Hansen Global Forest Change: no published map source",
                    "MODIS MCD64A1 v6.1 where available",
                    "Sentinel-2 L2A where available",
                ],
                "reproduction": {
                    "command": (
                        f"python tools/extract_case_data.py --data data --out app/src/data/case-data.json "
                        f"--maps app/public/maps --only {aoi_id} --verify"
                    ),
                    "required_cache": (
                        "archived Hansen GFC 2024 v1.12 cache used for this published result; "
                        "regeneration with current v1.13 must create a new result version"
                        if uses_legacy_gfc
                        else "case archive or current versioned open-source cache"
                    ),
                },
            }
        )

    return {
        "schema_version": "1.0",
        "scope": "published demo results; hashes identify inputs and outputs but do not replace scientific validation",
        "generated_from": payload["generated_from"],
        "published_payload": relative_file(payload_path),
        "calculation_code": [relative_file(path) for path in code_files],
        "methodology": [relative_file(path) for path in methodology_files],
        "areas": areas,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "provenance_manifest.json",
    )
    args = parser.parse_args()
    result = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"written {args.out}: {len(result['areas'])} areas")


if __name__ == "__main__":
    main()
