FROM python:3.10-slim

WORKDIR /app

# Копируем всё из backend/
COPY . .  

RUN apt-get update && \
    apt-get install -y ffmpeg libsndfile1 rubberband-cli curl && \
    pip install --upgrade pip && \
    pip install -r requirements.txt && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
