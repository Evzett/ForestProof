"""Раздел 9 контракта — мок-набор. Заполняет БД тремя демо-участками
(расхождение >20%… точнее, значимое по AGB; без расхождения; territory_only),
каталогом реестра и списком наблюдения, плюс пишет геометрии и превью на
диск — ровно то, что должен отдавать API раздела 7 и 12 без сети (NFR-01).

Использует те же реальные проект/компания/регистрационный номер, что и
текущий мок фронтенда (`app/src/data/mock.ts`), скорректированные под явные
правила контракта, которые фронтенд пока не полностью отражает — например
`confidence` события "high/medium/low" (не "moderate", это отдельный набор
значений для `measurement_confidence`, раздел 0/1/3) и area_kind-корректную
сверку площади (раздел 2, П3 из docs/pravki.md).

Запуск (после `alembic upgrade head`):
    docker compose exec api python -m app.seed
Идемпотентно: очищает свои же таблицы перед вставкой, чтобы прогон дважды
не плодил дубликаты (внешние ключи требуют удаления в обратном порядке).
"""

import json
import math
from datetime import date, datetime, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app import models
from app.config import API_ROOT
from app.database import SessionLocal
from app.hashing import compute_input_hash
from app.previews import render_fallback_preview

CARBON_FRACTION = 0.47
CO2_FACTOR = 3.6667


def co2_equiv_t_ha(agb_t_ha: float) -> float:
    return round(agb_t_ha * CARBON_FRACTION * CO2_FACTOR, 2)


def make_polygon(center_lon: float, center_lat: float, target_area_ha: float, *, n_points: int = 14, wobble_seed: float = 0.0) -> dict:
    """Синтетический, но геометрически валидный многоугольник нужной
    примерной площади — не настоящая граница участка (её даёт Р4/Р5),
    только чтобы `/geometry` и превью были рабочими офлайн-файлами."""
    lat_rad = math.radians(center_lat)
    m_per_deg_lon = (math.pi / 180) * 6_371_000.0 * math.cos(lat_rad)
    m_per_deg_lat = (math.pi / 180) * 6_371_000.0
    target_area_m2 = target_area_ha * 10_000.0
    aspect = 1.3
    ry_m = math.sqrt(target_area_m2 / (math.pi * aspect))
    rx_m = ry_m * aspect

    coords = []
    for i in range(n_points):
        theta = 2 * math.pi * i / n_points
        wobble = 1 + 0.12 * math.sin(theta * 3 + wobble_seed)
        x_m = rx_m * math.cos(theta) * wobble
        y_m = ry_m * math.sin(theta) * wobble
        lon = center_lon + x_m / m_per_deg_lon
        lat = center_lat + y_m / m_per_deg_lat
        coords.append([round(lon, 6), round(lat, 6)])
    coords.append(coords[0])
    return {"type": "Polygon", "coordinates": [coords]}


def write_geometry(project_id: str, geometry: dict) -> str:
    rel_path = f"data/polygons/{project_id}.geojson"
    path = API_ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    feature = {"type": "Feature", "properties": {"project_id": project_id}, "geometry": geometry}
    path.write_text(json.dumps(feature, ensure_ascii=False), encoding="utf-8")
    return rel_path


def write_preview(geometry: dict, calc_id: str, observation_date: str, event_points: list[tuple[float, float]] | None = None) -> str:
    rel_path = f"data/previews/{calc_id}.png"
    render_fallback_preview(
        geometry,
        API_ROOT / rel_path,
        calc_id=calc_id,
        observation_date=observation_date,
        event_points=event_points,
    )
    return rel_path


def clear(db: Session) -> None:
    # Порядок — от зависимых к независимым (FK).
    for model in (
        models.WatchlistEntry,
        models.Plot,
        models.GeometryUpload,
        models.RegistryCatalogEntry,
        models.RegistryImportMeta,
        models.Calculation,
        models.DisturbanceEvent,
        models.Observation,
        models.ProjectClaims,
        models.ProjectRegistry,
        models.Project,
    ):
        db.execute(delete(model))
    db.commit()


