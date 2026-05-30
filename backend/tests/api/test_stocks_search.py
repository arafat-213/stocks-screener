from app.db.models import Stock


def test_search_stocks_empty(client):
    response = client.get("/api/stocks/search?q=")
    assert response.status_code == 200
    assert response.json() == []


def test_search_stocks_short(client):
    response = client.get("/api/stocks/search?q=R")
    assert response.status_code == 200
    assert response.json() == []


def test_search_stocks_basic(client, db):
    # Seed data
    db.add(Stock(symbol="RELIANCE", name="Reliance Industries Ltd", sector="Energy"))
    db.add(
        Stock(
            symbol="RELINFRA", name="Reliance Infrastructure", sector="Infrastructure"
        )
    )
    db.add(Stock(symbol="TCS", name="Tata Consultancy Services", sector="IT"))
    db.commit()

    # Exact symbol match should be first
    response = client.get("/api/stocks/search?q=RELIANCE")
    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 1
    assert results[0]["symbol"] == "RELIANCE"

    # Partial match
    response = client.get("/api/stocks/search?q=REL")
    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 2
    symbols = [r["symbol"] for r in results]
    assert "RELIANCE" in symbols
    assert "RELINFRA" in symbols


def test_search_stocks_with_ns_suffix(client, db):
    # Seed data
    db.add(Stock(symbol="RELIANCE", name="Reliance Industries Ltd", sector="Energy"))
    db.commit()

    # Searching with .NS suffix (case-insensitive) should work
    for suffix in [".NS", ".ns", ".Ns"]:
        response = client.get(f"/api/stocks/search?q=RELIANCE{suffix}")
        assert response.status_code == 200
        results = response.json()
        assert len(results) == 1
        assert results[0]["symbol"] == "RELIANCE"
