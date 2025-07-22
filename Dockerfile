# Multi-stage build для production
FROM node:18-alpine as build

WORKDIR /app

# Копируем package files
COPY package*.json ./
RUN npm ci --only=production

# Копируем исходный код и собираем
COPY . .
RUN npm run build

# Production stage с nginx
FROM nginx:alpine

# Копируем собранное приложение
COPY --from=build /app/build /usr/share/nginx/html

# Копируем конфигурацию nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