def seed_proj_01(db: Session) -> None:
    """Нижне-Енисейский, РУСАЛ — расхождение по биомассе (-12,6%),
    эффект avoided_emissions → строка не сопоставима (docs/pravki.md, П2)."""
    project_id = "proj-01"
    area_ha = 504_986.0
    geometry = make_polygon(91.2, 61.4, area_ha, wobble_seed=1.0)
    geometry_path = write_geometry(project_id, geometry)

    project = models.Project(
        project_id=project_id,
        name="Нижне-Енисейский",
        region="Красноярский край",
        mode=models.ProjectMode.with_project,
        geometry_path=geometry_path,
        area_ha=area_ha,
    )
    db.add(project)

    db.add(
        models.ProjectRegistry(
            project_id=project_id,
            registry_number="04-2023-00000012",
            company="АО «РУСАЛ КРАСНОЯРСК»",
            methodology="Охрана лесов от пожаров (авиамониторинг)",
            crediting_period_start=date(2023, 1, 1),
            crediting_period_end=date(2033, 12, 31),
            units_in_circulation=1_232_611,
            source="registry_xlsx",
        )
    )
    db.add(
        models.ProjectClaims(
            project_id=project_id,
            forest_area_ha=area_ha,
            area_kind=models.AreaKind.project_territory,
            agb_t_ha=135.0,
            expected_effect_co2_t_year=361_600.0,
            effect_kind=models.EffectKind.avoided_emissions,
            monitoring_date=date(2023, 11, 28),
            source=models.ClaimsSource.registry_xlsx,
        )
    )

    obs_rows = [
        (2015, 504100.0, 148.0, 26.0, 2015, True, 96.0),
        (2016, 503200.0, 145.0, 26.0, 2016, True, 95.0),
        (2017, None, None, None, None, False, 31.0),
        (2018, None, None, None, None, False, 28.0),
        (2019, 500900.0, 138.0, 25.0, 2019, True, 94.0),
        (2020, 500100.0, 133.0, 25.0, 2020, True, 95.0),
        (2021, 492600.0, 128.0, 25.0, 2021, True, 92.0),
        (2022, 491800.0, 124.0, 24.0, 2022, True, 93.0),
        (2023, 489300.0, 118.0, 24.0, 2022, True, 93.0),
        (2024, 483900.0, 116.0, 24.0, 2022, True, 91.0),
        (2025, 482100.0, 114.0, 24.0, 2022, True, 90.0),
        (2026, 476210.0, 113.0, 24.0, 2022, True, 96.0),
    ]
    for year, forest_area, agb, agb_sd, agb_src_year, valid, coverage in obs_rows:
        db.add(
            models.Observation(
                project_id=project_id,
                year=year,
                forest_area_ha=forest_area,
                agb_t_ha=agb,
                agb_sd_t_ha=agb_sd,
                agb_source_year=agb_src_year,
                valid=valid,
                valid_coverage_pct=coverage,
            )
        )

    events = [
        dict(
            event_id="proj-01-2021-01", year=2021, area_ha=840.0, fire_evidence=True,
            event_type=models.EventType.fire_supported, confidence=models.Confidence.high,
            sources=["hansen_gfc_v1_13", "modis_mcd64a1"],
            detected_between_start=date(2021, 6, 1), detected_between_end=date(2021, 9, 30),
        ),
        dict(
            event_id="proj-01-2024-01", year=2024, area_ha=320.0, fire_evidence=False,
            event_type=models.EventType.non_fire, confidence=models.Confidence.medium,
            sources=["hansen_gfc_v1_13"],
            detected_between_start=date(2024, 5, 1), detected_between_end=date(2024, 8, 15),
        ),
        dict(
            event_id="proj-01-2026-01", year=2026, area_ha=18.4, fire_evidence=True,
            event_type=models.EventType.fire_supported, confidence=models.Confidence.medium,
            sources=["hansen_gfc_v1_13", "modis_mcd64a1"],
            detected_between_start=date(2026, 6, 18), detected_between_end=date(2026, 8, 27),
        ),
    ]
    for e in events:
        db.add(models.DisturbanceEvent(project_id=project_id, **e))

    co2_ha = co2_equiv_t_ha(113.0)
    calc_id = "CALC-0148"
    calculated_at = datetime(2026, 9, 19, 11, 20, tzinfo=timezone.utc)
    result = {
        "calc_id": calc_id,
        "project_id": project_id,
        "calculated_at": calculated_at.isoformat(),
        "methodology_version": "1.0",
        "algorithm_version": "calc-0.1",
        "input_hash": "",  # проставляется ниже
        "measurement": {
            "forest_area_ha_latest": 476210.0,
            "forest_area_change_pct": round((476210.0 - 504100.0) / 504100.0 * 100, 1),
            "agb_t_ha": 113.0,
            "agb_sd_t_ha": 24.0,
            "agb_source_year": 2022,
            "co2_stock_equivalent_t_ha": co2_ha,
            "co2_stock_total_t": round(co2_ha * 476210.0, 1),
            "series": [
                {"year": r[0], "forest_area_ha": r[1], "co2_stock_total_t": round(co2_equiv_t_ha(r[2]) * r[1], 1) if r[1] else None}
                for r in obs_rows
            ],
        },
        "disturbances": {
            "historical_loss_share_pct": 7.2,
            "recent_loss_ha": 18.4,
            "recent_window_years": 1,
            "fire_exposure": "high",
            "events": [
                {
                    "event_id": e["event_id"],
                    "year": e["year"],
                    "area_ha": e["area_ha"],
                    "event_type": e["event_type"].value,
                    "confidence": e["confidence"].value,
                    "physical_carbon_exposure_co2_t": round(e["area_ha"] * co2_ha, 1),
                }
                for e in events
            ],
        },
        "vulnerability": {
            "level": "medium",
            "drivers": [
                "повторяющиеся пожары в радиусе 10 км",
                "близость к лесовозной дороге",
                "сухость сезона выше нормы за последние 3 года",
            ],
            "method": "heuristic",
            "model_version": None,
            "disclaimer": "Аналитический скрининг, не официальный расчёт риска реверсии",
        },
        "data_completeness": {
            "periods_available": 10,
            "periods_total": 12,
            "valid_coverage_pct": 93.0,
            "latest_observation_date": "2026-09-11",
            "missing_years": [2017, 2018],
        },
        "measurement_confidence": {
            "overall": "moderate",
            "components": {
                "optical_coverage": "high",
                "observation_freshness": "high",
                "biomass_uncertainty": "moderate",
                "cross_source_support": "high",
            },
        },
        "claim_check": {
            "status": "review_recommended",
            "reference_date": "2023-11-28",
            "observation_year_used": 2023,
            "rows": [
                {
                    "metric": "forest_area_ha",
                    "reported": area_ha,
                    "observed": 501200.0,
                    "observed_uncertainty": None,
                    "discrepancy_pct": round((501200.0 - area_ha) / area_ha * 100, 1),
                    "comparable": True,
                },
                {
                    "metric": "agb_t_ha",
                    "reported": 135.0,
                    "observed": 118.0,
                    "observed_uncertainty": 24.0,
                    "discrepancy_pct": round((118.0 - 135.0) / 135.0 * 100, 1),
                    "comparable": True,
                },
                {
                    "metric": "expected_effect_co2_t_year",
                    "reported": 361600.0,
                    "observed": None,
                    "observed_uncertainty": None,
                    "discrepancy_pct": None,
                    "comparable": False,
                    "not_comparable_reason": "avoided_emissions",
                },
            ],
            "events_after_reference_date": [
                {"event_id": "proj-01-2024-01", "year": 2024, "area_ha": 320.0, "event_type": "non_fire"},
                {"event_id": "proj-01-2026-01", "year": 2026, "area_ha": 18.4, "event_type": "fire_supported"},
            ],
            "likely_cause": (
                "Наблюдаемая биомасса ниже заявленной на 12,6 % при погрешности продукта ±24 т/га. "
                "Заявленный эффект относится к предотвращённым выбросам и не проверяется."
            ),
        },
        "scenario": {
            "expected_effect_co2_t_year": 361600.0,
            "effect_source": "project_reported",
            "price_scenario": "base",
            "price_rub_per_unit": 700.0,
            "haircut_pct": 0.0,
            "revenue_rub_year": round(361600.0 * 700.0, 1),
            "revenue_rub_per_ha": round(361600.0 * 700.0 / area_ha, 1),
            "area_basis": "polygon",
            "npv_rub": None,
            "npv_available": False,
            "npv_unavailable_reason": "Нет CAPEX, OPEX и графика выпуска",
        },
        "preview_path": f"data/previews/{calc_id}.png",
        "summary": {
            "text": (
                "Биомасса ниже заявленной на 12,6 % при погрешности продукта ±24 т/га. "
                "В 2026 году зафиксировано нарушение 18,4 га с пожарными признаками — после "
                "даты отчётности проекта. Заявленный эффект относится к предотвращённым "
                "выбросам и не проверяется."
            ),
            "generated_at": calculated_at.isoformat(),
            "generator_version": "summary-0.1",
            "based_on": [calc_id],
            "source_fields": ["claim_check.rows", "claim_check.events_after_reference_date", "claims.effect_kind"],
        },
        "provenance": {
            "datasets": [
                {"name": "UMD/hansen/global_forest_change_2025_v1_13", "version": "v1.13"},
                {"name": "GOOGLE/DYNAMICWORLD/V1", "version": "v1"},
                {"name": "ESA/CCI/Above_Ground_Biomass/V6_0", "version": "v6.0", "year_used": 2022},
                {"name": "MODIS/061/MCD64A1", "version": "061"},
            ],
            "observation_dates": ["2026-06-18", "2026-08-27", "2026-09-11"],
            "parameters": {
                "carbon_fraction": CARBON_FRACTION,
                "co2_factor": CO2_FACTOR,
                "discount_rate": 0.18,
                "price_rub_per_unit": 700.0,
            },
        },
    }
    input_hash = _hash_result_inputs(project_id, result)
    result["input_hash"] = input_hash

    write_preview(
        geometry, calc_id, "2026-09-11",
        event_points=[(91.2 + 0.05, 61.4 + 0.05), (91.2 - 0.03, 61.4 - 0.02)],
    )

    db.add(
        models.Calculation(
            calc_id=calc_id,
            project_id=project_id,
            calculated_at=calculated_at,
            methodology_version="1.0",
            algorithm_version="calc-0.1",
            model_version=None,
            input_hash=input_hash,
            observation_dates=result["provenance"]["observation_dates"],
            datasets=result["provenance"]["datasets"],
            parameters=result["provenance"]["parameters"],
            result=result,
        )
    )

    db.add(models.WatchlistEntry(
        project_id=project_id,
        last_checked_at=datetime(2026, 9, 18, 9, 14, tzinfo=timezone.utc),
        new_events_count=1,
        recent_loss_ha=18.4,
        status=models.WatchStatus.attention,
    ))


