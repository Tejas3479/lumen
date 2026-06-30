# Stage 1: Build the static files
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: Serve using Nginx
FROM nginx:1.25-alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# Custom nginx config to handle React SPA routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
