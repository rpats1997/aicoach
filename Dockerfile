# ---------- Stage 1: build the Expo (React Native Web) app ----------
FROM node:20-bookworm AS webbuild

WORKDIR /app/mobile
COPY mobile/package.json mobile/package-lock.json ./
RUN npm ci
COPY mobile/ ./
ENV EXPO_PUBLIC_API_URL=""
ENV CI=1
RUN npx expo export --platform web --output-dir dist

# ---------- Stage 2: runtime image (Postgres + FastAPI + Nginx) ----------
FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        postgresql \
        nginx \
        supervisor \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Expose stable, version-independent paths to the installed PostgreSQL binaries.
RUN set -eux; \
    PG_BIN="$(find /usr/lib/postgresql -maxdepth 2 -type d -name bin | head -n1)"; \
    ln -s "$PG_BIN/postgres" /usr/local/bin/pg-postgres; \
    ln -s "$PG_BIN/initdb" /usr/local/bin/pg-initdb; \
    ln -s "$PG_BIN/pg_ctl" /usr/local/bin/pg-pg_ctl; \
    ln -s "$PG_BIN/psql" /usr/local/bin/pg-psql; \
    ln -s "$PG_BIN/createdb" /usr/local/bin/pg-createdb

# Backend
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./

# Web build output, served by nginx
COPY --from=webbuild /app/mobile/dist /usr/share/nginx/html

# Service configuration
COPY docker/nginx.conf /etc/nginx/sites-enabled/default
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV DATABASE_URL=postgresql+psycopg2://coachai:coachai@localhost:5432/coachai
ENV JWT_SECRET=change-me-in-production
ENV PYTHONUNBUFFERED=1

VOLUME ["/var/lib/postgresql/data"]
EXPOSE 80

ENTRYPOINT ["/entrypoint.sh"]
