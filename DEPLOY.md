# 🚀 Deployment Instructions - SETINA Slowdown App

## Варианты деплоя

### 1. 🐳 Coolify (Рекомендуется)

#### Быстрый старт
1. Откройте Coolify dashboard
2. Создайте новый проект
3. Выберите "Docker Compose"
4. Подключите репозиторий: `https://github.com/Castellord/Slowler.git`
5. Используйте `docker-compose.yaml` как конфигурацию
6. Нажмите "Deploy"

#### Подробная инструкция
См. [README_COOLIFY.md](./README_COOLIFY.md)

---

### 2. 🖥️ Локальный Docker

#### Тестирование перед деплоем
```bash
# Запуск тестового скрипта
./test-docker.sh
```

#### Ручной запуск
```bash
# Сборка и запуск
docker-compose up -d

# Проверка статуса
docker-compose ps

# Просмотр логов
docker-compose logs -f

# Остановка
docker-compose down
```

---

### 3. 🖥️ Electron Desktop App

#### Запуск полного приложения
```bash
# Запуск с backend и frontend
./start-electron-app.sh
```

#### Только Electron (после сборки)
```bash
npm run build
npm run electron
```

---

## 🔧 Конфигурация

### Переменные окружения

#### Production (Docker)
```env
FLASK_ENV=production
PYTHONUNBUFFERED=1
NODE_ENV=production
```

#### Development
```env
FLASK_ENV=development
NODE_ENV=development
```

### Порты
- **Frontend**: 80 (production) / 3000 (development)
- **Backend**: 5230
- **Health Check**: `/health`

---

## 📊 Мониторинг

### Health Checks
```bash
# Backend
curl http://localhost:5230/health

# Frontend
curl http://localhost:80/
```

### Логи
```bash
# Docker
docker-compose logs -f

# Отдельные сервисы
docker-compose logs frontend
docker-compose logs backend
```

---

## 🛠️ Устранение неполадок

### Проблемы с Docker
```bash
# Очистка и пересборка
docker-compose down --rmi all --volumes
docker-compose build --no-cache
docker-compose up -d
```

### Проблемы с backend
```bash
# Проверка Python зависимостей
docker-compose exec backend pip list

# Проверка аудио библиотек
docker-compose exec backend python -c "import pyrubberband; print('OK')"
```

### Проблемы с frontend
```bash
# Проверка сборки React
docker-compose exec frontend ls -la /usr/share/nginx/html

# Проверка Nginx
docker-compose exec frontend nginx -t
```

---

## 📈 Производительность

### Рекомендуемые ресурсы
- **CPU**: 2+ cores
- **RAM**: 2GB+ (для больших аудио файлов)
- **Диск**: 10GB+ (временные файлы)

### Оптимизации
- Multi-stage Docker builds
- Nginx кэширование и сжатие
- Автоматическая очистка временных файлов

---

## 🔐 Безопасность

### Docker
- Контейнеры без root привилегий
- Минимальные образы (Alpine Linux)
- Безопасные заголовки Nginx

### Сеть
- Внутренняя сеть Docker
- Только необходимые порты открыты
- HTTPS через Traefik (в Coolify)

---

## 📋 Чек-лист деплоя

### Перед деплоем
- [ ] Протестировать локально: `./test-docker.sh`
- [ ] Проверить health endpoints
- [ ] Убедиться в работе аудио обработки
- [ ] Проверить размеры Docker образов

### После деплоя
- [ ] Проверить доступность приложения
- [ ] Тестировать загрузку и обработку файлов
- [ ] Проверить логи на ошибки
- [ ] Настроить мониторинг

---

## 🆘 Поддержка

### Контакты
- GitHub Issues: [Slowler Issues](https://github.com/Castellord/Slowler/issues)
- Документация: [README.md](./README.md)

### Полезные ссылки
- [Coolify Documentation](https://coolify.io/docs)
- [Docker Compose Reference](https://docs.docker.com/compose/)
- [Nginx Configuration](https://nginx.org/en/docs/)

---

**Готово к деплою в Coolify!** 🎉
