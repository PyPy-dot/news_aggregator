"""add_rss_tables

Revision ID: 765fdc9479e7
Revises: 94d430f06d9a
Create Date: 2026-08-09 22:11:30.431075

Миграция добавляет таблицы для RSS парсинга:
- rss_sources — источники RSS лент (сайты)
- rss_news — спарсенные новости из RSS
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '765fdc9479e7'
down_revision: Union[str, None] = '94d430f06d9a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Создать таблицы для RSS парсинга.
    """
    # =============================================================================
    # Таблица rss_sources — источники RSS лент
    # =============================================================================
    op.create_table(
        'rss_sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False, comment='Название источника'),
        sa.Column('url', sa.String(512), nullable=False, unique=True, comment='URL RSS ленты'),
        sa.Column('site_url', sa.String(512), nullable=True, comment='URL сайта'),
        sa.Column('category', sa.String(100), nullable=True, comment='Категория источника'),
        sa.Column('description', sa.String(1024), nullable=True, comment='Описание'),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False, comment='Активен ли источник'),
        sa.Column('last_checked', sa.DateTime(), nullable=True, comment='Время последней проверки'),
        sa.Column('last_modified', sa.String(255), nullable=True, comment='Last-Modified header'),
        sa.Column('etag', sa.String(255), nullable=True, comment='ETag header'),
        sa.Column('check_interval_minutes', sa.Integer(), default=5, nullable=False, comment='Интервал проверки (мин)'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Индексы для производительности
    op.create_index('idx_rss_sources_active', 'rss_sources', ['is_active'])
    op.create_index('idx_rss_sources_category', 'rss_sources', ['category'])
    op.create_index('idx_rss_sources_last_checked', 'rss_sources', ['last_checked'])

    # =============================================================================
    # Таблица rss_news — спарсенные новости
    # =============================================================================
    op.create_table(
        'rss_news',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), sa.ForeignKey('rss_sources.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(1024), nullable=False, comment='Заголовок новости'),
        sa.Column('description', sa.Text(), nullable=True, comment='Описание/анонс'),
        sa.Column('content', sa.Text(), nullable=True, comment='Полный текст (если есть)'),
        sa.Column('link', sa.String(1024), nullable=False, comment='Ссылка на новость'),
        sa.Column('author', sa.String(255), nullable=True, comment='Автор'),
        sa.Column('published_at', sa.DateTime(), nullable=True, comment='Дата публикации'),
        sa.Column('guid', sa.String(1024), nullable=True, comment='Уникальный ID (GUID)'),
        sa.Column('image_url', sa.String(512), nullable=True, comment='URL изображения'),
        sa.Column('category', sa.String(100), nullable=True, comment='Категория новости'),
        sa.Column('tags', sa.String(512), nullable=True, comment='Теги (JSON)'),
        sa.Column('processed', sa.Boolean(), default=False, nullable=False, comment='Обработана ли новость'),
        sa.Column('post_id', sa.Integer(), sa.ForeignKey('posts.id', ondelete='SET NULL'), nullable=True, comment='ID связанного поста'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_id', 'guid', name='uq_rss_news_source_guid'),
        sa.UniqueConstraint('source_id', 'link', name='uq_rss_news_source_link')
    )

    # Индексы для производительности
    op.create_index('idx_rss_news_source', 'rss_news', ['source_id'])
    op.create_index('idx_rss_news_processed', 'rss_news', ['processed'])
    op.create_index('idx_rss_news_published', 'rss_news', ['published_at'])
    op.create_index('idx_rss_news_category', 'rss_news', ['category'])


def downgrade() -> None:
    """
    Удалить таблицы RSS парсинга.
    """
    op.drop_index('idx_rss_news_category', table_name='rss_news')
    op.drop_index('idx_rss_news_published', table_name='rss_news')
    op.drop_index('idx_rss_news_processed', table_name='rss_news')
    op.drop_index('idx_rss_news_source', table_name='rss_news')
    op.drop_table('rss_news')

    op.drop_index('idx_rss_sources_last_checked', table_name='rss_sources')
    op.drop_index('idx_rss_sources_category', table_name='rss_sources')
    op.drop_index('idx_rss_sources_active', table_name='rss_sources')
    op.drop_table('rss_sources')
