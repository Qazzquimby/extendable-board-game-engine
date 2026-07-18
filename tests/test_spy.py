"""Tests for Spy hero — invisibility decoys, revolver, knife."""

from fastapi.testclient import TestClient
from backend.main import app


client = TestClient(app)


def test_spy_in_hero_list():
    """Spy is registered and discoverable."""
    resp = client.get("/heroes")
    assert resp.status_code == 200
    names = [h.lower() for h in resp.json()]
    assert "spy" in names


def test_spy_created_via_api():
    """A minimal game with Spy starts without error."""
    resp = client.post("/run-game", json={
        "seed": 42,
        "grid_size": 6,
        "teams": [
            {"heroes": [{"class": "Spy", "pos": [0, 0]}]},
            {"heroes": [{"class": "Axe", "pos": [5, 0]}]},
        ],
    })
    assert resp.status_code == 200
    data = resp.json()
    # Game should complete (will have a winner or draw)
    assert len(data["logs"]) > 1


def test_spy_has_decoy_markers():
    """Spy starts with 2 decoy markers."""
    from engine import Engine, RuleBasedAgent
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class

    g = Grid(6, 6)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=42)
    Spy = get_hero_class("Spy")
    Axe = get_hero_class("Axe")
    s = Spy(engine=e, pos=Point(0, 2), team=0)
    a = Axe(engine=e, pos=Point(5, 2), team=1)
    e.finalize_setup()

    decoys = [m for m in e.markers if "Decoy" in m.name]
    assert len(decoys) == 2, f"Spy should have 2 decoys, got {len(decoys)}"
    for d in decoys:
        assert d.pos is not None, "Decoy should have a position"
        assert d.pos != Point(0, 2), "Decoy should be at a different position than Spy"


def test_spy_has_revolver():
    """Spy has Revolver ability."""
    from engine import Engine, RuleBasedAgent
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class

    g = Grid(6, 6)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=42)
    Spy = get_hero_class("Spy")
    s = Spy(engine=e, pos=Point(0, 2), team=0)
    e.finalize_setup()

    revolver = next((ab for ab in s.abilities if ab.name == "Revolver"), None)
    assert revolver is not None, "Spy should have Revolver"
    assert revolver.is_default, "Revolver should be default action"
    assert revolver.aiming is not None, "Revolver should have targeting"


def test_enemy_can_target_spy_decoys():
    """Enemies can target Spy decoy markers with their abilities."""
    from engine import Engine, RuleBasedAgent
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class
    from aimings import TargetEntity

    g = Grid(6, 6)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=42)
    Spy = get_hero_class("Spy")
    Axe = get_hero_class("Axe")
    s = Spy(engine=e, pos=Point(0, 2), team=0)
    a = Axe(engine=e, pos=Point(5, 2), team=1)
    e.finalize_setup()

    decoy_positions = {m.pos for m in e.markers if "Decoy" in m.name}
    assert len(decoy_positions) > 0, "Spy should have decoys"

    # Use Spy's own TargetSpyOrDecoys from an enemy's perspective
    # (simulate what an enemy hero would see)
    from heroes.spy import TargetSpyOrDecoys
    enemy_aiming = TargetSpyOrDecoys(in_range=6)
    aimings = enemy_aiming.get_all_aimings(e, actor=a, require_los=False)
    aimed_positions = {p for aim in aimings for p in aim.target_points}

    # Decoy markers should be targetable by enemies
    for dp in decoy_positions:
        assert dp in aimed_positions, (
            f"Decoy at {dp} should be targetable by enemy, positions: {aimed_positions}"
        )
