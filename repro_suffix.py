from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.db.models import Stock
import pytest

client = TestClient(app)

def test_get_stock_detail_with_ns_suffix_case_insensitive():
    db = SessionLocal()
    try:
        # Seed data
        stock = Stock(symbol="RELIANCE", name="Reliance Industries Ltd", sector="Energy")
        db.merge(stock)
        db.commit()

        # Searching with .NS suffix (case-insensitive) should work
        for suffix in [".NS", ".ns", ".Ns"]:
            response = client.get(f"/api/stocks/RELIANCE{suffix}")
            print(f"Testing RELIANCE{suffix}: {response.status_code}")
            assert response.status_code == 200
            data = response.json()
            assert data["symbol"] == "RELIANCE"
    finally:
        db.close()

if __name__ == "__main__":
    test_get_stock_detail_with_ns_suffix_case_insensitive()
