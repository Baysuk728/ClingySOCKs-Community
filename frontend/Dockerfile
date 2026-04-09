# Build stage
FROM node:20-alpine AS build

WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm install

# Copy all files and build the app
COPY . .

# Build arg for API URL (Vite inlines env vars at build time)
ARG VITE_MEMORY_API_URL
ENV VITE_MEMORY_API_URL=$VITE_MEMORY_API_URL

# Cache-bust: ARG changes invalidate this layer, forcing a fresh build
ARG CACHEBUST=1
RUN npm run build

# Production stage
FROM nginx:stable-alpine

# Copy build output to nginx public folder
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx config for SPA client-side routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Create entrypoint script that injects VITE_MEMORY_API_URL at runtime
RUN printf '#!/bin/sh\n\
URL="${VITE_MEMORY_API_URL:-}"\n\
if [ -n "$URL" ]; then\n\
  sed -i "s|RUNTIME_API_URL_PLACEHOLDER|$URL|g" /etc/nginx/conf.d/default.conf\n\
fi\n\
exec nginx -g "daemon off;"\n' > /docker-entrypoint-runtime.sh && chmod +x /docker-entrypoint-runtime.sh

EXPOSE 80

CMD ["/docker-entrypoint-runtime.sh"]