def seed_proj_02(db: Session) -> None:
    """Ачинское лесничество, ООО «Сибирский лес» — без значимого расхождения."""
    project_id = "proj-02"
    area_ha = 25_000.0
    geometry = make_polygon(90.4, 56.3, area_ha, wobble_seed=2.0)
    geometry_path = write_geometry(project_id, geometry)

    db.add(models.Project(
        project_id=project_id, name="Ачинское лесничество", region="Красноярский край",
        mode=models.ProjectMode.with_project, geometry_path=geometry_path, area_ha=area_ha,
    ))
    db.add(models.ProjectRegistry(
        project_id=project_id, registry_number="04-2024-00000031", company="ООО «Сибирский лес»",
        methodology="Лесовосстановление и содействие возобновлению",
        crediting_period_start=date(2024, 1, 1), crediting_period_end=date(2034, 12, 31),
        units_in_circulation=45_000, source="registry_xlsx",
    ))
    db.add(models.ProjectClaims(
        project_id=project_id, forest_area_ha=area_ha, area_kind=models.AreaKind.forest_cover,
        agb_t_ha=160.0, expected_effect_co2_t_year=18_500.0, effect_kind=models.EffectKind.removals,
        monitoring_date=date(2026, 1, 15), source=models.ClaimsSource.registry_xlsx,
    ))

    obs_rows = [
        (2015, 24700.0, 140.0, 28.0, 2015, True, 97.0),
        (2016, 24720.0, 143.0, 28.0, 2016, True, 96.0),
        (2017, 24740.0, 146.0, 28.0, 2017, True, 97.0),
        (2018, 24760.0, 149.0, 27.0, 2018, True, 98.0),
        (2019, 24780.0, 151.0, 27.0, 2019, True, 98.0),
        (2020, 24800.0, 153.0, 27.0, 2020, True, 99.0),
        (2021, 24810.0, 154.0, 27.0, 2021, True, 98.0),
        (2022, 24820.0, 155.0, 28.0, 2022, True, 99.0),
        (2023, 24830.0, 156.0, 28.0, 2022, True, 99.0),
        (2024, 24840.0, 157.0, 28.0, 2022, True, 98.0),
        (2025, 24845.0, 157.5, 28.0, 2022, True, 99.0),
        (2026, 24850.0, 158.0, 28.0, 2022, True, 98.0),
    ]
    for year, forest_area, agb, agb_sd, agb_src_year, valid, coverage in obs_rows:
        db.add(models.Observation(
            project_id=project_id, year=year, forest_area_ha=forest_area, agb_t_ha=agb,
            agb_sd_t_ha=agb_sd, agb_source_year=agb_src_year, valid=valid, valid_coverage_pct=coverage,
        ))

    event = dict(
        event_id="proj-02-2017-01", year=2017, area_ha=45.0, fire_evidence=False,
        event_type=models.EventType.vegetation_stress, confidence=models.Confidence.low,
        sources=["modis_mcd64a1"], detected_between_start=date(2017, 5, 1), detected_between_end=date(2017, 6, 20),
    )
    db.add(models.DisturbanceEvent(project_id=project_id, **event))

    co2_ha = co2_equiv_t_ha(158.0)
    calc_id = "CALC-0149"
    calculated_at = datetime(2026, 9, 19, 11, 18, tzinfo=timezone.utc)
    revenue_year = round(18500.0 * 700.0, 1)
    result = {
        "calc_id": calc_id,
        "project_id": project_id,
        "calculated_at": calculated_at.isoformat(),
        "methodology_version": "1.0",
        "algorithm_version": "calc-0.1",
        "input_hash": "",
        "measurement": {
            "forest_area_ha_latest": 24850.0,
            "forest_area_change_pct": round((24850.0 - 24700.0) / 24700.0 * 100, 1),
            "agb_t_ha": 158.0,
            "agb_sd_t_ha": 28.0,
            "agb_source_year": 2022,
            "co2_stock_equivalent_t_ha": co2_ha,
            "co2_stock_total_t": round(co2_ha * 24850.0, 1),
            "series": [
                {"year": r[0], "forest_area_ha": r[1], "co2_stock_total_t": round(co2_equiv_t_ha(r[2]) * r[1], 1)}
                for r in obs_rows
            ],
        },
        "disturbances": {
            "historical_loss_share_pct": 3.1,
            "recent_loss_ha": 0.0,
            "recent_window_years": 1,
            "fire_exposure": "low",
            "events": [
                {
                    "event_id": event["event_id"], "year": event["year"], "area_ha": event["area_ha"],
                    "event_type": event["event_type"].value, "confidence": event["confidence"].value,
                    "physical_carbon_exposure_co2_t": round(event["area_ha"] * co2_ha, 1),
                }
            ],
        },
        "vulnerability": {
            "level": "low",
            "drivers": ["стабильный покров без свежих потерь", "удалённость от лесовозных дорог"],
            "method": "heuristic", "model_version": None,
            "disclaimer": "Аналитический скрининг, не официальный расчёт риска реверсии",
        },
        "data_completeness": {
            "periods_available": 12, "periods_total": 12, "valid_coverage_pct": 98.0,
            "latest_observation_date": "2026-09-08", "missing_years": [],
        },
        "measurement_confidence": {
            "overall": "high",
            "components": {
                "optical_coverage": "high", "observation_freshness": "high",
                "biomass_uncertainty": "moderate", "cross_source_support": "high",
            },
        },
        "claim_check": {
            "status": "no_material_discrepancy",
            "reference_date": "2026-01-15",
            "observation_year_used": 2026,
            "rows": [
                {
                    "metric": "forest_area_ha", "reported": area_ha, "observed": 24850.0,
                    "observed_uncertainty": None,
                    "discrepancy_pct": round((24850.0 - area_ha) / area_ha * 100, 1), "comparable": True,
                },
                {
                    "metric": "agb_t_ha", "reported": 160.0, "observed": 158.0, "observed_uncertainty": 28.0,
                    "discrepancy_pct": round((158.0 - 160.0) / 160.0 * 100, 1), "comparable": True,
                },
                {
                    "metric": "expected_effect_co2_t_year", "reported": 18500.0, "observed": 18100.0,
                    "observed_uncertainty": 900.0,
                    "discrepancy_pct": round((18100.0 - 18500.0) / 18500.0 * 100, 1), "comparable": True,
                },
            ],
            "events_after_reference_date": [],
            "likely_cause": "Все сопоставимые показатели в пределах ±10% — расхождений, требующих внимания, нет.",
        },
        "scenario": {
            "expected_effect_co2_t_year": 18500.0, "effect_source": "project_reported",
            "price_scenario": "base", "price_rub_per_unit": 700.0, "haircut_pct": 0.0,
            "revenue_rub_year": revenue_year, "revenue_rub_per_ha": round(revenue_year / area_ha, 1),
            "area_basis": "polygon", "npv_rub": None, "npv_available": False,
            "npv_unavailable_reason": "Нет CAPEX, OPEX и графика выпуска",
        },
        "preview_path": f"data/previews/{calc_id}.png",
        "summary": {
            "text": (
                "Наблюдаемые показатели соответствуют заявленным в пределах погрешности измерения. "
                "Свежих нарушений за отчётный год не зафиксировано."
            ),
            "generated_at": calculated_at.isoformat(), "generator_version": "summary-0.1",
            "based_on": [calc_id], "source_fields": ["claim_check.rows", "disturbances.recent_loss_ha"],
        },
        "provenance": {
            "datasets": [
                {"name": "UMD/hansen/global_forest_change_2025_v1_13", "version": "v1.13"},
                {"name": "GOOGLE/DYNAMICWORLD/V1", "version": "v1"},
                {"name": "ESA/CCI/Above_Ground_Biomass/V6_0", "version": "v6.0", "year_used": 2022},
                {"name": "MODIS/061/MCD64A1", "version": "061"},
            ],
            "observation_dates": ["2026-05-02", "2026-07-19", "2026-09-08"],
            "parameters": {
                "carbon_fraction": CARBON_FRACTION, "co2_factor": CO2_FACTOR,
                "discount_rate": 0.18, "price_rub_per_unit": 700.0,
            },
        },
    }
    input_hash = _hash_result_inputs(project_id, result)
    result["input_hash"] = input_hash

    write_preview(geometry, calc_id, "2026-09-08")

    db.add(models.Calculation(
        calc_id=calc_id, project_id=project_id, calculated_at=calculated_at,
        methodology_version="1.0", algorithm_version="calc-0.1", model_version=None,
        input_hash=input_hash, observation_dates=result["provenance"]["observation_dates"],
        datasets=result["provenance"]["datasets"], parameters=result["provenance"]["parameters"], result=result,
    ))

    db.add(models.WatchlistEntry(
        project_id=project_id,
        last_checked_at=datetime(2026, 9, 18, 9, 14, tzinfo=timezone.utc),
        new_events_count=0, recent_loss_ha=0.0, status=models.WatchStatus.quiet,
    ))


