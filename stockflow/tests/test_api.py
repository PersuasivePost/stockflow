def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_homepage_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "StockFlow" in res.text


def test_create_and_list_product(client, product):
    res = client.get("/api/products")
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["sku"] == "MSE-01"
    assert items[0]["low_stock"] is False


def test_duplicate_sku_rejected(client, product):
    res = client.post("/api/products", json={"name": "Another", "sku": "MSE-01"})
    assert res.status_code == 409


def test_negative_quantity_rejected(client):
    res = client.post("/api/products", json={"name": "Bad", "sku": "BAD-1", "quantity": -3})
    assert res.status_code == 422


def test_update_product(client, product):
    res = client.put(f"/api/products/{product['id']}", json={"price": 599})
    assert res.status_code == 200
    assert res.json()["price"] == 599
    assert res.json()["name"] == "Wireless Mouse"  # untouched fields stay the same


def test_delete_product(client, product):
    assert client.delete(f"/api/products/{product['id']}").status_code == 204
    assert client.get(f"/api/products/{product['id']}").status_code == 404


def test_stock_in_and_out(client, product):
    pid = product["id"]
    res = client.post(f"/api/products/{pid}/stock", json={"change": 15, "reason": "shipment"})
    assert res.json()["quantity"] == 25
    res = client.post(f"/api/products/{pid}/stock", json={"change": -20, "reason": "sold"})
    assert res.json()["quantity"] == 5
    movements = client.get(f"/api/products/{pid}/movements").json()
    assert [m["change"] for m in movements] == [-20, 15]


def test_cannot_sell_more_than_in_stock(client, product):
    res = client.post(f"/api/products/{product['id']}/stock", json={"change": -50})
    assert res.status_code == 400
    assert client.get(f"/api/products/{product['id']}").json()["quantity"] == 10


def test_low_stock_and_stats(client, product):
    client.post(f"/api/products/{product['id']}/stock", json={"change": -7})  # 3 left, min is 5
    low = client.get("/api/products/low-stock").json()
    assert [p["sku"] for p in low] == ["MSE-01"]

    stats = client.get("/api/stats").json()
    assert stats == {"total_products": 1, "total_units": 3, "total_value": 1947.0, "low_stock_count": 1}
