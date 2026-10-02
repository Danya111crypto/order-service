import os
import json
import grpc
from fastapi import FastAPI, Header, HTTPException, Query, Response, status
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Імпортуємо згенеровані gRPC файли для клієнта
import protos.warehouse_pb2 as pb2
import protos.warehouse_pb2_grpc as pb2_grpc

app = FastAPI(title="Order Service with gRPC Warehouse")

# Підключення до БД (тільки через змінні оточення)
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:secretpassword@localhost:5432/orders_db"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# === БЛОК СТВОРЕННЯ ТАБЛИЦЬ ТА ДОДАВАННЯ ТОВАРУ ===
with engine.begin() as connection:
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name VARCHAR NOT NULL,
            price FLOAT NOT NULL,
            stock INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            product_id INTEGER REFERENCES products(id),
            quantity INTEGER NOT NULL,
            status VARCHAR DEFAULT 'Created',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        DROP TABLE IF EXISTS idempotency_keys CASCADE;
        CREATE TABLE idempotency_keys (
            id SERIAL PRIMARY KEY,
            idempotency_key VARCHAR(255) UNIQUE NOT NULL,
            response_body TEXT,
            status_code INT
        );
        
        -- Додаємо або оновлюємо тестовий товар з ID = 1, щоб він завжди був у наявності
        INSERT INTO products (id, name, price, stock) 
        VALUES (1, 'Тестовий товар', 100.0, 10)
        ON CONFLICT (id) DO UPDATE SET stock = 10;
    """))

# Налаштування gRPC-клієнта до сервісу складу
WAREHOUSE_HOST = os.getenv("WAREHOUSE_HOST", "localhost:50051")


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "order-service"}


@app.post("/orders", status_code=status.HTTP_201_CREATED)
def create_order(
    product_id: int = Query(..., description="ID товару"),
    quantity: int = Query(..., gt=0, description="Кількість товару (більше 0)"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key")
):
    db = SessionLocal()
    try:
        # 1. Перевірка ідемпотентності (якщо ключ передано)
        if idempotency_key:
            existing_key = db.execute(
                text("SELECT response_body, status_code FROM idempotency_keys WHERE idempotency_key = :key"),
                {"key": idempotency_key}
            ).fetchone()
            
            if existing_key:
                # Повертаємо збережену відповідь попереднього успішного запиту
                return Response(content=existing_key[0], status_code=existing_key[1], media_type="application/json")

        # 2. Звернення до Сервісу Складу через gRPC із тайм-аутом (deadline = 2 секунди)
        try:
            with grpc.insecure_channel(WAREHOUSE_HOST) as channel:
                stub = pb2_grpc.WarehouseStub(channel)
                
                # Викликаємо метод перевірки залишку з тайм-аутом 2 секунди
                stock_response = stub.CheckStock(
                    pb2.StockRequest(product_id=product_id), 
                    timeout=2.0
                )
                
                if not stock_response.is_available or stock_response.current_stock < quantity:
                    raise HTTPException(status_code=400, detail="Product is out of stock or insufficient quantity")
                
                # Викликаємо метод резервування товару через gRPC
                reserve_response = stub.ReserveStock(
                    pb2.ReserveRequest(product_id=product_id, quantity=quantity),
                    timeout=2.0
                )
                
                if not reserve_response.success:
                    raise HTTPException(status_code=400, detail=reserve_response.message)
                    
        except grpc.RpcError as e:
            # Якщо склад недоступний або спрацював тайм-аут
            if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED or e.code() == grpc.StatusCode.UNAVAILABLE:
                raise HTTPException(
                    status_code=503, 
                    detail="Warehouse service is unavailable or timed out"
                )
            raise HTTPException(status_code=500, detail=f"gRPC error: {e.details()}")

        # 3. Створення замовлення в базі даних Order Service
        insert_order_query = """
            INSERT INTO orders (product_id, quantity, status) 
            VALUES (:product_id, :quantity, 'Created') 
            RETURNING id, product_id, quantity, status
        """
        new_order = db.execute(
            text(insert_order_query), 
            {"product_id": product_id, "quantity": quantity}
        ).fetchone()
        db.commit()

        response_data = {
            "order_id": new_order[0],
            "product_id": new_order[1],
            "quantity": new_order[2],
            "status": new_order[3]
        }

        # 4. Зберігаємо результат для ідемпотентності
        if idempotency_key:
            db.execute(
                text("INSERT INTO idempotency_keys (idempotency_key, response_body, status_code) VALUES (:key, :body, :code)"),
                {"key": idempotency_key, "body": json.dumps(response_data), "code": 201}
            )
            db.commit()

        return response_data

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

# === НОВІ МАРШРУТИ ДЛЯ ОТРИМАННЯ ТА СКАСУВАННЯ ЗАМОВЛЕННЯ ===

@app.get("/orders/{order_id}")
def get_order(order_id: int):
    db = SessionLocal()
    try:
        order = db.execute(
            text("SELECT id, product_id, quantity, status FROM orders WHERE id = :id"),
            {"id": order_id}
        ).fetchone()
        
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
            
        return {
            "order_id": order[0],
            "product_id": order[1],
            "quantity": order[2],
            "status": order[3]
        }
    finally:
        db.close()

@app.post("/orders/{order_id}/cancel")
def cancel_order(order_id: int):
    db = SessionLocal()
    try:
        order = db.execute(
            text("SELECT id, status FROM orders WHERE id = :id"),
            {"id": order_id}
        ).fetchone()
        
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
            
        db.execute(
            text("UPDATE orders SET status = 'Canceled' WHERE id = :id"),
            {"id": order_id}
        )
        db.commit()
        
        return {"message": f"Order {order_id} has been canceled successfully", "status": "Canceled"}
    finally:
        db.close()