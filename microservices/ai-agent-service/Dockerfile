# =============================================================================
# AI Agent Microservice Dockerfile
# =============================================================================

FROM python:3.12-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код сервиса
COPY app/ ./app/

# Копируем общие модули из основного проекта (агенты, настройки)
COPY --from=news-aggregator-app /app/services/ ./services/
COPY --from=news-aggregator-app /app/config/ ./config/
COPY --from=news-aggregator-app /app/prompts/ ./prompts/
COPY --from=news-aggregator-app /app/database/ ./database/

# Экспортируем порт
EXPOSE 8002

# Запускаем сервис
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
