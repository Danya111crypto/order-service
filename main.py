import json
from fastapi import FastAPI, Depends, HTTPException, Header, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db, engine, Base
import models

# Автоматичне створення таблиць при старті (або можна використовувати SQL міграції)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Order Service API (Variant A)")

# 1. Healthcheck ендпоінт (перевірка доступності БД)
@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"error": "DatabaseUnavailable", "message": str(e)}
        )

# 2. Створення замовлення з ідемпотентністю через заголовок Idempotency-Key
@app.post("/orders", status_code=201)
def create_order(
    product_id: int, 
    quantity: int, 
    response: Response,
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db)
):
    # Перевірка ідемпотентності: якщо ключ вже використовувався, повертаємо збережену відповідь
    if idempotency_key:
        cached = db.query(models.IdempotencyKey).filter_by(key=idempotency_key).first()
        if cached:
            response.status_code = cached.status_code
            return json.loads(cached.response_body)

    # Валідація вхідних даних (статус 400)
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero")

    product = db.query(models.Product).filter_by(id=product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    if product.stock < quantity:
        raise HTTPException(status_code=409, detail="Not enough items in stock")

    # Бізнес-логіка: зменшення залишку на складі та створення замовлення
    product.stock -= quantity
    new_order = models.Order(product_id=product_id, quantity=quantity, status="Created")
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    result = {
        "order_id": new_order.id,
        "product_id": new_order.product_id,
        "quantity": new_order.quantity,
        "status": new_order.status
    }

    # Зберігаємо результат для забезпечення ідемпотентності
    if idempotency_key:
        idemp_record = models.IdempotencyKey(
            key=idempotency_key,
            response_body=json.dumps(result),
            status_code=201
        )
        db.add(idemp_record)
        db.commit()

    return result

# 3. Скасування замовлення (бізнес-операція)
@app.post("/orders/{order_id}/cancel")
def cancel_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter_by(id=order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.status == "Cancelled":
        raise HTTPException(status_code=409, detail="Order is already cancelled")

    # Повертаємо товар назад на склад
    product = db.query(models.Product).filter_by(id=order.product_id).first()
    if product:
        product.stock += order.quantity

    order.status = "Cancelled"
    db.commit()
    return {"message": f"Order {order_id} successfully cancelled"}

# 4. Перегляд замовлення (CRUD)
@app.get("/orders/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter_by(id=order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order