from api.app import case_service


def test_catalog_area_is_available_without_heavy_rasters() -> None:
    result = case_service.published_area_result("RU_MORDOVIA_03", 2020, 2022)
    assert result["aoi_id"] == "RU_MORDOVIA_03"
    assert result["period"]["year_start"] == 2020
    assert result["period"]["year_end"] == 2022
    assert result["result_cache"]["used"] is True
    assert result["result_cache"]["manifest"] == "data/provenance_manifest.json"


def test_catalog_result_preserves_zero_vs_unavailable() -> None:
    result = case_service.published_area_result("RU_TVER_01", 2019, 2024)
    assert result["period"]["units"] == 0
    assert result["period"]["reason"]
