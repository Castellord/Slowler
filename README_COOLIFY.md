# SETINA Slowdown App - Coolify Deployment Guide

## 🚀 Деплой в Coolify

Этот проект готов для деплоя в Coolify с использованием Docker Compose.

### 📋 Предварительные требования

- Coolify сервер с Docker и Docker Compose
- Минимум 2GB RAM для backend обработки
- Доступ к интернету для установки зависимостей

### 🔧 Настройка проекта в Coolify

1. **Создание нового проекта**
   - Войдите в панель Coolify
   - Создайте новый проект
   - Выберите "Docker Compose" как тип деплоя

2. **Подключение репозитория**
   ```
   Repository URL: https://github.com/Castellord/Slowler.git
   Branch: main
   ```

3. **Конфигурация**
   - Используйте файл `docker-compose.yaml` как основу
   - Или используйте `coolify.yaml` для расширенной конфигурации

### 🏗️ Архитектура приложения

```
┌─────────────────┐    ┌──────────────────┐
│   Frontend      │    │    Backend       │
│   (React+Nginx) │◄──►│   (Python+Flask) │
│   Port: 80      │    │   Port: 5230     │
└─────────────────┘    └──────────────────┘
```

### 📦 Сервисы

#### Frontend
- **Технологии**: React, Nginx
- **Порт**: 80
- **Функции**: 
  - Статическая раздача React приложения
  - Проксирование API запросов к backend
  - Gzip сжатие
  - Кэширование статических ресурсов

#### Backend
- **Технологии**: Python, Flask, Rubber Band
- **Порт**: 5230
- **Функции**:
  - Обработка аудио файлов
  - API для замедления аудио
  - Поддержка WAV и MP3 форматов
  - Health check endpoint

### 🔍 Health Checks

Оба сервиса имеют настроенные health checks:

- **Frontend**: `GET /` (проверка доступности Nginx)
- **Backend**: `GET /health` (проверка работы Flask приложения)

### 🌐 Переменные окружения

#### Backend
```env
FLASK_ENV=production
PYTHONUNBUFFERED=1
```

#### Frontend (автоматически)
```env
NODE_ENV=production
```

### 📁 Структура проекта

```
├── Dockerfile              # Production frontend (React + Nginx)
├── nginx.conf              # Конфигурация Nginx
├── docker-compose.yaml     # Основная конфигурация
├── coolify.yaml           # Расширенная конфигурация для Coolify
├── backend/
│   ├── Dockerfile         # Backend (Python + Flask)
│   ├── app.py            # Основное приложение
│   └── requirements.txt   # Python зависимости
└── src/                   # React исходники
```

### 🚀 Процесс деплоя

1. **Сборка образов**
   ```bash
   # Frontend: Multi-stage build (Node.js → Nginx)
   # Backend: Python + системные зависимости
   ```

2. **Запуск сервисов**
   ```bash
   # Backend запускается первым
   # Frontend ждет готовности backend
   ```

3. **Проверка работоспособности**
   ```bash
   # Health checks каждые 30 секунд
   # Автоматический перезапуск при сбоях
   ```

### 🔧 Настройки Nginx

- **Gzip сжатие** для всех текстовых файлов
- **Кэширование** статических ресурсов на 1 год
- **Проксирование** `/api/*` запросов к backend
- **SPA поддержка** - все маршруты ведут к `index.html`
- **Безопасность** - заголовки защиты

### 📊 Мониторинг

#### Логи
```bash
# Просмотр логов frontend
docker logs slowdown-frontend

# Просмотр логов backend
docker logs slowdown-backend
```

#### Метрики
- Health check статус в Coolify dashboard
- Использование ресурсов
- Время отклика

### 🛠️ Устранение неполадок

#### Проблемы с сборкой
```bash
# Очистка Docker кэша
docker system prune -a

# Пересборка без кэша
docker-compose build --no-cache
```

#### Проблема с package-lock.json
Если возникает ошибка `npm ci` с package-lock.json:
- Используется `npm install` вместо `npm ci`
- package-lock.json исключен из .dockerignore
- Альтернативно можно использовать `Dockerfile.production`

#### Проблемы с backend
```bash
# Проверка health endpoint
curl http://localhost:5230/health

# Проверка логов Python
docker logs slowdown-backend -f
```

#### Проблемы с frontend
```bash
# Проверка Nginx конфигурации
docker exec slowdown-frontend nginx -t

# Проверка статических файлов
docker exec slowdown-frontend ls -la /usr/share/nginx/html
```

### 🔄 Обновления

1. **Автоматические обновления**
   - Coolify может отслеживать изменения в Git
   - Автоматическая пересборка при push

2. **Ручные обновления**
   ```bash
   # В Coolify dashboard
   # Нажать "Redeploy" для пересборки
   ```

### 📈 Производительность

#### Рекомендуемые ресурсы
- **CPU**: 2+ cores
- **RAM**: 2GB+ (для обработки больших аудио файлов)
- **Диск**: 10GB+ (для временных файлов)

#### Оптимизации
- Multi-stage Docker build для минимального размера образов
- Nginx кэширование и сжатие
- Python оптимизации для аудио обработки

### 🔐 Безопасность

- Контейнеры запускаются без root привилегий где возможно
- Nginx настроен с безопасными заголовками
- Нет открытых портов кроме необходимых
- Временные файлы автоматически очищаются

### 📞 Поддержка

При возникновении проблем:
1. Проверьте логи сервисов
2. Убедитесь в доступности health endpoints
3. Проверьте ресурсы сервера
4. Обратитесь к документации Coolify

---

**Готово к деплою!** 🎉

Просто подключите репозиторий к Coolify и запустите деплой.
