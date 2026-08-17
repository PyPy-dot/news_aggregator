"""
Web Admin — управление Web источниками парсинга.
"""

import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from services.database import get_database_service
from database import RepositoryFactory

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get('/')
async def list_web() -> Dict[str, Any]:
    """Получить список всех Web источников."""
    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        sources_repo = factory.web_sources()
        news_repo = factory.web_news()

        sources = await sources_repo.get_active()

        result = []
        for s in sources:
            count = await news_repo.count_unprocessed()
            result.append({
                'id': s.id,
                'name': s.name,
                'url': s.url,
                'category': s.category,
                'is_active': s.is_active,
                'last_checked': s.last_checked.isoformat() if s.last_checked else None,
                'check_interval_minutes': s.check_interval_minutes,
                'unprocessed': count,
            })

        return {'web_sources': result}


@router.post('/sources')
async def create_web_source(
    name: str,
    url: str,
    parser_config: str,
    category: str = 'Общее',
    description: str = '',
    check_interval_minutes: int = 60,
) -> Dict[str, Any]:
    """Создать новый Web источник."""
    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        sources_repo = factory.web_sources()

        # Проверяем уникальность URL
        existing = await sources_repo.get_by_url(url)
        if existing:
            raise HTTPException(status_code=400, detail=f"Источник с URL {url} уже существует")

        try:
            # Валидируем JSON конфигурации
            json.loads(parser_config)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Невалидный JSON в parser_config: {e}")

        source = await sources_repo.create_source(
            name=name,
            url=url,
            parser_config=parser_config,
            category=category,
            description=description,
            check_interval_minutes=check_interval_minutes,
        )

        return {'id': source.id, 'name': source.name, 'url': source.url}


@router.post('/sources/{source_id}/parse')
async def parse_source(source_id: int) -> Dict[str, Any]:
    """Запустить ручной парсинг источника."""
    from services.web.processor import WebProcessorService

    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)

        web_processor = WebProcessorService(repo_factory=factory)
        received, added = await web_processor.parse_source(source_id)

        return {
            'source_id': source_id,
            'received': received,
            'added': added,
        }


@router.post('/sources/{source_id}/toggle')
async def toggle_source(source_id: int) -> Dict[str, Any]:
    """Переключить активность источника."""
    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        sources_repo = factory.web_sources()

        ok = await sources_repo.toggle_active(source_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Источник не найден")

        return {'success': True}


@router.delete('/sources/{source_id}')
async def delete_source(source_id: int) -> Dict[str, Any]:
    """Удалить источник."""
    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        sources_repo = factory.web_sources()

        ok = await sources_repo.delete_source(source_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Источник не найден")

        return {'success': True}


@router.get('/news')
async def list_web_news(limit: int = 50, processed: bool | None = None) -> Dict[str, Any]:
    """Получить список Web новостей."""
    db_service = get_database_service()
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        news_repo = factory.web_news()

        if processed is None:
            items = await news_repo.get_unprocessed(limit=limit)
        else:
            from sqlalchemy import select
            stmt = (
                select(news_repo.model)
                .where(news_repo.model.processed == processed)
                .order_by(news_repo.model.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            items = result.scalars().all()

        return {
            'web_news': [
                {
                    'id': n.id,
                    'title': n.title,
                    'link': n.link,
                    'category': n.category,
                    'urgency': n.urgency,
                    'processed': n.processed,
                    'source_id': n.source_id,
                    'created_at': n.created_at.isoformat() if n.created_at else None,
                }
                for n in items
            ]
        }
