# Builder stage: install dependencies into a relocatable prefix.
FROM python:3.12-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --prefix=/install -r requirements.txt

# Runtime stage: minimal image with non-root user.
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Non-root user
RUN useradd -m appuser

# App files and dependencies
COPY --from=builder /install /usr/local
COPY . .

# Entry script: migrations + collectstatic + start server
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Writable dirs
RUN mkdir -p /app/staticfiles /app/media && chown -R appuser:appuser /app

USER appuser
EXPOSE 8000

# Default to dev; compose overrides to prod
ENV DJANGO_SETTINGS_MODULE=sitepro.settings.dev

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["/bin/sh","-c","gunicorn sitepro.wsgi:application \
  --bind=0.0.0.0:8000 \
  --workers=${GUNICORN_WORKERS:-6} \
  --max-requests=1000 \
  --max-requests-jitter=100 \
  --timeout=30 \
  --graceful-timeout=30 \
  --access-logfile - \
  --error-logfile - \
  --log-level info"]