def seed_proj_03(db: Session) -> None:
    """Кежемская площадка — territory_only: без registry/claims/claim_check."""
    project_id = "proj-03"
    area_ha = 31_500.0
    geometry = make_polygon(96.5, 58.2, area_ha, wobble_seed=3.0)
    geometry_path = write_geometry(project_id, geometry)

    db.add(models.Project(
        project_id=project_id, name="Кежемская площадка", region="Красноярский край",
        mode=models.ProjectMode.territory_only, geometry_path=geometry_path, area_ha=area_ha,
    ))

    obs_rows = [
        (2015, 29800.0, 160.0, 31.0, 2015, True, 88.0),
        (2016, None, None, None, None, False, 40.0),
        (2017, None, None, None, None, False, 35.0),
        (2018, 29500.0, 165.0, 31.0, 2018, True, 82.0),
        (2019, None, None, None, None, False, 38.0),
        (2020, 29200.0, 168.0, 31.0, 2020, True, 85.0),
        (2021, 28950.0, 170.0, 31.0, 2021, True, 84.0),
        (2022, 28700.0, 171.0, 31.0, 2022, True, 86.0),
        (2023, 28500.0, 171.0, 31.0, 2022, True, 83.0),
        (2024, 28250.0, 172.0, 31.0, 2022, True, 87.0),
        (2025, 28000.0, 172.0, 31.0, 2022, True, 85.0),
        (2026, 27750.0, 171.0, 31.0, 2022, True, 90.0),
    ]
    for year, forest_area, agb, agb_sd, agb_src_year, valid, coverage in obs_rows:
        db.add(models.Observation(
            project_id=project_id, year=year, forest_area_ha=forest_area, agb_t_ha=agb,
            agb_sd_t_ha=agb_sd, agb_source_year=agb_src_year, valid=valid, valid_coverage_pct=coverage,
        ))

    event = dict(
        event_id="proj-03-2026-01", year=2026, area_ha=42.1, fire_evidence=False,
        event_type=models.EventType.unknown, confidence=models.Confidence.low,
        sources=["hansen_gfc_v1_13"], detected_between_start=date(2026, 7, 1), detected_between_end=date(2026, 8, 19),
    )
    db.add(models.DisturbanceEvent(project_id=project_id, **event))

    co2_ha = co2_equiv_t_ha(171.0)
    calc_id = "CALC-0150"
    calculated_at = datetime(2026, 9, 19, 11, 14, tzinfo=timezone.utc)
    result = {
        "calc_id": calc_id,
        "project_id": project_id,
        "calculated_at": calculated_at.isoformat(),
        "methodology_version": "1.0",
        "algorithm_version": "calc-0.1",
        "input_hash": "",
        "measurement": {
            "forest_area_ha_latest": 27750.0,
            "forest_area_change_pct": round((27750.0 - 29800.0) / 29800.0 * 100, 1),
            "agb_t_ha": 171.0, "agb_sd_t_ha": 31.0, "agb_source_year": 2022,
            "co2_stock_equivalent_t_ha": co2_ha, "co2_stock_total_t": round(co2_ha * 27750.0, 1),
            "series": [
                {"year": r[0], "forest_area_ha": r[1], "co2_stock_total_t": round(co2_equiv_t_ha(r[2]) * r[1], 1) if r[1] else None}
                for r in obs_rows
            ],
        },
        "disturbances": {
            "historical_loss_share_pct": 7.8, "recent_loss_ha": 42.1, "recent_window_years": 1,
            "fire_exposure": "high",
            "events": [
                {
                    "event_id": event["event_id"], "year": event["year"], "area_ha": event["area_ha"],
                    "event_type": event["event_type"].value, "confidence": event["confidence"].value,
                    "physical_carbon_exposure_co2_t": round(event["area_ha"] * co2_ha, 1),
                }
            ],
        },
        "vulnerability": {
            "level": "high",
            "drivers": [
                "частые пожары в радиусе 10 км",
                "высокая доля открытых участков в радиусе 5 км",
                "близость к лесовозной дороге",
            ],
            "method": "heuristic", "model_version": None,
            "disclaimer": "Аналитический скрининг, не официальный расчёт риска реверсии",
        },
        "data_completeness": {
            "periods_available": 9, "periods_total": 12, "valid_coverage_pct": 85.0,
            "latest_observation_date": "2026-09-13", "missing_years": [2016, 2017, 2019],
        },
        "measurement_confidence": {
            "overall": "low",
            "components": {
                "optical_coverage": "moderate", "observation_freshness": "high",
                "biomass_uncertainty": "moderate", "cross_source_support": "low",
            },
        },
        # claim_check отсутствует целиком — mode: territory_only (раздел 6).
        "scenario": {
            "expected_effect_co2_t_year": 0.0, "effect_source": "user_defined",
            "price_scenario": None, "price_rub_per_unit": 0.0, "haircut_pct": 0.0,
            "revenue_rub_year": 0.0, "revenue_rub_per_ha": 0.0, "area_basis": "polygon",
            "npv_rub": None, "npv_available": False,
            "npv_unavailable_reason": "Нет заявленных показателей — участок не зарегистрирован как проект",
        },
        "preview_path": f"data/previews/{calc_id}.png",
        "summary": {
            "text": (
                "Территория не зарегистрирована как проект, заявленных показателей нет. "
                "В 2026 году зафиксировано нарушение 42,1 га, тип не определён. Уязвимость "
                "территории — высокая, основной фактор — повторяющиеся пожары."
            ),
            "generated_at": calculated_at.isoformat(), "generator_version": "summary-0.1",
            "based_on": [calc_id], "source_fields": ["disturbances.events", "vulnerability.level"],
        },
        "provenance": {
            "datasets": [
                {"name": "UMD/hansen/global_forest_change_2025_v1_13", "version": "v1.13"},
                {"name": "GOOGLE/DYNAMICWORLD/V1", "version": "v1"},
                {"name": "ESA/CCI/Above_Ground_Biomass/V6_0", "version": "v6.0", "year_used": 2022},
                {"name": "MODIS/061/MCD64A1", "version": "061"},
            ],
            "observation_dates": ["2026-07-01", "2026-08-19", "2026-09-13"],
            "parameters": {
                "carbon_fraction": CARBON_FRACTION, "co2_factor": CO2_FACTOR,
                "discount_rate": 0.18, "price_rub_per_unit": 700.0,
            },
        },
    }
    input_hash = _hash_result_inputs(project_id, result)
    result["input_hash"] = input_hash

    write_preview(geometry, calc_id, "2026-09-13")

    db.add(models.Calculation(
        calc_id=calc_id, project_id=project_id, calculated_at=calculated_at,
        methodology_version="1.0", algorithm_version="calc-0.1", model_version=None,
        input_hash=input_hash, observation_dates=result["provenance"]["observation_dates"],
        datasets=result["provenance"]["datasets"], parameters=result["provenance"]["parameters"], result=result,
    ))

    db.add(models.WatchlistEntry(
        project_id=project_id,
        last_checked_at=datetime(2026, 9, 18, 9, 14, tzinfo=timezone.utc),
        new_events_count=1, recent_loss_ha=42.1, status=models.WatchStatus.attention,
    ))


