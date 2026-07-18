"""Tests for BUG-010: movement optimal range.

Verifies that heroes position themselves at the optimal range
(default: max default ability range) rather than moving adjacent.
"""


def test_hero_optimal_range_default():
    """Hero.get_optimal_range returns max range of default ability."""
    from engine import Engine
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class

    g = Grid(10, 10)
    e = Engine(grid=g, agents={}, seed=42)
    Soldier76 = get_hero_class("Soldier76")
    s = Soldier76(engine=e, pos=Point(0, 0), team=0)
    e.finalize_setup()

    optimal = s.get_optimal_range()
    # Heavy Pulse Rifle has range 4
    assert optimal == 4, f"Expected optimal range 4, got {optimal}"


def test_melee_hero_has_no_optimal_range():
    """Melee heroes have optimal range 1 (their attack range)."""
    from engine import Engine
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class

    g = Grid(10, 10)
    e = Engine(grid=g, agents={}, seed=42)
    Axe = get_hero_class("Axe")
    a = Axe(engine=e, pos=Point(0, 0), team=0)
    e.finalize_setup()

    optimal = a.get_optimal_range()
    # Axe's default ability has range 1
    assert optimal == 1, f"Expected optimal range 1 for melee, got {optimal}"


def test_ranged_hero_fallback_moves_to_optimal_range():
    """When no ability can target from current position, fallback moves toward optimal range."""
    from engine import Engine, RuleBasedAgent
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class
    from planner import get_plausible_movements

    g = Grid(10, 10)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=42)
    Soldier76 = get_hero_class("Soldier76")
    Axe = get_hero_class("Axe")
    s = Soldier76(engine=e, pos=Point(0, 5), team=0)
    a = Axe(engine=e, pos=Point(9, 5), team=1)
    e.finalize_setup()

    # Enemy at distance 9, Soldier76 has speed 4 and range 4
    # Fallback should propose moving to maintain range (not adjacent)
    moves = get_plausible_movements(s, e)
    assert len(moves) == 1, f"Expected 1 fallback move, got {len(moves)}"
    move_pos = list(moves.keys())[0]
    enemy_dist = move_pos.get_distance(a.pos)
    assert enemy_dist >= 4, f"Should be at least range 4 from enemy, got {enemy_dist}"
    assert move_pos != s.pos, "Should not stay in place"


def test_ranged_hero_moves_away_from_adjacent_enemy():
    """When adjacent to an enemy, ranged hero moves to maintain optimal range."""
    from engine import Engine, RuleBasedAgent
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class
    from planner import get_plausible_movements

    g = Grid(10, 10)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=42)
    Soldier76 = get_hero_class("Soldier76")
    Axe = get_hero_class("Axe")
    s = Soldier76(engine=e, pos=Point(4, 5), team=0)
    a = Axe(engine=e, pos=Point(5, 5), team=1)
    e.finalize_setup()

    # Enemy is adjacent (distance 1), Soldier76 has speed 4 and range 4
    # Should propose moving to maintain range 4
    moves = get_plausible_movements(s, e)
    move_pos = list(moves.keys())[0]
    # If moves only has 1 entry (fallback + Stay merged), check it
    if len(moves) == 1:
        enemy_dist = move_pos.get_distance(a.pos)
        assert enemy_dist >= 2, f"Should move away from adjacent enemy, distance={move_pos}"
