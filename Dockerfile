# Simple Dockerfile for Coolify deployment
FROM node:18-alpine as build

WORKDIR /app

# Копируем package.json
COPY package.json ./

# Устанавливаем зависимости
RUN npm install

# Копируем исходный код
COPY src ./src
COPY public ./public

# Собираем приложение
RUN npm run build

# Production stage с nginx
FROM nginx:alpine

# Устанавливаем curl для health checks
RUN apk add --no-cache curl

# Копируем собранное приложение
COPY --from=build /app/build /usr/share/nginx/html

# Копируем конфигурацию nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
