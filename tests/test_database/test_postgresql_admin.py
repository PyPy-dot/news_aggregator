"""
Тесты для PostgreSQL администрирования.

Проверяют:
- PostgreSQLAdmin класс
- Health checks
- Статистику подключений
- Репликацию
- Обслуживание
- Статистику таблиц
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from services.database.postgresql_admin import PostgreSQLAdmin


# =============================================================================
# Вспомогательные функции
# =============================================================================

def make_mock_session():
    """Создать mock сессию."""
    session = AsyncMock()

    # execute возвращает AsyncMock, который при await возвращает MagicMock
    async def execute(*args, **kwargs):
        result = MagicMock()
        return result

    session.execute = execute
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def make_mock_row(data):
    """Создать mock строку с доступом по атрибутам."""
    row = MagicMock()
    for key, value in data.items():
        setattr(row, key, value)
    return row


# =============================================================================
# Тесты PostgreSQLAdmin
# =============================================================================

class TestPostgreSQLAdmin:
    """Тесты для PostgreSQLAdmin."""

    def test_init(self):
        """Тест: инициализация."""
        session = make_mock_session()
        admin = PostgreSQLAdmin(session)

        assert admin.session is session

    @pytest.mark.asyncio
    async def test_check_health_connected(self):
        """Тест: проверка здоровья при подключении."""
        session = make_mock_session()

        admin = PostgreSQLAdmin(session)

        # Mock результаты запросов
        async def execute(*args, **kwargs):
            result = MagicMock()
            if 'count(*)' in str(args[0].compile() if hasattr(args[0], 'compile') else args[0]):
                result.scalar.return_value = 5
            elif 'pg_database_size' in str(args[0]):
                result.scalar.return_value = "125 MB"
            else:
                result.scalar.return_value = "PostgreSQL 14.5"
            return result

        session.execute = execute

        health = await admin.check_health()

        assert health['connected'] is True
        assert health['version'] == "PostgreSQL 14.5"

    @pytest.mark.asyncio
    async def test_check_health_error(self):
        """Тест: проверка здоровья при ошибке."""
        session = make_mock_session()

        async def execute(*args, **kwargs):
            raise Exception("Connection refused")

        session.execute = execute

        admin = PostgreSQLAdmin(session)
        health = await admin.check_health()

        assert health['connected'] is False
        assert len(health['errors']) > 0

    @pytest.mark.asyncio
    async def test_get_connection_stats(self):
        """Тест: статистика подключений."""
        session = make_mock_session()

        admin = PostgreSQLAdmin(session)

        # Mock возврата нескольких строк
        async def execute(*args, **kwargs):
            result = MagicMock()
            result.fetchall.return_value = [
                make_mock_row({
                    'pid': 100,
                    'username': 'news_user',
                    'application_name': 'python',
                    'client_addr': '127.0.0.1',
                    'client_port': 5432,
                    'backend_start': '2026-08-10 10:00:00',
                    'state': 'active',
                    'wait_event_type': None,
                    'wait_event': None,
                    'query': 'SELECT 1',
                    'query_duration_seconds': 0.5,
                }),
                make_mock_row({
                    'pid': 101,
                    'username': 'news_user',
                    'application_name': 'python',
                    'client_addr': '127.0.0.1',
                    'client_port': 5432,
                    'backend_start': '2026-08-10 10:00:01',
                    'state': 'idle',
                    'wait_event_type': 'Client',
                    'wait_event': 'ClientRead',
                    'query': None,
                    'query_duration_seconds': 0.0,
                }),
            ]
            return result

        session.execute = execute

        connections = await admin.get_connection_stats()

        assert len(connections) == 2
        assert connections[0]['pid'] == 100
        assert connections[0]['state'] == 'active'
        assert connections[1]['pid'] == 101
        assert connections[1]['state'] == 'idle'

    @pytest.mark.asyncio
    async def test_get_connection_pool_stats(self):
        """Тест: статистика пула."""
        session = make_mock_session()

        admin = PostgreSQLAdmin(session)

        # Mock get_connection_stats
        connections = [
            {'state': 'active', 'pid': 1},
            {'state': 'active', 'pid': 2},
            {'state': 'idle', 'pid': 3},
            {'state': 'idle', 'pid': 4},
            {'state': 'idle in transaction', 'pid': 5},
        ]
        admin.get_connection_stats = AsyncMock(return_value=connections)

        stats = await admin.get_connection_pool_stats(
            pool_size=10,
            max_overflow=5,
        )

        assert stats['pool_size'] == 10
        assert stats['max_overflow'] == 5
        assert stats['max_possible_connections'] == 15
        assert stats['active_connections'] == 5
        assert stats['active_queries'] == 2
        assert stats['idle_connections'] == 2
        assert stats['idle_in_transaction'] == 1
        assert stats['available_slots'] == 10
        assert stats['utilization_percent'] == round(5 / 15 * 100, 2)

    @pytest.mark.asyncio
    async def test_get_replication_status_enabled(self):
        """Тест: статус репликации."""
        session = make_mock_session()

        admin = PostgreSQLAdmin(session)

        async def execute(*args, **kwargs):
            result = MagicMock()
            result.fetchall.return_value = [
                make_mock_row({
                    'client_addr': '10.0.0.5',
                    'client_port': 5432,
                    'state': 'streaming',
                    'sent_lsn': '0/3000000',
                    'write_lsn': '0/3000000',
                    'flush_lsn': '0/3000000',
                    'replay_lsn': '0/3000000',
                    'lag_seconds': 0.5,
                    'sync_state': 'async',
                }),
            ]
            return result

        session.execute = execute

        status = await admin.get_replication_status()

        assert status['replication_enabled'] is True
        assert status['replica_count'] == 1
        assert status['max_lag_seconds'] == 0.5

    @pytest.mark.asyncio
    async def test_get_replication_status_disabled(self):
        """Тест: статус репликации когда не настроена."""
        session = make_mock_session()

        admin = PostgreSQLAdmin(session)

        async def execute(*args, **kwargs):
            result = MagicMock()
            result.fetchall.return_value = []
            return result

        session.execute = execute

        status = await admin.get_replication_status()

        assert status['replication_enabled'] is False
        assert status['replica_count'] == 0
        assert status['max_lag_seconds'] == 0

    @pytest.mark.asyncio
    async def test_check_replica_health_is_replica(self):
        """Тест: проверка здоровья реплики."""
        session = make_mock_session()

        admin = PostgreSQLAdmin(session)

        # Первый вызов: pg_is_in_recovery() → True
        # Второй вызов: статус восстановления
        call_count = [0]

        async def execute(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()

            if call_count[0] == 1:
                result.scalar.return_value = True
            else:
                result.fetchone.return_value = make_mock_row({
                    'receive_lsn': '0/3000000',
                    'replay_lsn': '0/3000000',
                    'last_timestamp': None,
                })
            return result

        session.execute = execute

        health = await admin.check_replica_health()

        assert health['is_replica'] is True
        assert health['recovery_status'] == 'recovering'

    @pytest.mark.asyncio
    async def test_check_replica_health_not_replica(self):
        """Тест: проверка здоровья не реплики."""
        session = make_mock_session()

        admin = PostgreSQLAdmin(session)

        async def execute(*args, **kwargs):
            result = MagicMock()
            result.scalar.return_value = False
            return result

        session.execute = execute

        health = await admin.check_replica_health()

        assert health['is_replica'] is False

    @pytest.mark.asyncio
    async def test_vacuum_analyze_success(self):
        """Тест: VACUUM ANALYZE успешный."""
        session = make_mock_session()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        admin = PostgreSQLAdmin(session)
        result = await admin.vacuum_analyze(table='posts')

        assert result is True
        session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_vacuum_analyze_error(self):
        """Тест: VACUUM ANALYZE с ошибкой."""
        session = make_mock_session()

        async def execute(*args, **kwargs):
            raise Exception("VACUUM error")

        session.execute = execute
        session.rollback = AsyncMock()

        admin = PostgreSQLAdmin(session)
        result = await admin.vacuum_analyze()

        assert result is False
        session.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_reindex_table(self):
        """Тест: пересоздание индексов."""
        session = make_mock_session()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        admin = PostgreSQLAdmin(session)
        result = await admin.reindex_table(table='posts', concurrent=True)

        assert result is True
        session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_table_stats(self):
        """Тест: статистика таблиц."""
        session = make_mock_session()

        admin = PostgreSQLAdmin(session)

        async def execute(*args, **kwargs):
            result = MagicMock()
            result.fetchall.return_value = [
                make_mock_row({
                    'schemaname': 'public',
                    'table_name': 'posts',
                    'live_rows': 10000,
                    'dead_rows': 50,
                    'last_vacuum': None,
                    'last_autovacuum': '2026-08-10 10:00:00',
                    'last_analyze': None,
                    'last_autoanalyze': '2026-08-10 10:00:00',
                    'total_size': "10 MB",
                    'table_size': "5 MB",
                    'indexes_size': "5 MB",
                }),
            ]
            return result

        session.execute = execute

        tables = await admin.get_table_stats()

        assert len(tables) == 1
        assert tables[0]['table_name'] == 'posts'
        assert tables[0]['live_rows'] == 10000
        assert tables[0]['dead_rows'] == 50
        assert tables[0]['dead_ratio'] == round(50 / 10000 * 100, 2)

    @pytest.mark.asyncio
    async def test_get_slow_queries(self):
        """Тест: долгие запросы."""
        session = make_mock_session()

        admin = PostgreSQLAdmin(session)

        async def execute(*args, **kwargs):
            result = MagicMock()
            result.fetchall.return_value = [
                make_mock_row({
                    'pid': 200,
                    'username': 'news_user',
                    'duration_seconds': 25.5,
                    'state': 'active',
                    'wait_event_type': 'Lock',
                    'wait_event': 'transactionid',
                    'query': 'SELECT * FROM posts WHERE ...',
                }),
            ]
            return result

        session.execute = execute

        queries = await admin.get_slow_queries(min_duration_seconds=1.0)

        assert len(queries) == 1
        assert queries[0]['duration_seconds'] == 25.5
        assert queries[0]['wait_event_type'] == 'Lock'


# =============================================================================
# Тесты helper функций
# =============================================================================

class TestHelpers:
    """Тесты для helper функций."""

    @pytest.mark.asyncio
    async def test_check_postgresql_health(self):
        """Тест: helper для health check."""
        from services.database.postgresql_admin import check_postgresql_health

        session = AsyncMock()

        async def execute(*args, **kwargs):
            return MagicMock()

        session.execute = execute

        health = await check_postgresql_health(session)

        assert isinstance(health, dict)

    @pytest.mark.asyncio
    async def test_get_connection_pool_stats(self):
        """Тест: helper для статистики пула."""
        from services.database.postgresql_admin import get_connection_pool_stats

        session = AsyncMock()

        async def execute(*args, **kwargs):
            return MagicMock()

        session.execute = execute

        stats = await get_connection_pool_stats(session, pool_size=10, max_overflow=5)

        assert isinstance(stats, dict)