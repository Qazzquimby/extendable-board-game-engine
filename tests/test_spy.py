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
    assert len(data["logs"]) > 1


def test_spy_has_decoy_entities():
    """Spy starts with 2 decoy entities."""
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

    decoys = [ent for ent in e.entities if ent.name == "SpyDecoy"]
    assert len(decoys) == 2, f"Spy should have 2 decoys, got {len(decoys)}"
    for d in decoys:
        assert d.pos is not None, "Decoy should have a position"
        assert d.hp == 1, f"Decoy should have 1 HP, got {d.hp}"
        assert d.pos != Point(0, 2), "Decoy should be at a different position than Spy"
        assert d.team == 0, "Decoy should be on Spy's team"


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
    from aimings import TargetEntity
    assert isinstance(revolver.aiming, TargetEntity), "Revolver should use TargetEntity"


def test_spy_revolver_targets_enemies_and_decoys():
    """Spy's Revolver targets enemy heroes and decoy entities."""
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

    revolver = next(ab for ab in s.abilities if ab.name == "Revolver")
    # Check target condition includes both enemies and decoys
    from aimings import TargetEntity
    assert isinstance(revolver.aiming, TargetEntity)
    cond = revolver.aiming.condition
    # Condition should accept SpyDecoyEntity even though same team
    decoys = [ent for ent in e.entities if ent.name == "SpyDecoy"]
    assert len(decoys) > 0
    for d in decoys:
        assert cond(e, s, d.pos), f"Condition should accept decoy at {d.pos}"
    # Condition should accept enemy hero
    assert cond(e, s, a.pos), "Condition should accept enemy hero"

    # Aimings from range should find both enemies and decoys
    aimings = revolver.aiming.get_all_aimings(e, s, start_pos=Point(2, 2), require_los=False)
    targeted_names = set()
    for aim in aimings:
        for pt in aim.target_points:
            ent = e.entity_at(pt)
            if ent:
                targeted_names.add(ent.name)
    assert "Axe" in targeted_names, "Should target enemy hero"
    assert "SpyDecoy" in targeted_names, "Should target decoy entities"
