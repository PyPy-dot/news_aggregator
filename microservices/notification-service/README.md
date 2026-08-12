# Notification Service

Сервис для отправки уведомлений (Telegram Bot API).

## Архитектура

```
notification-service/
├── src/
│   ├── __init__.py
│   ├── main.py              # Точка входа
│   ├── telegram_client.py   # Telegram клиент
│   ├── sender.py            # Отправщик уведомлений
│   ├── retry.py             # Retry логика
│   └── api.py               # REST/gRPC API
├── tests/
├── configs/
│   ├── dev.yaml
│   └── prod.yaml
├── Dockerfile
├── requirements.txt
└── README.md
```

## API

### REST Endpoints

#### POST /v1/notify/admin
Уведомление админа:
```json
{
  "admin_id": 123456,
  "message": "Текст уведомления",
  "news_id": 789,
  "type": "moderation"
}
```

#### POST /v1/notify/subscriber
Уведомление подписчика:
```json
{
  "subscriber_id": 8038455907,
  "news_id": 168,
  "message": "Текст новости",
  "retry_count": 3
}
```

#### POST /v1/broadcast
Рассылка всем подписчикам:
```json
{
  "message": "Текст рассылки",
  "filter": {
    "subscription_type": "premium"
  }
}
```

### gRPC Service

```protobuf
service NotificationService {
  rpc NotifyAdmin(NotifyAdminRequest) returns (NotifyAdminResponse);
  rpc NotifySubscriber(NotifySubscriberRequest) returns (NotifySubscriberResponse);
  rpc Broadcast(BroadcastRequest) returns (BroadcastResponse);
}
```

## Конфигурация

```yaml
server:
  host: 0.0.0.0
  port: 8003

telegram:
  bot_token: ${BOT_TOKEN}
  timeout_seconds: 60

retry:
  max_attempts: 3
  base_delay_seconds: 1
  max_delay_seconds: 30

rate_limit:
  messages_per_second: 30
```

## Запуск

### Development
```bash
python src/main.py --config configs/dev.yaml
```

### Docker
```bash
docker build -t news-aggregator/notification-service:latest .
docker run -p 8003:8003 --env-file .env news-aggregator/notification-service:latest
```

## Метрики

- `notifications_sent_total` — всего отправлено
- `notifications_failed_total` — всего ошибок
- `notification_retry_count` — количество retry
- `notification_duration_seconds` — время отправки

---

**Версия:** 1.0.0  
**Статус:** 🚧 В разработке
