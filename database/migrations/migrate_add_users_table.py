"""
Миграция: Добавление таблицы пользователей (users).

Поля:
- id: первичный ключ
- user_id_encrypted: зашифрованный ID пользователя Telegram (AES-256-GCM)
- user_id_hash: HMAC-SHA256 хэш для поиска (детерминированный)
- role: роль пользователя ('user', 'admin')
- created_at: дата регистрации
- has_subscription: наличие подписки
- subscription_started_at: дата начала подписки
- subscription_ends_at: дата окончания подписки (NULL = бессрочно)
- preferred_tags: предпочтительные теги (JSON)
- preferred_categories: предпочтительные категории (JSON)

Admin получает бессрочную подписку (subscription_ends_at = NULL).
"""

import logging
import sqlite3
import os
import hmac
from datetime import datetime, timezone
from base64 import b64encode, b64decode
from hashlib import sha256

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = 'db.sqlite3'

DEFAULT_ENCRYPTION_KEY = "news_aggregator_default_key_change_in_prod"


def get_encryption_key() -> bytes:
    """Получить ключ шифрования из окружения или использовать дефолтный."""
    key = os.getenv('ENCRYPTION_KEY', DEFAULT_ENCRYPTION_KEY)
    return sha256(key.encode()).digest()


def encrypt_user_id(user_id: int, key: bytes) -> str:
    """Зашифровать user_id используя AES-256-GCM."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    plaintext = str(user_id).encode('utf-8')
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return b64encode(nonce + ciphertext).decode('utf-8')


def hash_user_id_for_lookup(user_id: int, key: bytes) -> str:
    """Создать детерминированный HMAC-SHA256 хэш для поиска в БД."""
    h = hmac.new(key, str(user_id).encode('utf-8'), 'sha256')
    return b64encode(h.digest()).decode('utf-8')


def decrypt_user_id(encrypted: str, key: bytes) -> int:
    """Расшифровать user_id."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    data = b64decode(encrypted)
    nonce = data[:12]
    ciphertext = data[12:]
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return int(plaintext.decode('utf-8'))


def migrate():
    """Выполнить миграцию."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    key = get_encryption_key()

    try:
        # Создаём таблицу users с новым полем user_id_hash
        logger.info("📦 Создание таблицы users...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id_encrypted TEXT NOT NULL,
                user_id_hash TEXT UNIQUE NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'user',
                created_at DATETIME NOT NULL,
                has_subscription BOOLEAN NOT NULL DEFAULT 0,
                subscription_started_at DATETIME,
                subscription_ends_at DATETIME,
                preferred_tags TEXT NOT NULL DEFAULT '[]',
                preferred_categories TEXT NOT NULL DEFAULT '[]'
            )
        """)

        # Проверяем, есть ли поле user_id_hash в существующей таблице
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'user_id_hash' not in columns:
            logger.info("➕ Добавление поля user_id_hash...")
            cursor.execute("ALTER TABLE users ADD COLUMN user_id_hash TEXT")

            # Заполняем user_id_hash для существующих пользователей
            cursor.execute("SELECT id, user_id_encrypted FROM users WHERE user_id_hash IS NULL")
            users_to_update = cursor.fetchall()

            if users_to_update:
                logger.info(f"🔄 Обновление user_id_hash для {len(users_to_update)} пользователей...")
                for user_id, encrypted in users_to_update:
                    try:
                        telegram_id = decrypt_user_id(encrypted, key)
                        user_hash = hash_user_id_for_lookup(telegram_id, key)
                        cursor.execute(
                            "UPDATE users SET user_id_hash = ? WHERE id = ?",
                            (user_hash, user_id)
                        )
                    except Exception as e:
                        logger.error(f"❌ Ошибка расшифровки для пользователя {user_id}: {e}")

        # Переносим ADMIN_ID в таблицу users как admin с бессрочной подпиской
        from dotenv import load_dotenv
        load_dotenv()
        admin_id = os.getenv('ADMIN_ID')

        if admin_id:
            admin_id = int(admin_id)
            now = datetime.now(timezone.utc).isoformat()

            admin_id_encrypted = encrypt_user_id(admin_id, key)
            admin_id_hash = hash_user_id_for_lookup(admin_id, key)

            # Проверяем по хэшу (детерминированный поиск)
            cursor.execute("SELECT id, role FROM users WHERE user_id_hash = ?", (admin_id_hash,))
            existing = cursor.fetchone()

            if existing:
                logger.info(f"ℹ️ Пользователь {admin_id} уже существует, обновляем роль до admin...")
                cursor.execute("""
                    UPDATE users
                    SET role = 'admin',
                        has_subscription = 1,
                        subscription_started_at = ?,
                        subscription_ends_at = NULL
                    WHERE user_id_hash = ?
                """, (now, admin_id_hash))
            else:
                logger.info(f"➕ Добавление администратора {admin_id} с бессрочной подпиской...")
                cursor.execute("""
                    INSERT INTO users (user_id_encrypted, user_id_hash, role, created_at,
                                       has_subscription, subscription_started_at, subscription_ends_at,
                                       preferred_tags, preferred_categories)
                    VALUES (?, ?, 'admin', ?, 1, ?, NULL, '[]', '[]')
                """, (admin_id_encrypted, admin_id_hash, now, now))

            logger.info(f"✅ Администратор {admin_id} добавлен/обновлён")
        else:
            logger.warning("⚠️ ADMIN_ID не найден в .env файле")

        conn.commit()
        logger.info("✅ Миграция users завершена успешно")

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Ошибка миграции: {e}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    migrate()
