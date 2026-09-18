/* Типы по контракту данных: docs/04-kontrakty-dannyh.md.
   Имена полей менять нельзя — любое расхождение с контрактом считается багом. */

export type Level = "low" | "medium" | "high";
export type Confidence = "high" | "moderate" | "low";
export type DataStatus = "calculated" | "no_geometry" | "in_progress";
export type EffectKind = "removals" | "avoided_emissions";
export type AreaKind = "forest_cover" | "project_territory";
export type EventType = "fire_supported" | "non_fire" | "vegetation_stress" | "unknown";

export type ClaimStatus =
  | "no_material_discrepancy"
  | "review_recommended"
  | "evidence_insufficient"
  | "not_comparable";

export type NotComparableReason =
  | "avoided_emissions"
  | "area_kind_mismatch"
  | "no_valid_observation";

/* Строка каталога реестра — GET /api/registry/projects */
export interface RegistryItem {
  registry_number: string;
  name: string;
  company: string;
  region: string;
  methodology: string;
  effect_kind: EffectKind | null;
  units_in_circulation: number | null;
  data_status: DataStatus;
  project_id: string | null;
  calc_id: string | null;
}

/* Строка экрана сравнения — GET /api/projects */
export interface ProjectSummary {
  project_id: string;
  name: string;
  subtitle: string;
  mode: "with_project" | "territory_only";
  area_ha: number;
  agb_t_ha: number;
  agb_sd_t_ha: number;
  historical_loss_share_pct: number;
  recent_loss_ha: number;
  fire_exposure: Level;
  measurement_confidence_overall: Confidence;
  vulnerability_level: Level;
  latest_observation_days_ago: number;
  claim_status: ClaimStatus | null;
  revenue_rub_per_ha: number | null;
  preview_path: string;
  boundary_source: string;
  calc_id: string;
}

export interface DisturbanceEvent {
  event_id: string;
  year: number;
  area_ha: number;
  event_type: EventType;
  fire_evidence: boolean;
  confidence: Confidence;
}

export interface ClaimRow {
  metric: string;
  label: string;
  reported: number | null;
  observed: number | null;
  discrepancy_pct: number | null;
  comparable: boolean;
  not_comparable_reason?: NotComparableReason;
}

export interface ClaimCheck {
  status: ClaimStatus;
  reference_date: string;
  observation_year_used: number;
  rows: ClaimRow[];
  events_after_reference_date: DisturbanceEvent[];
  likely_cause: string;
}

export interface Summary {
  text: string;
  generated_at: string;
  generator_version: string;
  based_on: string[];
}

export interface Calculation {
  calc_id: string;
  project_id: string;
  calculated_at: string;
  methodology_version: string;
  algorithm_version: string;
  input_hash: string;
  claim_status: ClaimStatus | null;
  plot_name: string;
}

export interface WatchItem {
  project_id: string;
  name: string;
  subtitle: string;
  last_check: string;
  new_events: number;
  recent_loss: string;
  status: "attention" | "quiet";
}

export interface FeedItem {
  date: string;
  name: string;
  text: string;
  kind: "disturbance" | "data" | "recalc";
  level: Level | "none";
}
