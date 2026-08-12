# 🐘 Production PostgreSQL Настройка

**Версия:** 1.0  
**Дата:** 2026-08-10

---

## 📋 Обзор

Настройка PostgreSQL для production-развёртывания News Aggregator включает:

- Connection pooling (asyncpg)
- Репликация (master-slave)
- Оптимизация параметров СУБД
- Health checks
- Мониторинг и алерты

---

## 🏗️ Архитектура

### Production конфигурация

```
┌─────────────────────────────────────────────────────────────┐
│                    News Aggregator                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Connection Pool (asyncpg)                          │   │
│  │  • pool_size: 20                                    │   │
│  │  • max_overflow: 10                                 │   │
│  │  • pool_timeout: 30s                                │   │
│  │  • pool_recycle: 1800s                              │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    PostgreSQL Master                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  • shared_buffers: 4GB                              │   │
│  │  • effective_cache_size: 12GB                       │   │
│  │  • work_mem: 64MB                                   │   │
│  │  • max_connections: 200                             │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────┬───────────────────────────────────────┘
                      │
         ┌────────────┴────────────┐
         ▼                         ▼
┌─────────────────┐     ┌─────────────────┐
│  Replica 1      │     │  Replica 2      │
│  (read-only)    │     │  (read-only)    │
└─────────────────┘     └─────────────────┘
```

---

## ⚙️ Настройка connection pooling

### Базовая конфигурация

```python
# config/settings.py
class Settings(BaseSettings):
    # Database pool settings
    db_pool_size: int = Field(default=20, description="Размер пула подключений")
    db_max_overflow: int = Field(default=10, description="Макс. превышение пула")
    db_pool_timeout: int = Field(default=30, description="Таймаут ожидания (сек)")
    db_pool_recycle: int = Field(default=1800, description="Время пересоздания (сек)")
    db_echo: bool = Field(default=False, description="Логирование SQL")
```

### Рекомендации по размеру пула

| Кол-во потоков | pool_size | max_overflow | pool_timeout |
|----------------|-----------|--------------|--------------|
| **< 10** | 10 | 5 | 30s |
| **10-50** | 20 | 10 | 30s |
| **50-100** | 40 | 20 | 30s |
| **> 100** | 80 | 40 | 30s |

### Формула расчёта

```
pool_size = (ядра_CPU × 2) + эффективный_диск
max_overflow = pool_size × 0.5
pool_timeout = 30 (секунд)
pool_recycle = 1800 (30 минут)
```

**Пример для 8 ядер:**
```
pool_size = (8 × 2) + 1 = 17 → округляем до 20
max_overflow = 20 × 0.5 = 10
```

---

## 📊 Оптимизация параметров PostgreSQL

### postgresql.conf

```ini
# =============================================================================
# ПАМЯТЬ
# =============================================================================

# shared_buffers: 25% от RAM (но не более 8GB)
# Для сервера с 16GB RAM:
shared_buffers = 4GB

# effective_cache_size: 75% от RAM
effective_cache_size = 12GB

# work_mem: для сортировок и хешей
# (RAM / max_connections) / 4
work_mem = 64MB

# maintenance_work_mem: для VACUUM, CREATE INDEX
maintenance_work_mem = 1GB

# =============================================================================
# ПОДКЛЮЧЕНИЯ
# =============================================================================

max_connections = 200

# =============================================================================
# WAL (Write-Ahead Logging)
# =============================================================================

# WAL уровень
wal_level = replica

# Макс. слотов репликации
max_replication_slots = 5

# Макс. WAL отправителей
max_wal_senders = 5

# Мин. задержка между WAL отправлениями
wal_sender_timeout = 60s

# =============================================================================
# РЕПЛИКАЦИЯ
# =============================================================================

# Синхронная репликация (опционально)
# synchronous_standby_names = 'replica1,replica2'

# Задержка применения WAL на реплике
hot_standby_feedback = on

# =============================================================================
# АВТО-ОБСЛУЖИВАНИЕ
# =============================================================================

# Auto-vacuum
autovacuum = on
autovacuum_max_workers = 3
autovacuum_naptime = 60s
autovacuum_vacuum_threshold = 50
autovacuum_analyze_threshold = 50

# =============================================================================
# ЛОГИРОВАНИЕ
# =============================================================================

logging_collector = on
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_rotation_age = 1d
log_rotation_size = 100MB

# Медленные запросы (> 1000ms)
log_min_duration_statement = 1000

# Чекпоинты
log_checkpoints = on

# Блокировки
log_lock_waits = on

# =============================================================================
# ПРОИЗВОДИТЕЛЬНОСТЬ
# =============================================================================

# Random page cost (для SSD)
random_page_cost = 1.1

# Effective I/O concurrency (для SSD)
effective_io_concurrency = 200

# Parallel workers
max_parallel_workers_per_gather = 2
max_parallel_workers = 4
```

