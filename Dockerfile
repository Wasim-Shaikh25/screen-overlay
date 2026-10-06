# Production image for the self-hosted web app.
# Stage 1 builds the static site. Stage 2 serves it with nginx.
# The OpenAI API key is never part of this image and is never accepted by it.

FROM node:22-alpine AS build
WORKDIR /app
COPY web/package.json web/package-lock.json ./
COPY web/scripts ./scripts
RUN npm ci
COPY web/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -q -O - http://127.0.0.1:8080/healthz || exit 1
