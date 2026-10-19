# Development image for the RAGIMS backend (see deploy/docker-compose.yml).
# Dependencies are baked in at build time; the app source is bind-mounted in
# development for hot reload, and copied in for standalone/CI builds.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source is bind-mounted in development; copied here for standalone builds.
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
