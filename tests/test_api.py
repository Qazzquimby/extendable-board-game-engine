"""Tests for the game-runner API.

Tests the FastAPI endpoint at the seam boundary — send a request, check the response.
"""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_action_logs_contain_hierarchical_messages():
    """Log entries should contain action_logs with ability names and damage messages."""
    response = client.post(
        "/run-game",
        json={
            "seed": 42,
            "grid_size": 6,
            "teams": [
                {
                    "heroes": [
                        {"class": "Axe", "pos": [0, 0]},
                    ]
                },
                {
                    "heroes": [
                        {"class": "MeleeHero", "pos": [5, 0]},
                    ]
                },
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    logs = data["logs"]

    # At least one entry should have action_logs
    entries_with_logs = [e for e in logs if e.get("action_logs")]
    assert len(entries_with_logs) > 0, "No entries have action_logs"

    # Collect all log messages
    all_messages = set()
    for entry in logs:
        for msg in entry.get("action_logs", []):
            all_messages.add(msg)

    # Should contain ability usage messages
    ability_msgs = [m for m in all_messages if "used" in m]
    assert len(ability_msgs) > 0, f"No ability usage messages found in {all_messages}"

    # Should contain damage messages ("dealt X damage to Y")
    damage_msgs = [m for m in all_messages if "dealt" in m and "damage" in m]
    assert len(damage_msgs) > 0, f"No damage messages found in {all_messages}"

    # Should contain death or death-related messages
    death_msgs = [m for m in all_messages if "died" in m.lower()]
    # Death may not occur in every game, so this is not required

    print(f"Entries with logs: {len(entries_with_logs)}")
    print(f"Unique messages: {len(all_messages)}")
    print(f"Ability messages: {ability_msgs}")
    print(f"Damage messages: {damage_msgs}")


def test_log_entries_contain_event_types():
    """Log entries should contain move, ability_use, and damage event types."""
    response = client.post(
        "/run-game",
        json={
            "seed": 42,
            "grid_size": 6,
            "teams": [
                {
                    "heroes": [
                        {"class": "Axe", "pos": [0, 0]},
                        {"class": "Viktoria", "pos": [0, 1]},
                    ]
                },
                {
                    "heroes": [
                        {"class": "MeleeHero", "pos": [5, 0]},
                    ]
                },
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    logs = data["logs"]

    # Collect all event types across all entries
    all_types = set()
    for entry in logs:
        for ev in entry.get("events", []):
            all_types.add(ev["type"])

    # Should have move events (entities walk around)
    assert "move" in all_types, f"No move events in {all_types}"
    # Should have ability_use events (heroes use abilities)
    assert "ability_use" in all_types, f"No ability_use events in {all_types}"
    # Should have damage events (combat)
    assert "damage" in all_types, f"No damage events in {all_types}"

    # Verify move events have correct source/target positions
    for entry in logs:
        for ev in entry.get("events", []):
            if ev["type"] == "move":
                assert ev.get("source_pos") is not None, f"Move event missing source_pos: {ev}"
                assert ev.get("target_pos") is not None, f"Move event missing target_pos: {ev}"
                break
        else:
            continue
        break

    # Verify ability_use events have ability_name
    for entry in logs:
        for ev in entry.get("events", []):
            if ev["type"] == "ability_use":
                assert ev.get("ability_name") is not None, f"AbilityUseEvent missing ability_name: {ev}"
                break
        else:
            continue
        break


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
