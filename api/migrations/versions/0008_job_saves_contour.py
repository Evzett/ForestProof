"""Задача сохраняет контур сама

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-19

Контур сохранял браузер: он дожидался окончания фоновой задачи и делал
`POST /api/contours`. Из-за этого результат многоминутного расчёта
терялся от чего угодно — закрытой вкладки, перезагрузки, запуска
второго расчёта поверх первого. Обещание «окно можно закрыть», которое
мастер выводит на экран, было неправдой.

Имя и происхождение контура известны ещё до запуска: их вводят на шаге
метаданных. Значит задача может сохранить контур сама — и тогда он
появляется независимо от того, смотрит ли кто-то на экран.

Колонки nullable: у задач, заведённых до этой миграции, имени нет, и
придумывать его за пользователя мы не будем.
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calc_jobs", sa.Column("name", sa.String(255)))
    op.add_column("calc_jobs", sa.Column("source_name", sa.String(255)))
    op.add_column("calc_jobs", sa.Column("source_kind", sa.String(32)))
    op.add_column("calc_jobs", sa.Column("contour_id", sa.String(32)))


def downgrade() -> None:
    op.drop_column("calc_jobs", "contour_id")
    op.drop_column("calc_jobs", "source_kind")
    op.drop_column("calc_jobs", "source_name")
    op.drop_column("calc_jobs", "name")
