#!/bin/bash

# Test Docker Build Script for SETINA Slowdown App
# Этот скрипт тестирует Docker сборку локально перед деплоем в Coolify

echo "🐳 SETINA Slowdown App - Docker Test"
echo "===================================="

# Проверяем что Docker запущен
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker не запущен. Запустите Docker и попробуйте снова."
    exit 1
fi

# Проверяем что docker-compose доступен
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose не найден. Установите docker-compose."
    exit 1
fi

echo "✅ Docker и docker-compose готовы"

# Останавливаем существующие контейнеры
echo "🛑 Остановка существующих контейнеров..."
docker-compose down --remove-orphans

# Очищаем старые образы (опционально)
read -p "🗑️  Очистить старые образы? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🧹 Очистка старых образов..."
    docker-compose down --rmi all --volumes --remove-orphans
    docker system prune -f
fi

# Собираем образы
echo "🔨 Сборка Docker образов..."
docker-compose build --no-cache

if [ $? -ne 0 ]; then
    echo "❌ Ошибка сборки образов"
    exit 1
fi

echo "✅ Образы собраны успешно"

# Запускаем контейнеры
echo "🚀 Запуск контейнеров..."
docker-compose up -d

if [ $? -ne 0 ]; then
    echo "❌ Ошибка запуска контейнеров"
    exit 1
fi

echo "✅ Контейнеры запущены"

# Ждем запуска сервисов
echo "⏳ Ожидание запуска сервисов..."
sleep 10

# Проверяем health checks
echo "🔍 Проверка работоспособности сервисов..."

# Проверяем backend
echo "📡 Проверка backend (http://localhost:5230/health)..."
backend_status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5230/health)

if [ "$backend_status" = "200" ]; then
    echo "✅ Backend работает (HTTP $backend_status)"
else
    echo "❌ Backend не отвечает (HTTP $backend_status)"
    echo "📋 Логи backend:"
    docker-compose logs backend
fi

# Проверяем frontend
echo "🌐 Проверка frontend (http://localhost:80)..."
frontend_status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:80)

if [ "$frontend_status" = "200" ]; then
    echo "✅ Frontend работает (HTTP $frontend_status)"
else
    echo "❌ Frontend не отвечает (HTTP $frontend_status)"
    echo "📋 Логи frontend:"
    docker-compose logs frontend
fi

# Показываем статус контейнеров
echo ""
echo "📊 Статус контейнеров:"
docker-compose ps

# Показываем использование ресурсов
echo ""
echo "💾 Использование ресурсов:"
docker stats --no-stream

echo ""
echo "🎯 Тестирование завершено!"
echo ""
echo "📱 Доступные URL:"
echo "   Frontend: http://localhost:80"
echo "   Backend API: http://localhost:5230"
echo "   Health Check: http://localhost:5230/health"
echo ""
echo "📋 Полезные команды:"
echo "   Логи: docker-compose logs -f"
echo "   Остановка: docker-compose down"
echo "   Перезапуск: docker-compose restart"
echo ""

# Опционально открываем браузер
read -p "🌐 Открыть приложение в браузере? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if command -v open &> /dev/null; then
        open http://localhost:80
    elif command -v xdg-open &> /dev/null; then
        xdg-open http://localhost:80
    else
        echo "Откройте http://localhost:80 в браузере"
    fi
fi

echo "✅ Готово к деплою в Coolify!"
