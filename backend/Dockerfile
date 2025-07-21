FROM python:3.10-slim

WORKDIR /app

# Копируем всё из backend/
COPY . .  

RUN apt-get update && \
    apt-get install -y ffmpeg libsndfile1 && \
    pip install --upgrade pip && \
    pip install -r requirements.txt

CMD ["python", "app.py"]
