"""
PostgreSQL Utilities — утилиты для администрирования PostgreSQL.

Включает:
- Проверка состояния БД
- Настройка connection pooling
- Мониторинг репликации
- Обслуживание (VACUUM, ANALYZE, REINDEX)
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PostgreSQLAdmin:
    """
    Утилиты для администрирования PostgreSQL.

    Usage:
        admin = PostgreSQLAdmin(session)

        # Проверка состояния
        health = await admin.check_health()

        # Статистика подключений
        stats = await admin.get_connection_stats()

        # Обслуживание
        await admin.vacuum_analyze(table='posts')
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Инициализация администратора.

        Args:
            session: SQLAlchemy async сессия
        """
        self.session = session

    # =============================================================================
    # Health checks
    # =============================================================================

    async def check_health(self) -> Dict[str, Any]:
        """
        Проверка здоровья PostgreSQL.

        Returns:
            Dict со статусом и деталями
        """
        result = {
            'connected': False,
            'version': None,
            'active_connections': 0,
            'max_connections': 0,
            'replication_lag_seconds': None,
            'database_size_mb': 0,
            'errors': [],
        }

        try:
            # Базовая проверка подключения
            db_result = await self.session.execute(text("SELECT 1"))
            result['connected'] = True

            # Версия PostgreSQL
            version_result = await self.session.execute(text("SELECT version()"))
            result['version'] = version_result.scalar()

            # Активные подключения
            conn_result = await self.session.execute(text("""
                SELECT count(*) as active_connections
                FROM pg_stat_activity
                WHERE datname = current_database()
            """))
            result['active_connections'] = conn_result.scalar()

            # Макс. подключения
            max_conn_result = await self.session.execute(text("""
                SELECT setting::int as max_connections
                FROM pg_settings
                WHERE name = 'max_connections'
            """))
            result['max_connections'] = max_conn_result.scalar()

            # Задержка реплики (если репликация настроена)
            try:
                lag_result = await self.session.execute(text("""
                    SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))
                    FROM pg_stat_replication
                    LIMIT 1
                """))
                lag_row = lag_result.fetchone()
                if lag_row and lag_row[0] is not None:
                    result['replication_lag_seconds'] = float(lag_row[0])
            except Exception:
                # Репликация не настроена
                pass

            # Размер БД
            size_result = await self.session.execute(text("""
                SELECT pg_size_pretty(pg_database_size(current_database())) as size
            """))
            result['database_size'] = size_result.scalar()

            # Размер в MB для метрик
            size_mb_result = await self.session.execute(text("""
                SELECT pg_database_size(current_database()) / (1024 * 1024) as size_mb
            """))
            result['database_size_mb'] = size_mb_result.scalar()

        except Exception as e:
            result['errors'].append(f"{type(e).__name__}: {e}")

        return result

    # =============================================================================
    # Connection statistics
    # =============================================================================

    async def get_connection_stats(self) -> List[Dict[str, Any]]:
        """
        Получить статистику подключений.

        Returns:
            Список подключений с деталями
        """
        result = await self.session.execute(text("""
            SELECT
                pid,
                usename as username,
                application_name,
                client_addr,
                client_port,
                backend_start,
                state,
                wait_event_type,
                wait_event,
                query,
                EXTRACT(EPOCH FROM (now() - query_start)) as query_duration_seconds
            FROM pg_stat_activity
            WHERE datname = current_database()
            ORDER BY query_start
        """))

        connections = []
        for row in result.fetchall():
            connections.append({
                'pid': row.pid,
                'username': row.username,
                'application_name': row.application_name,
                'client_addr': str(row.client_addr),
                'client_port': row.client_port,
                'backend_start': str(row.backend_start),
                'state': row.state,
                'wait_event_type': row.wait_event_type,
                'wait_event': row.wait_event,
                'query': row.query[:200] if row.query else None,
                'query_duration_seconds': float(row.query_duration_seconds) if row.query_duration_seconds else 0,
            })

        return connections

    async def get_connection_pool_stats(self, pool_size: int, max_overflow: int) -> Dict[str, Any]:
        """
        Получить статистику пула подключений.

        Args:
            pool_size: Размер пула
            max_overflow: Макс. превышение

        Returns:
            Dict со статистикой пула
        """
        connections = await self.get_connection_stats()

        active = sum(1 for c in connections if c['state'] == 'active')
        idle = sum(1 for c in connections if c['state'] == 'idle')
        idle_in_transaction = sum(1 for c in connections if c['state'] == 'idle in transaction')

        return {
            'pool_size': pool_size,
            'max_overflow': max_overflow,
            'max_possible_connections': pool_size + max_overflow,
            'active_connections': len(connections),
            'active_queries': active,
            'idle_connections': idle,
            'idle_in_transaction': idle_in_transaction,
            'available_slots': (pool_size + max_overflow) - len(connections),
            'utilization_percent': round(len(connections) / (pool_size + max_overflow) * 100, 2),
        }

    # =============================================================================
    # Replication monitoring
    # =============================================================================

    async def get_replication_status(self) -> Dict[str, Any]:
        """
        Получить статус репликации (на Master).

        Returns:
            Dict со статусом репликации
        """
        result = await self.session.execute(text("""
            SELECT
                client_addr,
                client_port,
                state,
                sent_lsn,
                write_lsn,
                flush_lsn,
                replay_lsn,
                EXTRACT(EPOCH FROM (now() - reply_time)) as lag_seconds,
                sync_state
            FROM pg_stat_replication
        """))

        replicas = []
        for row in result.fetchall():
            replicas.append({
                'client_addr': str(row.client_addr),
                'client_port': row.client_port,
                'state': row.state,
                'sent_lsn': str(row.sent_lsn),
                'write_lsn': str(row.write_lsn),
                'flush_lsn': str(row.flush_lsn),
                'replay_lsn': str(row.replay_lsn),
                'lag_seconds': float(row.lag_seconds) if row.lag_seconds else 0,
                'sync_state': row.sync_state,
            })

        return {
            'replication_enabled': len(replicas) > 0,
            'replica_count': len(replicas),
            'replicas': replicas,
            'max_lag_seconds': max((r['lag_seconds'] for r in replicas), default=0),
        }

    async def check_replica_health(self) -> Dict[str, Any]:
        """
        Проверить здоровье реплики (на Replica).

        Returns:
            Dict со статусом реплики
        """
        result = {
            'is_replica': False,
            'recovery_status': None,
            'last_wal_receive': None,
            'last_wal_replay': None,
            'lag_seconds': None,
        }

        # Проверка является ли сервер репликой
        is_replica_result = await self.session.execute(text("SELECT pg_is_in_recovery()"))
        result['is_replica'] = is_replica_result.scalar()

        if result['is_replica']:
            # Статус восстановления
            recovery_result = await self.session.execute(text("""
                SELECT
                    pg_last_wal_receive_lsn() as receive_lsn,
                    pg_last_wal_replay_lsn() as replay_lsn,
                    pg_last_xact_replay_timestamp() as last_timestamp
            """))
            row = recovery_result.fetchone()

            if row:
                result['recovery_status'] = 'recovering' if row.receive_lsn else 'stopped'
                result['last_wal_receive'] = str(row.receive_lsn) if row.receive_lsn else None
                result['last_wal_replay'] = str(row.replay_lsn) if row.replay_lsn else None

                if row.last_timestamp:
                    result['lag_seconds'] = (datetime.now() - row.last_timestamp).total_seconds()

        return result

    # =============================================================================
    # Maintenance
    # =============================================================================

    async def vacuum_analyze(self, table: Optional[str] = None) -> bool:
        """
        Выполнить VACUUM ANALYZE.

        Args:
            table: Имя таблицы (None = все таблицы)

        Returns:
            True если успешно
        """
        try:
            if table:
                await self.session.execute(text(f"VACUUM ANALYZE {table}"))
                logger.info(f"✅ VACUUM ANALYZE выполнен для таблицы '{table}'")
            else:
                await self.session.execute(text("VACUUM ANALYZE"))
                logger.info("✅ VACUUM ANALYZE выполнен для всех таблиц")

            await self.session.commit()
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка VACUUM ANALYZE: {e}")
            await self.session.rollback()
            return False

    async def reindex_table(self, table: str, concurrent: bool = True) -> bool:
        """
        Пересоздать индексы таблицы.

        Args:
            table: Имя таблицы
            concurrent: Online режим (не блокирует запись)

        Returns:
            True если успешно
        """
        try:
            mode = "CONCURRENTLY" if concurrent else ""
            await self.session.execute(text(f"REINDEX TABLE {mode} {table}"))
            await self.session.commit()

            logger.info(f"✅ Индексы таблицы '{table}' пересозданы")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка REINDEX: {e}")
            await self.session.rollback()
            return False

    async def get_table_stats(self) -> List[Dict[str, Any]]:
        """
        Получить статистику по таблицам.

        Returns:
            Список статистик таблиц
        """
        result = await self.session.execute(text("""
            SELECT
                schemaname,
                relname as table_name,
                n_live_tup as live_rows,
                n_dead_tup as dead_rows,
                last_vacuum,
                last_autovacuum,
                last_analyze,
                last_autoanalyze,
                pg_size_pretty(pg_total_relation_size(relid)) as total_size,
                pg_size_pretty(pg_relation_size(relid)) as table_size,
                pg_size_pretty(pg_indexes_size(relid)) as indexes_size
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
            ORDER BY n_live_tup DESC
        """))

        tables = []
        for row in result.fetchall():
            tables.append({
                'schema': row.schemaname,
                'table_name': row.table_name,
                'live_rows': row.live_rows,
                'dead_rows': row.dead_rows,
                'dead_ratio': round(row.dead_rows / max(row.live_rows, 1) * 100, 2),
                'last_vacuum': str(row.last_vacuum) if row.last_vacuum else None,
                'last_autovacuum': str(row.last_autovacuum) if row.last_autovacuum else None,
                'last_analyze': str(row.last_analyze) if row.last_analyze else None,
                'last_autoanalyze': str(row.last_autoanalyze) if row.last_autoanalyze else None,
                'total_size': row.total_size,
                'table_size': row.table_size,
                'indexes_size': row.indexes_size,
            })

        return tables

    async def get_slow_queries(self, min_duration_seconds: float = 1.0) -> List[Dict[str, Any]]:
        """
        Получить долгие запросы.

        Args:
            min_duration_seconds: Мин. длительность (сек)

        Returns:
            Список долгих запросов
        """
        result = await self.session.execute(text("""
            SELECT
                pid,
                usename as username,
                EXTRACT(EPOCH FROM (now() - query_start)) as duration_seconds,
                state,
                wait_event_type,
                wait_event,
                query
            FROM pg_stat_activity
            WHERE (now() - query_start) > interval ':min_duration seconds'
              AND datname = current_database()
              AND state != 'idle'
            ORDER BY duration_seconds DESC
        """).bindparams(min_duration=min_duration_seconds))

        queries = []
        for row in result.fetchall():
            queries.append({
                'pid': row.pid,
                'username': row.username,
                'duration_seconds': float(row.duration_seconds),
                'state': row.state,
                'wait_event_type': row.wait_event_type,
                'wait_event': row.wait_event,
                'query': row.query[:500] if row.query else None,
            })

        return queries


# =============================================================================
# Helper функции
# =============================================================================

async def check_postgresql_health(session: AsyncSession) -> Dict[str, Any]:
    """
    Проверить здоровье PostgreSQL.

    Args:
        session: SQLAlchemy async сессия

    Returns:
        Dict со статусом здоровья
    """
    admin = PostgreSQLAdmin(session)
    return await admin.check_health()


async def get_connection_pool_stats(
    session: AsyncSession,
    pool_size: int,
    max_overflow: int
) -> Dict[str, Any]:
    """
    Получить статистику пула подключений.

    Args:
        session: SQLAlchemy async сессия
        pool_size: Размер пула
        max_overflow: Макс. превышение

    Returns:
        Dict со статистикой пула
    """
    admin = PostgreSQLAdmin(session)
    return await admin.get_connection_pool_stats(pool_size, max_overflow)


__all__ = [
    'PostgreSQLAdmin',
    'check_postgresql_health',
    'get_connection_pool_stats',
]
