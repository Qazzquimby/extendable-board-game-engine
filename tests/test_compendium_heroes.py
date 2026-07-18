"""Tests for new compendium heroes: Soldier 76, Zenyatta, Scout."""

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_soldier76_in_hero_list():
    resp = client.get("/heroes")
    assert resp.status_code == 200
    names = [h.lower() for h in resp.json()]
    assert "soldier76" in names


def test_zenyatta_in_hero_list():
    resp = client.get("/heroes")
    assert resp.status_code == 200
    names = [h.lower() for h in resp.json()]
    assert "zenyatta" in names


def test_scout_in_hero_list():
    resp = client.get("/heroes")
    assert resp.status_code == 200
    names = [h.lower() for h in resp.json()]
    assert "scout" in names


def test_soldier76_has_heavy_pulse_rifle():
    from engine import Engine, RuleBasedAgent
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class

    g = Grid(6, 6)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=7)
    Soldier76 = get_hero_class("Soldier76")
    Axe = get_hero_class("Axe")
    s = Soldier76(engine=e, pos=Point(0, 2), team=0)
    a = Axe(engine=e, pos=Point(4, 2), team=1)
    e.finalize_setup()

    rifle = next((ab for ab in s.abilities if ab.name == "Heavy Pulse Rifle"), None)
    assert rifle is not None
    assert rifle.is_default
    assert len(rifle.instructions) == 1


def test_scout_has_scattergun():
    from engine import Engine, RuleBasedAgent
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class

    g = Grid(6, 6)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=7)
    Scout = get_hero_class("Scout")
    Axe = get_hero_class("Axe")
    s = Scout(engine=e, pos=Point(0, 2), team=0)
    a = Axe(engine=e, pos=Point(1, 2), team=1)
    e.finalize_setup()

    scatter = next((ab for ab in s.abilities if ab.name == "Scattergun"), None)
    assert scatter is not None
    assert scatter.is_default


def test_zenyatta_has_orb_of_destruction():
    from engine import Engine, RuleBasedAgent
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class

    g = Grid(6, 6)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=7)
    Zenyatta = get_hero_class("Zenyatta")
    Axe = get_hero_class("Axe")
    z = Zenyatta(engine=e, pos=Point(0, 2), team=0)
    a = Axe(engine=e, pos=Point(4, 2), team=1)
    e.finalize_setup()

    orb = next((ab for ab in z.abilities if ab.name == "Orb of Destruction"), None)
    assert orb is not None
    assert orb.is_default
    assert len(orb.instructions) == 1


def test_soldier76_heals_with_biotic_field():
    from engine import Engine, RuleBasedAgent
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class

    g = Grid(6, 6)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=7)
    Soldier76 = get_hero_class("Soldier76")
    s = Soldier76(engine=e, pos=Point(0, 2), team=0)
    e.finalize_setup()

    field = next((ab for ab in s.abilities if ab.name == "Biotic Field"), None)
    assert field is not None
    assert any(
        "Heal" in type(inst).__name__ for inst in field.instructions
    ), "Biotic Field should have a heal instruction"


def test_zenyatta_has_transcendence_ultimate():
    from engine import Engine, RuleBasedAgent
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class

    g = Grid(6, 6)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=7)
    Zenyatta = get_hero_class("Zenyatta")
    z = Zenyatta(engine=e, pos=Point(0, 2), team=0)
    e.finalize_setup()

    ult = next((ab for ab in z.abilities if ab.name == "Transcendence"), None)
    assert ult is not None
    assert ult.is_ultimate
    assert ult.ultimate_turn == 3


def test_scout_has_bonk():
    from engine import Engine, RuleBasedAgent
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class

    g = Grid(6, 6)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=7)
    Scout = get_hero_class("Scout")
    s = Scout(engine=e, pos=Point(0, 2), team=0)
    e.finalize_setup()

    bonk = next((ab for ab in s.abilities if ab.name == "Bonk Atomic Punch"), None)
    assert bonk is not None
    assert bonk.taps  # 1/Game


def test_soldier76_game_runs():
    """A full game with Soldier 76 completes without error."""
    from engine import Engine, RuleBasedAgent
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class

    g = Grid(6, 6)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=7)
    Soldier76 = get_hero_class("Soldier76")
    Axe = get_hero_class("Axe")
    s = Soldier76(engine=e, pos=Point(0, 2), team=0)
    a = Axe(engine=e, pos=Point(5, 2), team=1)
    e.finalize_setup()
    log = e.run_game()
    assert log.winner_team is not None


def test_zenyatta_game_runs():
    from engine import Engine, RuleBasedAgent
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class

    g = Grid(6, 6)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=7)
    Zenyatta = get_hero_class("Zenyatta")
    Axe = get_hero_class("Axe")
    z = Zenyatta(engine=e, pos=Point(0, 2), team=0)
    a = Axe(engine=e, pos=Point(5, 2), team=1)
    e.finalize_setup()
    log = e.run_game()
    assert log.winner_team is not None


def test_scout_game_runs():
    from engine import Engine, RuleBasedAgent
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class

    g = Grid(6, 6)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=7)
    Scout = get_hero_class("Scout")
    Axe = get_hero_class("Axe")
    s = Scout(engine=e, pos=Point(0, 2), team=0)
    a = Axe(engine=e, pos=Point(5, 2), team=1)
    e.finalize_setup()
    log = e.run_game()
    assert log.winner_team is not None
