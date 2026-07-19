"""Tests for Sprint ability: movement bonus, modifier, and duration."""


def test_sprint_moves_further_than_normal():
    """Sprint's get_movement proposes positions beyond normal speed range."""
    from engine import Engine, RuleBasedAgent
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class
    from planner import get_plausible_movements

    g = Grid(10, 10)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=42)
    S76 = get_hero_class("Soldier76")
    Axe = get_hero_class("Axe")
    s = S76(engine=e, pos=Point(0, 5), team=0)
    a = Axe(engine=e, pos=Point(9, 5), team=1)
    e.finalize_setup()

    moves = get_plausible_movements(s, e)
    # Find the Sprint move (non-stay)
    sprint_moves = [pos for pos, reason in moves.items()
                    if "Sprint" in reason and pos != s.pos]
    assert len(sprint_moves) > 0, "Sprint should propose a move"
    sprint_pos = sprint_moves[0]
    dist = s.pos.get_distance(sprint_pos)
    # Sprint should move further than the hero's base speed (3)
    assert dist > 3, f"Sprint should move >3, got {dist}"
    assert dist <= 6, f"Sprint should move ≤6, got {dist}"


def test_sprint_buff_increases_speed():
    """SprintBuff modifier adds +3 to QuerySpeed."""
    from engine import Engine
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class
    from queries import QuerySpeed
    from backend.src.heroes.soldier76 import SprintBuff

    g = Grid(10, 10)
    e = Engine(grid=g, agents={}, seed=42)
    S76 = get_hero_class("Soldier76")
    s = S76(engine=e, pos=Point(0, 5), team=0)
    e.finalize_setup()

    base_speed = QuerySpeed(s).resolve(e).value
    assert base_speed <= 4, f"Base speed should be ~3, got {base_speed}"

    # Apply SprintBuff
    buff = SprintBuff()
    s.add_modifier(e, buff)
    buffed_speed = QuerySpeed(s).resolve(e).value
    assert buffed_speed == base_speed + 3, (
        f"SprintBuff should add 3 speed: {base_speed} -> {buffed_speed}"
    )


def test_sprint_buff_clears_at_end_of_turn():
    """SprintBuff with ClearAtEndOfTurnMixin is removed on TurnEndEvent."""
    from engine import Engine
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class
    from backend.src.heroes.soldier76 import SprintBuff
    from event_library import TurnEndEvent

    g = Grid(10, 10)
    e = Engine(grid=g, agents={}, seed=42)
    S76 = get_hero_class("Soldier76")
    s = S76(engine=e, pos=Point(0, 5), team=0)
    e.finalize_setup()

    buff = SprintBuff()
    s.add_modifier(e, buff)
    assert buff in s.modifiers, "Buff should be present after add"

    # Process TurnEndEvent through all phases (BEFORE -> RESOLVE -> AFTER -> DONE)
    e.event_queue.enqueue(TurnEndEvent(subject=s))
    while e.event_queue._queue:
        e.event_queue.process_one(engine=e)

    assert buff not in s.modifiers, "Buff should be removed at end of turn"
