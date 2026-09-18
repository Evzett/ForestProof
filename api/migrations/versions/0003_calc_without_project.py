"""calculations.project_id nullable: расчёт по контуру без проекта

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-19

Схема заводилась под прежнюю постановку, где расчёт всегда принадлежал
проекту реестра. В постановке кейса расчёт делается по контуру, и проекта
у него нет вовсе — ни в данных, ни по смыслу.

Внешний ключ сохраняется: если проект указан, он обязан существовать.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "calculations",
        "project_id",
        existing_type=sa.String(32),
        nullable=True,
    )


def downgrade() -> None:
    # Обратно только если ни одного расчёта без проекта не осталось.
    op.execute("DELETE FROM calculations WHERE project_id IS NULL")
    op.alter_column(
        "calculations",
        "project_id",
        existing_type=sa.String(32),
        nullable=False,
    )
