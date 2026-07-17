"""Tests for death handling and scoring (e02s05)."""

from backend.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_game_ends_with_winner():
    """Full game returns a winner_team."""
    resp = client.post("/run-game", json={
        "seed": 42, "grid_size": 6,
        "teams": [
            {"heroes": [{"class": "Axe", "pos": [0, 0]}]},
            {"heroes": [{"class": "MeleeHero", "pos": [5, 0]}]},
        ],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["winner_team"] is not None


def test_final_frame_done():
    """Last log entry has done=True."""
    resp = client.post("/run-game", json={
        "seed": 42, "grid_size": 6,
        "teams": [
            {"heroes": [{"class": "Axe", "pos": [0, 0]}]},
            {"heroes": [{"class": "MeleeHero", "pos": [5, 0]}]},
        ],
    })
    data = resp.json()
    assert data["logs"][-1]["done"] == True


def test_initial_frame_no_events():
    """First log entry is initial state with no events."""
    resp = client.post("/run-game", json={
        "seed": 42, "grid_size": 6,
        "teams": [
            {"heroes": [{"class": "Axe", "pos": [0, 0]}]},
            {"heroes": [{"class": "MeleeHero", "pos": [5, 0]}]},
        ],
    })
    data = resp.json()
    assert data["logs"][0]["events"] == []


def test_log_has_multiple_entries():
    """Game log contains multiple entries (not just initial+final)."""
    resp = client.post("/run-game", json={
        "seed": 42, "grid_size": 6,
        "teams": [
            {"heroes": [{"class": "Axe", "pos": [0, 0]}]},
            {"heroes": [{"class": "MeleeHero", "pos": [5, 0]}]},
        ],
    })
    data = resp.json()
    assert len(data["logs"]) > 2
