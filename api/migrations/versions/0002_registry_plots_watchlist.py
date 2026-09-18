"""registry catalog, geometry uploads, plots, watchlist

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Схема — до первого реального проекта в БД, поэтому NOT NULL без
    # server_default безопасен (нет существующих строк, которые надо бэкфилить).
    op.add_column("projects", sa.Column("area_ha", sa.Numeric(14, 2), nullable=False))

    op.create_table(
        "registry_import_meta",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("export_date", sa.Date, nullable=False),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("total_declared", sa.Integer),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "registry_catalog",
        sa.Column("registry_number", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("company", sa.String(512), nullable=False),
        sa.Column("region", sa.String(255), nullable=False),
        sa.Column("methodology", sa.String(255), nullable=False),
        sa.Column(
            "effect_kind", sa.Enum("removals", "avoided_emissions", name="effectkind", native_enum=False)
        ),
        sa.Column("units_in_circulation", sa.Integer),
        sa.Column(
            "data_status",
            sa.Enum("calculated", "no_geometry", "in_progress", name="datastatus", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "project_id", sa.String(32), sa.ForeignKey("projects.project_id", ondelete="SET NULL")
        ),
        sa.Column(
            "calc_id", sa.String(32), sa.ForeignKey("calculations.calc_id", ondelete="SET NULL")
        ),
    )

    op.create_table(
        "geometry_uploads",
        sa.Column("upload_token", sa.String(32), primary_key=True),
        sa.Column("geometry", JSONB, nullable=False),
        sa.Column("checks", JSONB, nullable=False),
        sa.Column("accepted", sa.Boolean, nullable=False),
        sa.Column("area_ha", sa.Numeric(14, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "plots",
        sa.Column("plot_id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("boundary_source", sa.String(512), nullable=False),
        sa.Column(
            "link_project_id", sa.String(32), sa.ForeignKey("projects.project_id", ondelete="SET NULL")
        ),
        sa.Column(
            "upload_token",
            sa.String(32),
            sa.ForeignKey("geometry_uploads.upload_token"),
            nullable=False,
        ),
        sa.Column(
            "project_id", sa.String(32), sa.ForeignKey("projects.project_id", ondelete="SET NULL")
        ),
        sa.Column(
            "calc_id", sa.String(32), sa.ForeignKey("calculations.calc_id", ondelete="SET NULL")
        ),
        sa.Column(
            "status",
            sa.Enum("running", "done", "failed", name="plotstatus", native_enum=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "watchlist",
        sa.Column(
            "project_id",
            sa.String(32),
            sa.ForeignKey("projects.project_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("new_events_count", sa.Integer, server_default="0"),
        sa.Column("recent_loss_ha", sa.Numeric(12, 2)),
        sa.Column(
            "status",
            sa.Enum("attention", "quiet", name="watchstatus", native_enum=False),
            server_default="quiet",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("watchlist")
    op.drop_table("plots")
    op.drop_table("geometry_uploads")
    op.drop_table("registry_catalog")
    op.drop_table("registry_import_meta")
    op.drop_column("projects", "area_ha")
