"""Tests for Symmetra hero — quick smoke tests."""

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_symmetra_in_hero_list():
    """Symmetra appears in the hero registry."""
    resp = client.get("/heroes")
    assert resp.status_code == 200
    names = [h.lower() for h in resp.json()]
    assert "symmetra" in names


def test_symmetra_created_via_api():
    """A minimal game with Symmetra starts without error."""
    resp = client.post("/run-game", json={
        "seed": 42,
        "grid_size": 6,
        "teams": [
            {"heroes": [{"class": "Symmetra", "pos": [0, 0]}]},
            {"heroes": [{"class": "Axe", "pos": [5, 0]}]},
        ],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["winner_team"] is not None
    assert len(data["logs"]) > 1
