"""
Session Manager для Web Admin — управление сессиями и аутентификацией.

Хранение учётных данных в SQLite файле .web_admin_session.db
Хэширование паролей через bcrypt
JWT токены с продлением сессии
"""

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import bcrypt
from jose import jwt

logger = logging.getLogger(__name__)

# Константы
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 3  # Время жизни сессии

# Путь к файлу сессии (SQLite в корне проекта)
PROJECT_ROOT = Path(__file__).parent.parent.parent
SESSION_DB_FILE = PROJECT_ROOT / ".web_admin_session.db"


@dataclass
class AdminCredentials:
    """Учётные данные администратора."""
    username: str
    password_hash: str
    created_at: str

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "created_at": self.created_at
        }

    @classmethod
    def from_row(cls, row: tuple) -> "AdminCredentials":
        """Создать из строки БД."""
        return cls(
            username=row[0],
            password_hash=row[1],
            created_at=row[2]
        )


class SessionManager:
    """
    Менеджер сессий для Web Admin.

    Usage:
        manager = SessionManager()

        # Первый запуск - создание учётки
        if not manager.credentials_exist():
            manager.create_credentials("admin", "password123")

        # Проверка пароля
        if manager.verify_password("password123"):
            token = manager.create_token()

        # Проверка токена
        payload = manager.verify_token(token)
    """

    def __init__(self, jwt_secret: Optional[str] = None):
        """
        Инициализация менеджера сессий.

        Args:
            jwt_secret: Секретный ключ для JWT (по умолчанию генерируется)
        """
        self._jwt_secret = jwt_secret or self._get_or_create_jwt_secret()
        self._db_path = SESSION_DB_FILE
        self._init_db()

    def _get_or_create_jwt_secret(self) -> str:
        """
        Получить или создать JWT секрет.

        Хранится в переменной окружения или генерируется.
        Для production использовать из .env!
        """
        import os
        secret = os.getenv("WEB_ADMIN_JWT_SECRET")
        if not secret:
            # Генерируем случайный секрет для текущей сессии
            import secrets
            secret = secrets.token_urlsafe(32)
            logger.warning("⚠️ WEB_ADMIN_JWT_SECRET не установлен, используется временный")
        return secret

    def _init_db(self) -> None:
        """Инициализировать SQLite базу данных."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()

        # Таблица для учётных данных
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
        """)

        # Таблица для сессий (опционально, для будущего расширения)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_activity TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                FOREIGN KEY (username) REFERENCES credentials(username) ON DELETE CASCADE
            )
        """)

        conn.commit()
        conn.close()
        logger.debug(f"✅ БД сессий инициализирована: {self._db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Получить подключение к БД."""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def credentials_exist(self) -> bool:
        """
        Проверить, существуют ли учётные данные.

        Returns:
            True если учётка уже создана
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM credentials")
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0

    def create_credentials(self, username: str, password: str) -> AdminCredentials:
        """
        Создать учётные данные администратора.

        Args:
            username: Имя пользователя (логин)
            password: Пароль (будет захэширован)

        Returns:
            AdminCredentials экземпляр

        Raises:
            ValueError: Если учётка уже существует
        """
        if self.credentials_exist():
            raise ValueError("Учётные данные уже существуют. Удалите файл сессии для сброса.")

        # Хэшируем пароль
        password_hash = self._hash_password(password)

        # Создаём учётные данные
        created_at = datetime.now(timezone.utc).isoformat()

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO credentials (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, password_hash, created_at)
        )
        conn.commit()
        conn.close()

        logger.info(f"✅ Учётная запись '{username}' создана")

        return AdminCredentials(
            username=username,
            password_hash=password_hash,
            created_at=created_at
        )

    def _get_credentials(self) -> Optional[AdminCredentials]:
        """Получить учётные данные из БД."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT username, password_hash, created_at FROM credentials LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        if row:
            return AdminCredentials.from_row(row)
        return None

    def _hash_password(self, password: str) -> str:
        """
        Захэшировать пароль через bcrypt.

        Args:
            password: Пароль в открытом виде

        Returns:
            Хэш пароля
        """
        salt = bcrypt.gensalt(rounds=12)
        password_hash = bcrypt.hashpw(password.encode("utf-8"), salt)
        return password_hash.decode("utf-8")

    def verify_password(self, password: str) -> bool:
        """
        Проверить пароль.

        Args:
            password: Пароль для проверки

        Returns:
            True если пароль верный
        """
        creds = self._get_credentials()
        if not creds:
            return False

        try:
            return bcrypt.checkpw(
                password.encode("utf-8"),
                creds.password_hash.encode("utf-8")
            )
        except Exception as e:
            logger.error(f"❌ Ошибка проверки пароля: {e}")
            return False

    def get_username(self) -> Optional[str]:
        """Получить имя пользователя."""
        creds = self._get_credentials()
        return creds.username if creds else None

    def create_token(self, username: Optional[str] = None) -> str:
        """
        Создать JWT токен сессии.

        Args:
            username: Имя пользователя (по умолчанию из credentials)

        Returns:
            JWT токен
        """
        if username is None:
            creds = self._get_credentials()
            if not creds:
                raise ValueError("Учётные данные не созданы")
            username = creds.username

        expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)

        payload = {
            "sub": username,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "access"
        }

        token = jwt.encode(payload, self._jwt_secret, algorithm=JWT_ALGORITHM)
        logger.debug(f"✅ Создан токен для {username}, истекает {expire}")

        return token

    def verify_token(self, token: str) -> Optional[dict]:
        """
        Проверить и расшифровать JWT токен.

        Args:
            token: JWT токен

        Returns:
            Payload токена или None если недействителен
        """
        try:
            payload = jwt.decode(
                token,
                self._jwt_secret,
                algorithms=[JWT_ALGORITHM]
            )

            # Проверяем тип токена
            if payload.get("type") != "access":
                return None

            # Проверяем, что пользователь существует
            creds = self._get_credentials()
            if creds and payload.get("sub") != creds.username:
                return None

            logger.debug(f"✅ Токен действителен для {payload.get('sub')}")
            return payload

        except jwt.ExpiredSignatureError:
            logger.debug("⏰ Токен истёк")
            return None
        except jwt.JWTError as e:
            logger.debug(f"❌ Ошибка токена: {e}")
            return None

    def refresh_token(self, token: str) -> Optional[str]:
        """
        Обновить токен сессии (продлить сессию).

        Args:
            token: Текущий токен

        Returns:
            Новый токен или None если текущий недействителен
        """
        payload = self.verify_token(token)
        if not payload:
            return None

        # Создаём новый токен с тем же пользователем
        username = payload.get("sub")
        return self.create_token(username)

    def reset_credentials(self) -> None:
        """
        Сбросить учётные данные (удалить файл сессии).

        Используется для сброса пароля.
        """
        if self._db_path.exists():
            self._db_path.unlink()
            logger.info(f"✅ Учётные данные сброшены")
            self._init_db()

    def change_password(self, old_password: str, new_password: str) -> bool:
        """
        Изменить пароль.

        Args:
            old_password: Текущий пароль
            new_password: Новый пароль

        Returns:
            True если пароль изменён успешно
        """
        if not self.verify_password(old_password):
            return False

        # Хэшируем новый пароль
        new_password_hash = self._hash_password(new_password)

        # Обновляем учётные данные в БД
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE credentials SET password_hash = ?, updated_at = ? WHERE username = ?",
            (new_password_hash, datetime.now(timezone.utc).isoformat(), self.get_username())
        )
        conn.commit()
        conn.close()

        logger.info("✅ Пароль изменён")
        return True


# Глобальный singleton
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Получить глобальный менеджер сессий."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


def reset_session_manager() -> None:
    """Сбросить менеджер сессий."""
    global _session_manager
    _session_manager = None
