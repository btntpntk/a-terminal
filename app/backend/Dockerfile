FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies via Poetry
COPY pyproject.toml poetry.lock ./
RUN pip install --no-cache-dir "poetry==1.8.*" \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction --without dev

# Copy source code
COPY src/ ./src/
COPY app/backend/ ./app/backend/

WORKDIR /app/app/backend

EXPOSE 8080

# Cloud Run injects $PORT; fall back to 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