### pg_hba.conf

```conf
# =============================================================================
# PostgreSQL Client Authentication Configuration File
# =============================================================================

# TYPE  DATABASE        USER            ADDRESS                 METHOD

# Local connections
local   all             all                                     peer

# IPv4 local connections
host    all             all             127.0.0.1/32            scram-sha-256

# IPv6 local connections
host    all             all             ::1/128                 scram-sha-256

# Replication connections (для реплик)
host    replication     replicator      10.0.0.0/8              scram-sha-256

# Production connections (ограничить по IP)
host    news_aggregator news_user       10.0.1.0/24             scram-sha-256
```

---

## 🔁 Настройка репликации

### Master конфигурация

```ini
# postgresql.conf (Master)

wal_level = replica
max_wal_senders = 5
max_replication_slots = 5
wal_keep_size = 1GB

# Архивирование WAL (опционально для point-in-time recovery)
archive_mode = on
archive_command = 'cp %p /var/lib/postgresql/archive/%f'
```

### Создание репликационного пользователя

```sql
-- На Master
CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD 'secure_replication_password';
```

### Replica конфигурация

```ini
# postgresql.conf (Replica)

hot_standby = on
primary_conninfo = 'host=master_ip port=5432 user=replicator password=secure_replication_password'
primary_slot_name = 'replica1'
```

### Инициализация реплики

```bash
# На Replica
pg_basebackup -h master_ip -D /var/lib/postgresql/data -U replicator -P -v -R -X stream -C -S replica1
```

---

## 🏥 Health checks

### SQL проверки

```sql
-- Проверка подключения
SELECT 1;

-- Проверка репликации (на Master)
SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn
FROM pg_stat_replication;

-- Проверка задержки реплики (на Replica)
SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp())) AS lag_seconds;

-- Проверка размера БД
SELECT pg_size_pretty(pg_database_size('news_aggregator'));

-- Проверка активных подключений
SELECT count(*) as active_connections
FROM pg_stat_activity
WHERE datname = 'news_aggregator';

-- Проверка долгих запросов
SELECT pid, now() - pg_stat_activity.query_start AS duration, query
FROM pg_stat_activity
WHERE (now() - pg_stat_activity.query_start) > interval '5 minutes'
  AND datname = 'news_aggregator';
```

### Python health check

```python
from services.monitoring.health_check import ComponentHealth, HealthStatus, SeverityLevel

async def check_postgresql_health() -> ComponentHealth:
    """Проверка здоровья PostgreSQL."""
    from services.database import get_database_service
    from sqlalchemy import text
    
    start_time = time.time()
    
    try:
        db_service = get_database_service()
        
        async with db_service.session_factory() as session:
            # Базовая проверка
            await session.execute(text("SELECT 1"))
            
            # Проверка подключений
            result = await session.execute(text("""
                SELECT count(*) as active_connections
                FROM pg_stat_activity
                WHERE datname = current_database()
            """))
            active_connections = result.scalar()
            
            # Проверка репликации (если настроена)
            result = await session.execute(text("""
                SELECT count(*) as replica_count
                FROM pg_stat_replication
            """))
            replica_count = result.scalar()
        
        latency_ms = (time.time() - start_time) * 1000
        
        return ComponentHealth(
            name="postgresql",
            status=HealthStatus.HEALTHY,
            severity=SeverityLevel.CRITICAL,
            message=f"PostgreSQL подключён ({active_connections} активных подключений)",
            latency_ms=latency_ms,
            details={
                "active_connections": active_connections,
                "replica_count": replica_count,
                "pool_size": db_service.config.pool_size,
            },
        )
        
    except Exception as e:
        return ComponentHealth(
            name="postgresql",
            status=HealthStatus.UNHEALTHY,
            severity=SeverityLevel.CRITICAL,
            message=f"PostgreSQL ошибка: {type(e).__name__}: {e}",
            latency_ms=(time.time() - start_time) * 1000,
        )
```

---

## 📈 Мониторинг

### Prometheus метрики

