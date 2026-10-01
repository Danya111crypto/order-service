import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Читаємо рядок підключення зі змінної оточення DATABASE_URL або використовуємо локальний дефолт
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:secretpassword@localhost:5432/orders_db"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()