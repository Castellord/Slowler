# SETINA Slowdown App - Coolify Deployment Guide

## 🚀 Деплой в Coolify с Traefik

Этот проект готов для деплоя в Coolify с использованием встроенного Traefik вместо nginx.

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
   - Используйте файл `coolify.yaml` для деплоя
   - Traefik автоматически настроит SSL и маршрутизацию

### 🏗️ Архитектура с Traefik

```
Internet → Coolify Traefik → Frontend (serve static files)
                         → Backend (Python Flask + SocketIO)
```

### 📦 Сервисы

#### Frontend
- **Технологии**: React, Node.js serve
- **Порт**: 80
- **Функции**: 
  - Статическая раздача React приложения через serve
  - SPA поддержка с fallback на index.html
  - Автоматическое кэширование через Traefik

#### Backend
- **Технологии**: Python, Flask, Rubber Band, Gunicorn + Eventlet
- **Порт**: 5230
- **Функции**:
  - Обработка аудио файлов
  - API для замедления аудио
  - WebSocket поддержка через Socket.IO
  - Поддержка WAV и MP3 форматов

### 🌐 Traefik Маршрутизация

#### Backend API Routes
```yaml
# API endpoints направляются на backend:5230
- /process     → backend (обработка файлов)
- /health      → backend (health check)
- /progress/*  → backend (прогресс обработки)
- /cancel/*    → backend (отмена обработки)
- /socket.io/* → backend (WebSocket соединения)
```

#### Frontend Routes
```yaml
# Все остальные запросы направляются на frontend:80
- /*           → frontend (статические файлы и SPA)
```

### 🔍 Health Checks

Оба сервиса имеют настроенные health checks:

- **Frontend**: `wget http://localhost:80/` (проверка serve)
- **Backend**: `curl http://localhost:5230/health` (проверка Flask)

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
├── Dockerfile.production   # Production frontend (React + serve)
├── coolify.yaml           # Конфигурация Traefik для Coolify
├── docker-compose.yaml    # Локальная разработка
├── backend/
│   ├── Dockerfile         # Backend (Python + Flask)
│   ├── app.py            # Основное приложение
│   ├── gunicorn.conf.py  # Конфигурация Gunicorn + Eventlet
│   └── requirements.txt   # Python зависимости
└── src/                   # React исходники
```

### 🚀 Процесс деплоя

1. **Сборка образов**
   ```bash
   # Frontend: Multi-stage build (Node.js build → serve)
   # Backend: Python + системные зависимости + Eventlet
   ```

2. **Traefik конфигурация**
   ```bash
   # Автоматическая настройка SSL через Let's Encrypt
   # Маршрутизация по правилам в labels
   # Балансировка нагрузки
   ```

3. **Запуск сервисов**
   ```bash
   # Backend запускается с Eventlet worker
   # Frontend запускается с serve
   # Traefik автоматически обнаруживает сервисы
   ```

### 🔧 Преимущества Traefik

#### Автоматизация
- **SSL сертификаты** - автоматическое получение и обновление
- **Service Discovery** - автоматическое обнаружение сервисов
- **Load Balancing** - встроенная балансировка нагрузки

#### Производительность
- **HTTP/2 поддержка** - автоматически включена
- **Compression** - встроенное сжатие
- **Caching** - интеллектуальное кэширование

#### Безопасность
- **HTTPS Redirect** - автоматическое перенаправление
- **Security Headers** - автоматические заголовки безопасности
- **Rate Limiting** - встроенная защита от DDoS

### 📊 Мониторинг

#### Логи
```bash
# Просмотр логов frontend
docker logs slowdown-frontend

# Просмотр логов backend
docker logs slowdown-backend

# Логи Traefik (в Coolify dashboard)
```

#### Traefik Dashboard
- Доступен через Coolify interface
- Показывает все маршруты и сервисы
- Метрики производительности

### 🛠️ Устранение неполадок

#### Проблемы с маршрутизацией
```bash
# Проверка Traefik labels
docker inspect slowdown-frontend
docker inspect slowdown-backend

# Проверка правил маршрутизации в Coolify dashboard
```

#### Проблемы с SSL
- Traefik автоматически получает SSL сертификаты
- Проверьте домен в переменной FQDN
- Убедитесь что домен указывает на сервер

#### WebSocket проблемы
```bash
# Проверка WebSocket соединения
# Traefik автоматически обрабатывает upgrade запросы
# Eventlet worker поддерживает WebSocket нативно
```

### 🔄 Обновления

1. **Автоматические обновления**
   - Coolify отслеживает изменения в Git
   - Автоматическая пересборка при push
   - Zero-downtime deployment через Traefik

2. **Ручные обновления**
   ```bash
   # В Coolify dashboard
   # Нажать "Redeploy" для пересборки
   # Traefik автоматически переключит трафик
   ```

### 📈 Производительность

#### Рекомендуемые ресурсы
- **CPU**: 2+ cores
- **RAM**: 2GB+ (для обработки больших аудио файлов)
- **Диск**: 10GB+ (для временных файлов)

#### Оптимизации Traefik
- Автоматическое HTTP/2
- Встроенное сжатие
- Интеллектуальное кэширование статических файлов
- Connection pooling для backend

### 🔐 Безопасность

#### Traefik Security
- Автоматические HTTPS сертификаты
- Security headers из коробки
- Rate limiting и DDoS защита
- Secure defaults для всех соединений

#### Application Security
- Контейнеры без root привилегий
- Изолированная сеть между сервисами
- Автоматическая очистка временных файлов
- Валидация входных данных

### 🌟 Новые возможности с Traefik

#### Large File Uploads
- Автоматическая обработка больших файлов (до 500MB)
- Streaming uploads без буферизации
- Timeout настройки для длительных операций

#### WebSocket Support
- Нативная поддержка WebSocket через Eventlet
- Автоматический upgrade HTTP → WebSocket
- Real-time прогресс обработки

#### Cancellation Support
- Отмена обработки при закрытии вкладки
- Graceful shutdown длительных операций
- Автоматическая очистка ресурсов

### 📞 Поддержка

При возникновении проблем:
1. Проверьте Traefik dashboard в Coolify
2. Убедитесь в правильности FQDN переменной
3. Проверьте логи сервисов
4. Убедитесь в доступности health endpoints

### 🎯 Миграция с nginx

Если у вас уже есть версия с nginx:
1. Удалите nginx.conf (больше не нужен)
2. Используйте Dockerfile.production вместо Dockerfile
3. Обновите coolify.yaml с новыми Traefik labels
4. Переразверните приложение

---

**Готово к деплою с Traefik!** 🎉

Traefik обеспечивает более простую настройку, автоматический SSL и лучшую производительность из коробки.
