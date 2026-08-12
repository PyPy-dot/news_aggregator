"""add_2fa_fields_to_users

Revision ID: 94d430f06d9a
Revises: 96956db4262c
Create Date: 2026-08-09 22:01:53.694577

Миграция добавляет поля для поддержки 2FA (TOTP) аутентификации администраторов.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '94d430f06d9a'
down_revision: Union[str, None] = '96956db4262c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Добавить поля 2FA в таблицу users.
    """
    # totp_secret — TOTP секрет для Google Authenticator
    op.add_column('users', sa.Column('totp_secret', sa.String(256), nullable=True))

    # totp_enabled — флаг включения 2FA
    op.add_column('users', sa.Column('totp_enabled', sa.Boolean, default=False, nullable=False))

    # totp_backup_codes — JSON массив резервных кодов (10 кодов по 8 символов)
    op.add_column('users', sa.Column('totp_backup_codes', sa.Text, nullable=True))


def downgrade() -> None:
    """
    Удалить поля 2FA из таблицы users.
    """
    op.drop_column('users', 'totp_backup_codes')
    op.drop_column('users', 'totp_enabled')
    op.drop_column('users', 'totp_secret')
