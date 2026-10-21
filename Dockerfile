# ---------------------------------------------------
# Stage 1: Builder (Збірка та встановлення залежностей)
# ---------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

# Встановлюємо системні залежності для збірки (якщо потрібні)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Копіюємо файл залежностей та збираємо wheels
COPY order_service/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---------------------------------------------------
# Stage 2: Final (Мінімальний робочий образ)
# ---------------------------------------------------
FROM python:3.11-slim AS runner

WORKDIR /app

# Створюємо непривілейованого користувача для безпеки
RUN adduser --disabled-password --gecos "" appuser

# Копіюємо тільки встановлені пакеті з етапу builder
COPY --from=builder /root/.local /home/appuser/.local
COPY order_service /app/order_service

# Налаштовуємо оточення
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/order_service

USER appuser

# Дефолтна команда (може бути перевизначена)
CMD ["python", "order_service/main.py"]