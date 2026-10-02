from concurrent import futures
import time
import grpc
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Імпортуємо згенеровані gRPC файли
import protos.warehouse_pb2 as pb2
import protos.warehouse_pb2_grpc as pb2_grpc

# Підключення до бази даних
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:secretpassword@localhost:5432/orders_db"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class WarehouseServicer(pb2_grpc.WarehouseServicer):
    
    def CheckStock(self, request, context):
        db = SessionLocal()
        try:
            # Вибираємо всі колонки, щоб автоматично знайти поле кількості
            query = "SELECT * FROM products WHERE id = :product_id"
            result = db.execute(text(query), {"product_id": request.product_id}).fetchone()
            
            if not result:
                return pb2.StockResponse(
                    is_available=False, 
                    current_stock=0,
                    warehouse_location="Одеса, Головний склад"
                )
            
            row_dict = dict(result._mapping)
            stock_keys = ['quantity', 'stock', 'amount', 'count', 'qty', 'inventory']
            stock = 0
            for key in stock_keys:
                if key in row_dict:
                    stock = row_dict[key] or 0
                    break
            
            return pb2.StockResponse(
                is_available=(stock > 0), 
                current_stock=int(stock),
                warehouse_location="Одеса, Головний склад"
            )
        finally:
            db.close()

    def ReserveStock(self, request, context):
        db = SessionLocal()
        try:
            query = "SELECT * FROM products WHERE id = :product_id"
            result = db.execute(text(query), {"product_id": request.product_id}).fetchone()
            
            if not result:
                return pb2.ReserveResponse(success=False, message="Product not found")
            
            row_dict = dict(result._mapping)
            stock_keys = ['quantity', 'stock', 'amount', 'count', 'qty', 'inventory']
            stock_col = None
            stock_val = 0
            for key in stock_keys:
                if key in row_dict:
                    stock_col = key
                    stock_val = row_dict[key] or 0
                    break
            
            if stock_col is None or stock_val < request.quantity:
                return pb2.ReserveResponse(success=False, message="Not enough stock or stock column not found")
            
            update_query = f"UPDATE products SET {stock_col} = {stock_col} - :qty WHERE id = :product_id"
            db.execute(text(update_query), {"qty": request.quantity, "product_id": request.product_id})
            db.commit()
            
            return pb2.ReserveResponse(success=True, message="Stock reserved successfully")
        except Exception as e:
            db.rollback()
            return pb2.ReserveResponse(success=False, message=str(e))
        finally:
            db.close()

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb2_grpc.add_WarehouseServicer_to_server(WarehouseServicer(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("Warehouse gRPC Service is running on port 50051...")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()