```python
from prometheus_client import Gauge, Counter, Histogram

# Метрики
pg_connections = Gauge('postgresql_connections', 'Active connections', ['database'])
pg_replication_lag = Gauge('postgresql_replication_lag_seconds', 'Replication lag', ['replica'])
pg_query_duration = Histogram('postgresql_query_duration_seconds', 'Query duration', ['query_type'])
pg_errors = Counter('postgresql_errors_total', 'Database errors', ['error_type'])

# Обновление метрик
async def update_postgresql_metrics():
    """Обновить метрики PostgreSQL."""
    from services.database import get_database_service
    from sqlalchemy import text
    
    db_service = get_database_service()
    
    async with db_service.session_factory() as session:
        # Активные подключения
        result = await session.execute(text("""
            SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()
        """))
        pg_connections.labels(database='news_aggregator').set(result.scalar())
        
        # Задержка реплики
        result = await session.execute(text("""
            SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))
            FROM pg_stat_replication
        """))
        for row in result.fetchall():
            pg_replication_lag.labels(replica='replica1').set(row[0] or 0)
```

### Grafana дашборд

**Ключевые панели:**

1. **Active Connections**
   ```promql
   postgresql_connections{database="news_aggregator"}
   ```

2. **Replication Lag**
   ```promql
   postgresql_replication_lag_seconds
   ```

3. **Query Duration (p95)**
   ```promql
   histogram_quantile(0.95, rate(postgresql_query_duration_seconds_bucket[5m]))
   ```

4. **Error Rate**
   ```promql
   rate(postgresql_errors_total[5m])
   ```

---

## 🚨 Алерты

### Prometheus alert rules

```yaml
# postgresql_alerts.yml
groups:
  - name: postgresql
    rules:
      # Высокая загрузка подключений
      - alert: PostgreSQLHighConnections
        expr: postgresql_connections > 150
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Высокая загрузка подключений PostgreSQL"
          description: "{{ $value }} активных подключений"

      # Большая задержка реплики
      - alert: PostgreSQLReplicationLag
        expr: postgresql_replication_lag_seconds > 60
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Большая задержка реплики PostgreSQL"
          description: "Задержка реплики: {{ $value }} секунд"

      # Ошибки подключения
      - alert: PostgreSQLConnectionErrors
        expr: rate(postgresql_errors_total{error_type="connection"}[5m]) > 0.1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Ошибки подключения PostgreSQL"
          description: "{{ $value }} ошибок в секунду"

      # Долгие запросы
      - alert: PostgreSQLSlowQueries
        expr: histogram_quantile(0.95, rate(postgresql_query_duration_seconds_bucket[5m])) > 1
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Медленные запросы PostgreSQL"
          description: "p95 latency: {{ $value }}s"
```

---

## 🔧 Обслуживание

### VACUUM и ANALYZE

```sql
-- Авто-вакуум включен по умолчанию
-- Проверка последних vacuum
SELECT relname, last_vacuum, last_autovacuum, last_analyze, last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'public';

-- Ручной vacuum (если нужно)
VACUUM ANALYZE;

-- Vacuum конкретной таблицы
VACUUM ANALYZE posts;
```

### Пересоздание индексов

```sql
-- Пересоздание индекса (online в PostgreSQL 12+)
REINDEX INDEX CONCURRENTLY idx_posts_category;

-- Пересоздание всех индексов таблицы
REINDEX TABLE CONCURRENTLY posts;
```

### Обновление статистики

```sql
-- Обновление статистики для оптимизатора
ANALYZE posts;
ANALYZE channels;
ANALYZE generated_news;
```

---

## 📝 Changelog

### v1.0 (2026-08-10)
- ✅ Connection pooling конфигурация
- ✅ Оптимизация параметров PostgreSQL
- ✅ Настройка репликации (master-slave)
- ✅ Health checks (SQL + Python)
- ✅ Prometheus метрики
- ✅ Grafana дашборд
- ✅ Prometheus alert rules
- ✅ Обслуживание (VACUUM, REINDEX)

---

**Автор:** AI-агент Стефания  
**Связанные документы:**
- [POSTGRESQL_SETUP.md](POSTGRESQL_SETUP.md) — базовая настройка PostgreSQL
- [HEALTH_CHECK_SETUP.md](HEALTH_CHECK_SETUP.md) — health check API
- [MONITORING_SETUP.md](MONITORING_SETUP.md) — общий мониторинг
- [DOCKER_SETUP.md](DOCKER_SETUP.md) — Docker развёртывание
