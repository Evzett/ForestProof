"""Пять ролей, профиль и публикация контура

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-19

KAN-78, вторая часть. Новых значений роли (`investor`, `auditor`) эта
миграция не касается: колонка `users.role` — обычный VARCHAR, потому что
перечисления объявлены с `native_enum=False` и без CHECK. Добавление роли
в коде не требует DDL, и это здесь как раз кстати.

Меняются три вещи:

* `users.avatar_color` — цвет аватара. Картинок не храним.
* `users.blocked` — вход закрыт, а расчёты и авторство целы. Удаление
  учётной записи оборвало бы подписи в журнале.
* `saved_contours.published` — контур виден всем или только автору. По
  умолчанию не виден: загрузка файла и публикация — разные намерения.

Уже загруженные контуры остаются закрытыми. Раскрыть чужое задним числом
нельзя: человек загружал их, когда никакой публикации не существовало, и
согласия на показ не давал.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_color", sa.String(16)))
    op.add_column(
        "users",
        sa.Column("blocked", sa.Boolean, nullable=False, server_default="false"),
    )
    op.add_column(
        "saved_contours",
        sa.Column("published", sa.Boolean, nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("saved_contours", "published")
    op.drop_column("users", "blocked")
    op.drop_column("users", "avatar_color")
