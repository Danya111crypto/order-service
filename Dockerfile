# Stage 1: Builder (Збірка залежностей у venv)
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY order_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final (Мінімальний робочий образ)
FROM python:3.11-slim AS runner

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser

# Копіюємо ізольоване віртуальне оточення з builder
COPY --from=builder /opt/venv /opt/venv
COPY order_service /app/order_service

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/order_service

USER appuser
WORKDIR /app/order_service

CMD ["python", "main.py"]