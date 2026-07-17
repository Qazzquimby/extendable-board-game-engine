"""Tests for the game-runner API.

Tests the FastAPI endpoint at the seam boundary — send a request, check the response.
"""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_heroes_endpoint_returns_list():
    """GET /heroes returns a list of available hero class names."""
    response = client.get("/heroes")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    # Core heroes we expect to see
    assert "Axe" in data
    assert "Necrophos" in data


def test_run_game_with_valid_config():
    """POST /run-game with a valid team config returns a GameLog with logs."""
    response = client.post(
        "/run-game",
        json={
            "seed": 42,
            "grid_size": 5,
            "teams": [
                {
                    "heroes": [
                        {"class": "Axe", "pos": [0, 0]},
                        {"class": "Necrophos", "pos": [0, 1]},
                    ]
                },
                {
                    "heroes": [
                        {"class": "MeleeHero", "pos": [4, 3]},
                        {"class": "MeleeHero", "pos": [4, 4]},
                    ]
                },
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "winner_team" in data
    assert "logs" in data
    assert len(data["logs"]) > 1


def test_run_game_invalid_hero_class():
    """POST /run-game with an unknown hero class returns 400."""
    response = client.post(
        "/run-game",
        json={
            "seed": 42,
            "grid_size": 5,
            "teams": [
                {
                    "heroes": [
                        {"class": "NonExistentHero", "pos": [0, 0]},
                    ]
                },
                {
                    "heroes": [
                        {"class": "Axe", "pos": [4, 4]},
                    ]
                },
            ],
        },
    )
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data


def test_run_game_overlapping_positions():
    """POST /run-game with overlapping positions on the same team returns 400."""
    response = client.post(
        "/run-game",
        json={
            "seed": 42,
            "grid_size": 5,
            "teams": [
                {
                    "heroes": [
                        {"class": "Axe", "pos": [0, 0]},
                        {"class": "Necrophos", "pos": [0, 0]},  # Same pos
                    ]
                },
                {
                    "heroes": [
                        {"class": "MeleeHero", "pos": [4, 4]},
                    ]
                },
            ],
        },
    )
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data


def test_run_game_cross_team_overlap():
    """POST /run-game with overlapping positions across teams returns 400."""
    response = client.post(
        "/run-game",
        json={
            "seed": 42,
            "grid_size": 5,
            "teams": [
                {
                    "heroes": [
                        {"class": "Axe", "pos": [2, 2]},
                    ]
                },
                {
                    "heroes": [
                        {"class": "Necrophos", "pos": [2, 2]},  # Same pos, different team
                    ]
                },
            ],
        },
    )
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data


def test_run_game_deterministic_seed():
    """Same seed + same config should produce identical game logs."""
    config = {
        "seed": 42,
        "grid_size": 5,
        "teams": [
            {
                "heroes": [
                    {"class": "Axe", "pos": [0, 0]},
                    {"class": "Necrophos", "pos": [0, 1]},
                ]
            },
            {
                "heroes": [
                    {"class": "MeleeHero", "pos": [4, 3]},
                    {"class": "Viktoria", "pos": [4, 4]},
                ]
            },
        ],
    }
    response1 = client.post("/run-game", json=config)
    response2 = client.post("/run-game", json=config)
    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.json() == response2.json()
