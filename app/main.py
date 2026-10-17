import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine, get_db
from app.models import Product, StockMovement
from app.schemas import (
    MovementOut,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    Stats,
    StockChange,
)

APP_VERSION = os.getenv("APP_VERSION", "dev")  # baked into the image by CI (git commit SHA)
STATIC_DIR = Path(__file__).parent / "static"

SAMPLE_PRODUCTS = [
    dict(name="USB-C Cable 1m", sku="CBL-USBC-1M", category="Accessories", quantity=120, min_stock=20, price=199),
    dict(name="Wireless Mouse", sku="MSE-WL-01", category="Peripherals", quantity=8, min_stock=10, price=649),
    dict(name="Mechanical Keyboard", sku="KBD-MECH-87", category="Peripherals", quantity=25, min_stock=5, price=3499),
    dict(name="27\" Monitor", sku="MON-27-IPS", category="Displays", quantity=3, min_stock=4, price=15999),
    dict(name="Laptop Stand", sku="STD-ALU-01", category="Accessories", quantity=40, min_stock=10, price=1299),
]


def seed_if_empty() -> None:
    with SessionLocal() as db:
        if db.scalar(select(func.count(Product.id))) == 0:
            db.add_all(Product(**p) for p in SAMPLE_PRODUCTS)
            db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if os.getenv("SEED_DATA", "false").lower() == "true":
        seed_if_empty()
    yield


app = FastAPI(title="StockFlow Inventory API", version=APP_VERSION, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def to_out(p: Product) -> ProductOut:
    out = ProductOut.model_validate(p)
    out.price = float(p.price)
    out.low_stock = p.quantity < p.min_stock
    return out


def get_product_or_404(product_id: int, db: Session) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


# ---------- Health ----------
@app.get("/health", tags=["ops"])
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))  # fails (500) if the database is unreachable
    return {"status": "ok", "version": APP_VERSION}


# ---------- Frontend ----------
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


# ---------- Products ----------
@app.get("/api/products", response_model=list[ProductOut], tags=["products"])
def list_products(db: Session = Depends(get_db)):
    products = db.scalars(select(Product).order_by(Product.id)).all()
    return [to_out(p) for p in products]


@app.get("/api/products/low-stock", response_model=list[ProductOut], tags=["products"])
def low_stock(db: Session = Depends(get_db)):
    products = db.scalars(
        select(Product).where(Product.quantity < Product.min_stock).order_by(Product.quantity)
    ).all()
    return [to_out(p) for p in products]


@app.post("/api/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED, tags=["products"])
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    product = Product(**payload.model_dump())
    db.add(product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"SKU '{payload.sku}' already exists")
    db.refresh(product)
    return to_out(product)


@app.get("/api/products/{product_id}", response_model=ProductOut, tags=["products"])
def get_product(product_id: int, db: Session = Depends(get_db)):
    return to_out(get_product_or_404(product_id, db))


@app.put("/api/products/{product_id}", response_model=ProductOut, tags=["products"])
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)):
    product = get_product_or_404(product_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="SKU already exists")
    db.refresh(product)
    return to_out(product)


@app.delete("/api/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["products"])
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = get_product_or_404(product_id, db)
    db.delete(product)
    db.commit()


# ---------- Stock movements ----------
@app.post("/api/products/{product_id}/stock", response_model=ProductOut, tags=["stock"])
def change_stock(product_id: int, payload: StockChange, db: Session = Depends(get_db)):
    if payload.change == 0:
        raise HTTPException(status_code=400, detail="Change must not be zero")
    product = get_product_or_404(product_id, db)
    new_qty = product.quantity + payload.change
    if new_qty < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient stock: only {product.quantity} units of {product.sku} available",
        )
    product.quantity = new_qty
    db.add(StockMovement(product_id=product.id, change=payload.change, reason=payload.reason))
    db.commit()
    db.refresh(product)
    return to_out(product)


@app.get("/api/products/{product_id}/movements", response_model=list[MovementOut], tags=["stock"])
def list_movements(product_id: int, db: Session = Depends(get_db)):
    get_product_or_404(product_id, db)
    return db.scalars(
        select(StockMovement)
        .where(StockMovement.product_id == product_id)
        .order_by(StockMovement.id.desc())
    ).all()


# ---------- Dashboard ----------
@app.get("/api/stats", response_model=Stats, tags=["dashboard"])
def stats(db: Session = Depends(get_db)):
    products = db.scalars(select(Product)).all()
    return Stats(
        total_products=len(products),
        total_units=sum(p.quantity for p in products),
        total_value=round(sum(p.quantity * float(p.price) for p in products), 2),
        low_stock_count=sum(1 for p in products if p.quantity < p.min_stock),
    )
