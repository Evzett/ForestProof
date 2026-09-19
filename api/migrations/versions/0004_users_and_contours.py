"""Роли, учётные записи и сохранённые контуры

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-19

KAN-78. Три таблицы-изменения:

* `users` — учётные записи и роли. Пароль только хешем bcrypt.
* `saved_contours` — загруженный пользователем контур вместе с расчётом:
  без него файл исчезал сразу после показа результата.
* `calculations.created_by` — чей расчёт (Ж-01). Колонка nullable:
  расчёты, сделанные до появления ролей, владельца не имеют, и
  приписывать им автора задним числом нельзя.
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

ROLE = sa.Enum("viewer", "analyst", "admin", name="role", native_enum=False)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("login", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", ROLE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "saved_contours",
        sa.Column("contour_id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("geometry", sa.dialects.postgresql.JSONB, nullable=False),
        sa.Column("area_ha", sa.Numeric(14, 4), nullable=False),
        sa.Column("year_start", sa.Integer, nullable=False),
        sa.Column("year_end", sa.Integer, nullable=False),
        sa.Column(
            "calc_id",
            sa.String(32),
            sa.ForeignKey("calculations.calc_id", ondelete="SET NULL"),
            index=True,
        ),
        sa.Column(
            "created_by",
            sa.String(64),
            sa.ForeignKey("users.login", ondelete="SET NULL"),
            index=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.add_column(
        "calculations",
        sa.Column(
            "created_by",
            sa.String(64),
            sa.ForeignKey("users.login", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_calculations_created_by", "calculations", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_calculations_created_by", table_name="calculations")
    op.drop_column("calculations", "created_by")
    op.drop_table("saved_contours")
    op.drop_table("users")
