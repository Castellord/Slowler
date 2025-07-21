#!/bin/bash

echo "🔧 Установка зависимостей для SETINA Slowdown App"
echo "=================================================="

# Проверяем операционную систему
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "🍎 Обнаружена macOS"
    
    # Проверяем наличие Homebrew
    if ! command -v brew &> /dev/null; then
        echo "❌ Homebrew не найден. Устанавливаем Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    
    echo "📦 Устанавливаем libsndfile через Homebrew..."
    brew install libsndfile
    
    echo "📦 Устанавливаем ffmpeg для поддержки MP3..."
    brew install ffmpeg
    
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "🐧 Обнаружена Linux"
    
    # Определяем дистрибутив
    if command -v apt-get &> /dev/null; then
        echo "📦 Устанавливаем libsndfile через apt..."
        sudo apt-get update
        sudo apt-get install -y libsndfile1-dev ffmpeg
    elif command -v yum &> /dev/null; then
        echo "📦 Устанавливаем libsndfile через yum..."
        sudo yum install -y libsndfile-devel ffmpeg
    elif command -v pacman &> /dev/null; then
        echo "📦 Устанавливаем libsndfile через pacman..."
        sudo pacman -S libsndfile ffmpeg
    else
        echo "❌ Неподдерживаемый дистрибутив Linux"
        exit 1
    fi
    
else
    echo "❌ Неподдерживаемая операционная система: $OSTYPE"
    exit 1
fi

echo ""
echo "🐍 Устанавливаем Python зависимости..."
pip install -r requirements.txt

echo ""
echo "✅ Установка завершена!"
echo ""
echo "🚀 Теперь можно запустить сервер:"
echo "   python3 app.py"
echo ""
echo "📚 Доступные алгоритмы:"
echo "   1. Rubber Band (лучший для сохранения качества)"
echo "   2. Librosa Phase Vocoder (fallback)"
echo "   3. Простая интерполяция (последний fallback)"
