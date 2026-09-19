"""Три роли: оператор, инвестор, администратор

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-19

Роли пересмотрены: вместо пяти — три назначаемые. «Аналитик» стал
«оператором» (то же самое другим словом), «верификатор» исчез как
отдельная роль — проверка чужой работы оказалась обязанностью
администратора, а не четвёртой ступенью лестницы.

Колонка `users.role` — обычный VARCHAR без CHECK (перечисления объявлены
с `native_enum=False`). Но длину SQLAlchemy взяла по самому длинному
значению на момент создания таблицы — `analyst`, семь символов. Слово
`operator` длиннее, и без расширения колонки обновление обрывается на
полпути. Поэтому сначала ширина, потом значения.

Ширина взята с запасом (32), чтобы следующее переименование роли не
потребовало ещё одной такой миграции.

Значения в уже заведённых записях перевести обязательно: строка
`analyst` после переименования не соответствует ни одному члену
перечисления, и SQLAlchemy упадёт при первом же чтении такой строки.

Обратная миграция возвращает `analyst`. Бывших верификаторов она вернуть
не может — после перевода их в операторов различить их уже нечем, и
делать вид, что можно, было бы враньём.
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "role", type_=sa.String(32), existing_nullable=False)
    op.execute("UPDATE users SET role = 'operator' WHERE role IN ('analyst', 'auditor')")


def downgrade() -> None:
    op.execute("UPDATE users SET role = 'analyst' WHERE role = 'operator'")
    op.alter_column("users", "role", type_=sa.String(7), existing_nullable=False)
