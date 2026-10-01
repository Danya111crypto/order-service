from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text
from datetime import datetime
from database import Base

class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    stock = Column(Integer, nullable=False)

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, default="Created")  # Created / Cancelled
    created_at = Column(DateTime, default=datetime.utcnow)

class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    
    key = Column(String, primary_key=True, index=True)
    response_body = Column(Text, nullable=False)
    status_code = Column(Integer, nullable=False)