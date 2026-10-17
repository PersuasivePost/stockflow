import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture()
def client():
    # Fresh schema for every test, against whatever DATABASE_URL points to
    # (SQLite locally, a throwaway Postgres container in CI).
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def product(client):
    res = client.post(
        "/api/products",
        json={"name": "Wireless Mouse", "sku": "MSE-01", "category": "Peripherals",
              "quantity": 10, "min_stock": 5, "price": 649},
    )
    assert res.status_code == 201
    return res.json()
