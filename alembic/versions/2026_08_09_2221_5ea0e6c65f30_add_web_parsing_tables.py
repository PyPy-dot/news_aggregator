"""add_web_parsing_tables

Revision ID: 5ea0e6c65f30
Revises: 765fdc9479e7
Create Date: 2026-08-09 22:21:15.711336

Миграция добавляет таблицы для Web парсинга:
- web_sources — источники (сайты для парсинга)
- web_news — спарсенные новости из web
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ea0e6c65f30'
down_revision: Union[str, None] = '765fdc9479e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Создать таблицы для Web парсинга.
    """
    # =============================================================================
    # Таблица web_sources — источники (сайты)
    # =============================================================================
    op.create_table(
        'web_sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False, comment='Название сайта'),
        sa.Column('url', sa.String(512), nullable=False, unique=True, comment='URL сайта'),
        sa.Column('category', sa.String(100), nullable=True, comment='Категория'),
        sa.Column('description', sa.String(1024), nullable=True, comment='Описание'),
        sa.Column('parser_config', sa.Text(), nullable=True, comment='Конфигурация парсера (JSON)'),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False, comment='Активен ли источник'),
        sa.Column('last_checked', sa.DateTime(), nullable=True, comment='Время последней проверки'),
        sa.Column('check_interval_minutes', sa.Integer(), default=60, nullable=False, comment='Интервал проверки (мин)'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Индексы
    op.create_index('idx_web_sources_active', 'web_sources', ['is_active'])
    op.create_index('idx_web_sources_category', 'web_sources', ['category'])

    # =============================================================================
    # Таблица web_news — спарсенные новости
    # =============================================================================
    op.create_table(
        'web_news',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), sa.ForeignKey('web_sources.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(1024), nullable=False, comment='Заголовок'),
        sa.Column('description', sa.Text(), nullable=True, comment='Описание'),
        sa.Column('content', sa.Text(), nullable=True, comment='Полный текст'),
        sa.Column('link', sa.String(1024), nullable=False, comment='Ссылка'),
        sa.Column('author', sa.String(255), nullable=True, comment='Автор'),
        sa.Column('published_at', sa.DateTime(), nullable=True, comment='Дата публикации'),
        sa.Column('image_url', sa.String(512), nullable=True, comment='URL изображения'),
        sa.Column('category', sa.String(100), nullable=True, comment='Категория'),
        sa.Column('tags', sa.String(512), nullable=True, comment='Теги (JSON)'),
        sa.Column('processed', sa.Boolean(), default=False, nullable=False, comment='Обработана ли'),
        sa.Column('post_id', sa.Integer(), sa.ForeignKey('posts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_id', 'link', name='uq_web_news_source_link')
    )

    # Индексы
    op.create_index('idx_web_news_source', 'web_news', ['source_id'])
    op.create_index('idx_web_news_processed', 'web_news', ['processed'])
    op.create_index('idx_web_news_published', 'web_news', ['published_at'])


def downgrade() -> None:
    """
    Удалить таблицы Web парсинга.
    """
    op.drop_index('idx_web_news_published', table_name='web_news')
    op.drop_index('idx_web_news_processed', table_name='web_news')
    op.drop_index('idx_web_news_source', table_name='web_news')
    op.drop_table('web_news')

    op.drop_index('idx_web_sources_category', table_name='web_sources')
    op.drop_index('idx_web_sources_active', table_name='web_sources')
    op.drop_table('web_sources')