def seed_registry_catalog(db: Session) -> None:
    """Раздел 12, KAN-43. Полный набор 132 строк выгрузки сюда не входит
    (реальный xlsx-импорт — зона Р5); каталог самосогласован: `total` в
    ответе API считается от фактически загруженных строк (см. registry.py),
    а не декларируется отдельно, чтобы "отдаёт все проекты выгрузки" было
    буквально верно для мок-набора."""
    db.add(models.RegistryImportMeta(
        export_date=date(2026, 9, 17),
        source="carbonreg_xlsx_2026-09-17 + manual",
        total_declared=132,
    ))

    entries = [
        dict(registry_number="04-2023-00000012", name="Нижне-Енисейский", company="АО «РУСАЛ КРАСНОЯРСК»",
             region="Красноярский край", methodology="Охрана лесов от пожаров (авиамониторинг)",
             effect_kind=models.EffectKind.avoided_emissions, units_in_circulation=1_232_611,
             data_status=models.DataStatus.calculated, project_id="proj-01", calc_id="CALC-0148"),
        dict(registry_number="04-2024-00000031", name="Ачинское лесничество", company="ООО «Сибирский лес»",
             region="Красноярский край", methodology="Лесовосстановление и содействие возобновлению",
             effect_kind=models.EffectKind.removals, units_in_circulation=45_000,
             data_status=models.DataStatus.calculated, project_id="proj-02", calc_id="CALC-0149"),
        dict(registry_number="04-2023-00000008", name="Богучанский участок", company="АО «Лесинвест»",
             region="Красноярский край", methodology="Лесоразведение на неиспользуемых землях",
             effect_kind=models.EffectKind.removals, units_in_circulation=318_400,
             data_status=models.DataStatus.no_geometry, project_id=None, calc_id=None),
        dict(registry_number="04-2024-00000047", name="Тасеевский", company="ООО «КарбонСибирь»",
             region="Красноярский край", methodology="Охрана лесов от пожаров",
             effect_kind=models.EffectKind.avoided_emissions, units_in_circulation=96_200,
             data_status=models.DataStatus.no_geometry, project_id=None, calc_id=None),
        dict(registry_number="04-2022-00000003", name="Приангарский", company="ПАО «Сибирская генерация»",
             region="Иркутская область", methodology="Лесовосстановление",
             effect_kind=models.EffectKind.removals, units_in_circulation=740_000,
             data_status=models.DataStatus.no_geometry, project_id=None, calc_id=None),
        dict(registry_number="04-2025-00000066", name="Усть-Илимский", company="ООО «Грин Форест»",
             region="Иркутская область", methodology="Предотвращение обезлесения",
             effect_kind=models.EffectKind.avoided_emissions, units_in_circulation=12_500,
             data_status=models.DataStatus.in_progress, project_id=None, calc_id=None),
        dict(registry_number="04-2021-00000001", name="Сахалинский пилотный",
             company="Правительство Сахалинской области", region="Сахалинская область",
             methodology="Лесоклиматический проект", effect_kind=models.EffectKind.removals,
             units_in_circulation=2_100_000, data_status=models.DataStatus.no_geometry,
             project_id=None, calc_id=None),
        dict(registry_number="04-2022-00000015", name="Мотыгинский резерв", company="ООО «Ангара Лес»",
             region="Красноярский край", methodology="Лесовосстановление",
             effect_kind=models.EffectKind.removals, units_in_circulation=210_000,
             data_status=models.DataStatus.no_geometry, project_id=None, calc_id=None),
        dict(registry_number="04-2024-00000052", name="Северо-Енисейский", company="АО «Полюс»",
             region="Красноярский край", methodology="Охрана лесов от пожаров",
             effect_kind=models.EffectKind.avoided_emissions, units_in_circulation=540_000,
             data_status=models.DataStatus.no_geometry, project_id=None, calc_id=None),
        dict(registry_number="04-2025-00000071", name="Тайшетский", company="ООО «Лесресурс»",
             region="Иркутская область", methodology="Лесоразведение на неиспользуемых землях",
             effect_kind=models.EffectKind.removals, units_in_circulation=88_400,
             data_status=models.DataStatus.in_progress, project_id=None, calc_id=None),
    ]
    for e in entries:
        db.add(models.RegistryCatalogEntry(**e))


def _hash_result_inputs(project_id: str, result: dict) -> str:
    payload = {
        "project_id": project_id,
        "measurement": result["measurement"],
        "disturbances": result["disturbances"],
    }
    return compute_input_hash(payload)


def main() -> None:
    db = SessionLocal()
    try:
        clear(db)
        seed_proj_01(db)
        seed_proj_02(db)
        seed_proj_03(db)
        # Без ORM-relationship между RegistryCatalogEntry и Calculation/Project
        # (намеренно — избегаем неоднозначности из-за двух FK на projects)
        # SQLAlchemy не сортирует вставки по этой зависимости автоматически —
        # explicit flush гарантирует, что calc_id/project_id уже в БД раньше,
        # чем каталог реестра на них сошлётся.
        db.flush()
        seed_registry_catalog(db)
        db.commit()
        print("Мок-набор загружен: 3 участка, каталог реестра, список наблюдения.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
