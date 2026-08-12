# =============================================================================
# News Aggregator — Dockerfile для основного приложения
# =============================================================================
# Этапы:
# 1. Builder — установка зависимостей
# 2. Final — минимальный образ для запуска
# =============================================================================

FROM python:3.12-slim as builder

WORKDIR /app

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir --user -r requirements.txt

# =============================================================================
# Final stage
# =============================================================================

FROM python:3.12-slim

WORKDIR /app

# Создаём пользователя для безопасности
RUN groupadd -r newsaggregator && useradd -r -g newsaggregator newsaggregator

# Системные зависимости (минимальные)
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Копируем установленные пакеты из builder
COPY --from=builder /root/.local /home/newsaggregator/.local

# Копируем код приложения
COPY . .

# Устанавливаем PATH
ENV PATH=/home/newsaggregator/.local/bin:$PATH
ENV PYTHONPATH=/app

# Переключаемся на не-root пользователя
USER newsaggregator

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Порты
# 8000 — основное приложение
# 8001 — web админка
EXPOSE 8000 8001

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8001/health', timeout=5)" || exit 1

# Запуск приложения
CMD ["python", "main.py"]
