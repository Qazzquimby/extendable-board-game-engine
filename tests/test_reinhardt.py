"""Tests for Reinhardt hero — charge, shield, and barrier."""

import pytest
from engine import Engine, RuleBasedAgent
from grid import Grid
from point import Point
from hero_registry import get_hero_class


def test_reinhardt_in_hero_list():
    """Reinhardt is registered and discoverable."""
    heroes = get_hero_class.list_heroes() if hasattr(get_hero_class, 'list_heroes') else []
    # Check via API
    from fastapi.testclient import TestClient
    from backend.main import app
    client = TestClient(app)
    resp = client.get("/heroes")
    assert resp.status_code == 200
    names = [h.lower() for h in resp.json()]
    assert "reinhardt" in names


@pytest.fixture
def rein_axe_game():
    """Create a 5x5 game with Reinhardt vs Axe."""
    g = Grid(5, 5)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=7)
    Rein = get_hero_class("Reinhardt")
    Axe = get_hero_class("Axe")
    r = Rein(engine=e, pos=Point(0, 2), team=0)
    a = Axe(engine=e, pos=Point(4, 2), team=1)
    e.finalize_setup()
    return e, r, a


def test_reinhardt_has_charge(rein_axe_game):
    """Reinhardt has Charge ability."""
    e, r, a = rein_axe_game
    charge = next((ab for ab in r.abilities if ab.name == "Charge"), None)
    assert charge is not None, "Reinhardt should have Charge"
    assert charge.action_cost.name == "MOVE_AND_STANDARD"
    assert charge.max_charges == 1


def test_reinhardt_has_shield_marker(rein_axe_game):
    """Reinhardt starts with a shield marker on the edge."""
    e, r, a = rein_axe_game
    assert len(e.markers) >= 1, "Reinhardt should have at least one marker (shield)"
    shield_marker = next((m for m in e.markers if "Barrier" in m.name), None)
    assert shield_marker is not None, "Shield marker should exist"
    assert shield_marker.pos.x == 0, "Shield should be on left edge (team 0)"
    assert shield_marker.pos.y == 2, "Shield should be at Reinhardt's Y position"


def test_reinhardt_charge_pushes_all_enemies():
    """Charge pushes all enemies along the path to the end."""
    g = Grid(6, 6)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=7)
    Rein = get_hero_class("Reinhardt")
    Axe = get_hero_class("Axe")
    r = Rein(engine=e, pos=Point(0, 2), team=0)
    a1 = Axe(engine=e, pos=Point(3, 2), team=1)  # First enemy
    a2 = Axe(engine=e, pos=Point(5, 2), team=1)  # Second enemy (farther)
    e.finalize_setup()

    # Manually make Reinhardt charge right
    charge = next(ab for ab in r.abilities if ab.name == "Charge")
    aimings = charge.aiming.get_all_aimings(e, r, require_los=False)
    # Find the one that goes right along y=2
    right_aim = None
    for aim in aimings:
        if any(p.y == 2 and p.x > 0 for p in aim.included_points):
            right_aim = aim
            break
    assert right_aim is not None, "Should find a rightward charge"

    # Execute charge
    from events import AbilityUseEvent
    ev = AbilityUseEvent(source=r, ability=charge, aiming_result=right_aim)
    ev.process(e)  # BEFORE phase
    ev.process(e)  # RESOLVE phase
    ev.process(e)  # AFTER phase

    # Both enemies should have moved (nearest pushed farthest forward)
    assert a1.pos is not None and a1.pos != Point(3, 2), "Axe1 should have been pushed from (3,2)"
    assert a1.pos == Point(4, 2), f"Axe1 should be pushed to (4,2), got {a1.pos}"
    assert a2.pos is not None and a2.pos == Point(5, 2), f"Axe2 stays at end: {a2.pos}"


def test_shield_blocks_enemy_los():
    """Shield marker blocks LOS for enemy team."""
    g = Grid(6, 6)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=7)
    Rein = get_hero_class("Reinhardt")
    Axe = get_hero_class("Axe")
    r = Rein(engine=e, pos=Point(0, 2), team=0)
    a = Axe(engine=e, pos=Point(5, 2), team=1)
    e.finalize_setup()

    # Check LOS from Axe to a point behind the shield
    from aimings import get_blocked_points
    blocked = get_blocked_points(e, a)
    # The shield at (0,2) should be in blocked points
    assert Point(0, 2) in blocked, (
        f"Shield position should block LOS, blocked points: {blocked}"
    )
