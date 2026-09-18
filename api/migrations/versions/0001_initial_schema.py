"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("region", sa.String(255)),
        sa.Column(
            "mode", sa.Enum("with_project", "territory_only", name="projectmode", native_enum=False), nullable=False
        ),
        sa.Column("geometry_path", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "project_registry",
        sa.Column(
            "project_id",
            sa.String(32),
            sa.ForeignKey("projects.project_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("registry_number", sa.String(64), nullable=False),
        sa.Column("company", sa.String(512), nullable=False),
        sa.Column("methodology", sa.String(255), nullable=False),
        sa.Column("crediting_period_start", sa.Date),
        sa.Column("crediting_period_end", sa.Date),
        sa.Column("units_in_circulation", sa.Integer),
        sa.Column("source", sa.String(32), server_default="registry_xlsx"),
    )

    op.create_table(
        "project_claims",
        sa.Column(
            "project_id",
            sa.String(32),
            sa.ForeignKey("projects.project_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("forest_area_ha", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "area_kind",
            sa.Enum("forest_cover", "project_territory", name="areakind", native_enum=False),
            nullable=False,
        ),
        sa.Column("agb_t_ha", sa.Numeric(8, 2), nullable=False),
        sa.Column("expected_effect_co2_t_year", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "effect_kind",
            sa.Enum("removals", "avoided_emissions", name="effectkind", native_enum=False),
            nullable=False,
        ),
        sa.Column("monitoring_date", sa.Date, nullable=False),
        sa.Column(
            "source", sa.Enum("registry_xlsx", "manual", name="claimssource", native_enum=False), nullable=False
        ),
    )

    op.create_table(
        "observations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.String(32),
            sa.ForeignKey("projects.project_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("forest_area_ha", sa.Numeric(12, 2)),
        sa.Column("agb_t_ha", sa.Numeric(8, 2)),
        sa.Column("agb_sd_t_ha", sa.Numeric(8, 2)),
        sa.Column("agb_source_year", sa.Integer),
        sa.Column("valid", sa.Boolean, nullable=False),
        sa.Column("valid_coverage_pct", sa.Numeric(5, 2), nullable=False),
        sa.UniqueConstraint("project_id", "year", name="uq_observations_project_year"),
    )
    op.create_index("ix_observations_project_id", "observations", ["project_id"])

    op.create_table(
        "disturbance_events",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(32),
            sa.ForeignKey("projects.project_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("area_ha", sa.Numeric(12, 2), nullable=False),
        sa.Column("fire_evidence", sa.Boolean, nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "fire_supported",
                "non_fire",
                "vegetation_stress",
                "unknown",
                name="eventtype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Enum("high", "medium", "low", name="confidence", native_enum=False), nullable=False),
        sa.Column("sources", JSONB, nullable=False),
        sa.Column("detected_between_start", sa.Date),
        sa.Column("detected_between_end", sa.Date),
    )
    op.create_index("ix_disturbance_events_project_id", "disturbance_events", ["project_id"])

    # --- calculations: аудит-поля из раздела 8 контракта, не переименовывать ---
    op.create_table(
        "calculations",
        sa.Column("calc_id", sa.String(32), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(32),
            sa.ForeignKey("projects.project_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("methodology_version", sa.String(32), nullable=False),
        sa.Column("algorithm_version", sa.String(32), nullable=False),
        sa.Column("model_version", sa.String(64)),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("observation_dates", JSONB, nullable=False),
        sa.Column("datasets", JSONB, nullable=False),
        sa.Column("parameters", JSONB, nullable=False),
        sa.Column("result", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_calculations_project_id", "calculations", ["project_id"])


def downgrade() -> None:
    op.drop_table("calculations")
    op.drop_table("disturbance_events")
    op.drop_table("observations")
    op.drop_table("project_claims")
    op.drop_table("project_registry")
    op.drop_table("projects")
