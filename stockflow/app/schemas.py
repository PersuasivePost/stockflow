from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sku: str = Field(min_length=1, max_length=40)
    category: str = Field(default="General", max_length=60)
    quantity: int = Field(default=0, ge=0)
    min_stock: int = Field(default=5, ge=0)
    price: float = Field(default=0, ge=0)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    sku: str | None = Field(default=None, min_length=1, max_length=40)
    category: str | None = Field(default=None, max_length=60)
    quantity: int | None = Field(default=None, ge=0)
    min_stock: int | None = Field(default=None, ge=0)
    price: float | None = Field(default=None, ge=0)


class ProductOut(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    low_stock: bool = False


class StockChange(BaseModel):
    change: int = Field(description="Positive for stock in, negative for stock out")
    reason: str = Field(default="", max_length=120)


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    change: int
    reason: str
    created_at: datetime


class Stats(BaseModel):
    total_products: int
    total_units: int
    total_value: float
    low_stock_count: int
