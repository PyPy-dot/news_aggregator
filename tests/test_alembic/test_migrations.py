"""
Тесты миграций Alembic для News Aggregator.

Проверка работы миграций с SQLite и PostgreSQL.
"""

import pytest
import os
import tempfile
from pathlib import Path


@pytest.fixture
def temp_db_path():
    """Создать временный файл БД."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    yield db_path
    # Очистка после теста
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestAlembicMigrations:
    """Тесты для Alembic миграций."""

    def test_alembic_config_exists(self):
        """Проверка наличия alembic.ini."""
        alembic_ini = Path('alembic.ini')
        assert alembic_ini.exists(), "alembic.ini не найден"

    def test_alembic_env_exists(self):
        """Проверка наличия env.py."""
        env_py = Path('alembic/env.py')
        assert env_py.exists(), "alembic/env.py не найден"

    def test_alembic_versions_dir_exists(self):
        """Проверка наличия директории миграций."""
        versions_dir = Path('alembic/versions')
        assert versions_dir.exists(), "alembic/versions не найдена"
        assert versions_dir.is_dir(), "alembic/versions должна быть директорией"

    def test_alembic_has_migrations(self):
        """Проверка наличия миграций в versions."""
        versions_dir = Path('alembic/versions')
        migration_files = list(versions_dir.glob('*.py'))
        assert len(migration_files) > 0, "Нет файлов миграций в alembic/versions/"

    def test_env_imports_settings(self):
        """Проверка, что env.py импортирует настройки."""
        env_py = Path('alembic/env.py')
        content = env_py.read_text()

        assert 'from config.settings import settings' in content
        assert 'database_url_resolved' in content or 'database_url' in content

    def test_env_supports_postgresql(self):
        """Проверка, что env.py поддерживает PostgreSQL."""
        env_py = Path('alembic/env.py')
        content = env_py.read_text()

        # Проверка поддержки PostgreSQL
        assert 'postgresql' in content
        assert 'asyncpg' in content

    def test_env_supports_sqlite(self):
        """Проверка, что env.py поддерживает SQLite."""
        env_py = Path('alembic/env.py')
        content = env_py.read_text()

        # Проверка поддержки SQLite
        assert 'sqlite' in content
        assert 'aiosqlite' in content

    def test_env_url_conversion(self):
        """Проверка конверсии URL для Alembic."""
        env_py = Path('alembic/env.py')
        content = env_py.read_text()

        # Проверка конверсии async -> sync драйверов
        assert 'replace' in content  # Метод замены
        assert '+aiosqlite' in content or 'aiosqlite' in content
        assert '+asyncpg' in content or 'asyncpg' in content


class TestPostgreSQLSetup:
    """Тесты настройки PostgreSQL."""

    def test_asyncpg_in_requirements(self):
        """Проверка наличия asyncpg в requirements.txt."""
        requirements = Path('requirements.txt')
        content = requirements.read_text()

        assert 'asyncpg' in content

    def test_postgresql_setup_doc_exists(self):
        """Проверка наличия документации по PostgreSQL."""
        doc_path = Path('docs/POSTGRESQL_SETUP.md')
        assert doc_path.exists(), "docs/POSTGRESQL_SETUP.md не найден"

    def test_postgresql_setup_content(self):
        """Проверка содержания POSTGRESQL_SETUP.md."""
        doc_path = Path('docs/POSTGRESQL_SETUP.md')
        content = doc_path.read_text()

        # Проверка ключевых разделов
        assert 'DATABASE_URL' in content
        assert 'postgresql+asyncpg' in content
        assert 'alembic upgrade head' in content

    def test_readme_mentions_postgresql(self):
        """Проверка, что README упоминает PostgreSQL."""
        readme = Path('README.md')
        content = readme.read_text()

        assert 'PostgreSQL' in content or 'postgresql' in content


@pytest.mark.integration
class TestAlembicMigrationRun:
    """Интеграционные тесты миграций Alembic.

    Требуют наличия базы данных.
    """

    def test_alembic_upgrade_sqlite(self, temp_db_path):
        """Проверка применения миграций на SQLite.

        Примечание: Этот тест требует запуска Alembic через subprocess.
        """
        import subprocess

        sqlite_db_url = f'sqlite+aiosqlite:///{temp_db_path}'

        # Пропускаем тест если нет alembic в PATH
        try:
            result = subprocess.run(
                ['alembic', '--version'],
                capture_output=True,
                timeout=5
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Alembic не установлен или не в PATH")

        # Устанавливаем DATABASE_URL для теста
        env = os.environ.copy()
        env['DATABASE_URL'] = sqlite_db_url.replace('+aiosqlite', '')

        # Применяем миграции
        result = subprocess.run(
            ['alembic', 'upgrade', 'head'],
            capture_output=True,
            text=True,
            timeout=30,
            env=env
        )

        # Проверка результата
        if result.returncode != 0:
            pytest.fail(f"Alembic migration failed:\n{result.stderr}\n{result.stdout}")

        # Проверка успешного применения миграций
        # Alembic выводит "Context impl SQLiteImpl" или "Context impl PostgreSQLImpl"
        assert 'Context impl' in result.stderr or 'SQLite' in result.stdout or 'PostgreSQL' in result.stdout

    def test_alembic_current(self, temp_db_path):
        """Проверка текущей ревизии Alembic."""
        import subprocess

        sqlite_db_url = f'sqlite+aiosqlite:///{temp_db_path}'

        try:
            result = subprocess.run(
                ['alembic', '--version'],
                capture_output=True,
                timeout=5
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Alembic не установлен или не в PATH")

        env = os.environ.copy()
        env['DATABASE_URL'] = sqlite_db_url.replace('+aiosqlite', '')

        # Получаем текущую ревизию
        result = subprocess.run(
            ['alembic', 'current'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )

        # Должна быть хотя бы одна ревизия
        if result.returncode == 0:
            assert len(result.stdout.strip()) > 0
