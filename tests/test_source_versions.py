from pathlib import Path

from tools.fetch import GFC_VERSION, gfc_url


ROOT = Path(__file__).resolve().parents[1]


def test_external_gfc_matches_case_version() -> None:
    assert GFC_VERSION == "2025-v1.13"
    assert "GFC-2025-v1.13" in gfc_url("60N_040E", "lossyear")


def test_raster_cache_is_resolved_from_data_directory() -> None:
    source = (ROOT / "tools/extract_case_data.py").read_text(encoding="utf-8")
    assert 'data_dir / "cache" / "cci-biomass"' in source
    assert 'data_dir / "cache" / "hansen-gfc"' in source
    assert 'Path("data/cache/cci-biomass")' not in source
