"""Фоновые расчёты по контуру

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-19

KAN-78. Расчёт по контуру вне набора тянет данные из открытых источников
и занимает минуты. Держать всё это время открытое окно мастера нельзя,
поэтому состояние задачи хранится в базе: окно можно закрыть, вкладку
перезагрузить, а задача найдётся по номеру.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

STATUS = sa.Enum("queued", "running", "done", "failed", name="jobstatus", native_enum=False)


def upgrade() -> None:
    op.create_table(
        "calc_jobs",
        sa.Column("job_id", sa.String(32), primary_key=True),
        sa.Column("geometry", postgresql.JSONB, nullable=False),
        sa.Column("year_start", sa.Integer, nullable=False),
        sa.Column("year_end", sa.Integer, nullable=False),
        sa.Column("status", STATUS, nullable=False, server_default="queued"),
        sa.Column("step", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.String(1024)),
        sa.Column("result", postgresql.JSONB),
        sa.Column("calc_id", sa.String(32)),
        sa.Column(
            "created_by",
            sa.String(64),
            sa.ForeignKey("users.login", ondelete="SET NULL"),
            index=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("calc_jobs")
