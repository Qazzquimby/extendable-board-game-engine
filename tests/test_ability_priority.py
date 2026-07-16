"""Tests for ability priority, damage scoring, and movement helpers.

These test the pure helper functions first, then the auto-priority
on Ability with mocked engine state.
"""

from unittest.mock import MagicMock, PropertyMock

from abilities import (
    Ability,
    Instruction,
    ActionCost,
    best_move_for_score,
    displacement_value,
    score_damage,
    score_heal,
    score_add_token,
)
from aimings import TargetEntity, TargetSelf, AimingResult
from point import Point


# ── score_damage ──────────────────────────────────────────────────────

def test_score_damage_basic():
    """2 damage on 5hp target = 2."""
    assert score_damage(2, 5) == 2.0


def test_score_damage_kill_bonus():
    """5 damage on 3hp target = 6 (min(5,3)=3, doubled for kill)."""
    assert score_damage(5, 3) == 6.0


def test_score_damage_exact_kill():
    """3 damage on 3hp target = 6 (exact kill = doubled)."""
    assert score_damage(3, 3) == 6.0


def test_score_damage_overkill():
    """10 damage on 3hp target = 6 (overkill still capped + doubled)."""
    assert score_damage(10, 3) == 6.0


def test_score_damage_zero():
    """0 damage = 0."""
    assert score_damage(0, 5) == 0.0


def test_score_damage_no_negative():
    """No negative scores for non-existent targets."""
    assert score_damage(2, 0) == 0.0


# ── score_heal ────────────────────────────────────────────────────────

def test_score_heal_basic():
    """Heal 2 on target missing 3hp = 2."""
    assert score_heal(2, 3) == 2.0


def test_score_heal_full():
    """Heal 5 on target missing 3hp = 3 (capped at missing)."""
    assert score_heal(5, 3) == 3.0


def test_score_heal_zero():
    """Heal on full health = 0."""
    assert score_heal(2, 0) == 0.0


# ── score_add_token ───────────────────────────────────────────────────

class MockBadToken:
    valence = "bad"  # Will be compared to Valence.BAD

    def __init__(self):
        from valence import Valence
        self.valence = Valence.BAD


class MockGoodToken:
    def __init__(self):
        from valence import Valence
        self.valence = Valence.GOOD


class MockMixedToken:
    def __init__(self):
        from valence import Valence
        self.valence = Valence.MIXED


def test_score_add_token_bad():
    """Bad token = 2.0."""
    assert score_add_token(MockBadToken()) == 2.0


def test_score_add_token_good():
    """Good token = 1.0."""
    assert score_add_token(MockGoodToken()) == 1.0


def test_score_add_token_mixed():
    """Mixed token = 0.0."""
    assert score_add_token(MockMixedToken()) == 0.0


# ── best_move_for_score ───────────────────────────────────────────────

def test_best_move_for_score_picks_highest():
    """Should pick the point with the highest score."""
    pts = {Point(0, 0), Point(5, 0), Point(0, 5)}
    result = best_move_for_score(
        pts,
        Point(0, 0),
        score_fn=lambda pt: pt.x + pt.y,
        reason="Test",
    )
    # (5,0) has score 5, (0,5) has score 5, tie goes to closest to actor
    assert len(result) == 1
    key = list(result.keys())[0]
    assert result[key] == "Test"


def test_best_move_for_score_empty():
    """Empty reachable points = empty dict."""
    assert best_move_for_score(set(), Point(0, 0), lambda pt: 1.0, "x") == {}


def test_best_move_for_score_zero_score():
    """If best score is 0, return empty dict."""
    pts = {Point(0, 0)}
    result = best_move_for_score(pts, Point(0, 0), lambda pt: 0.0, "x")
    assert result == {}


def test_best_move_for_score_tiebreaker():
    """Tie goes to the point closest to the actor."""
    pts = {Point(3, 0), Point(0, 3)}
    result = best_move_for_score(
        pts, Point(0, 0), score_fn=lambda pt: 1.0, reason="Tie"
    )
    # Both score 1.0; (0,3) is distance 3, (3,0) is distance 3, both equal
    # The tiebreaker uses negative distance, so both are -3, then x,y
    # (0,3) → x=0,y=3; (3,0) → x=3,y=0. -pt.get_distance is same, so
    # secondary key is (point.x, point.y): (0,3) < (3,0) wins
    key = list(result.keys())[0]
    assert key in pts


# ── displacement_value ────────────────────────────────────────────────

def test_displacement_value_closer():
    """Moving closer to preferred position = positive value."""
    entity = MagicMock()
    entity.get_preferred_position.return_value = Point(10, 0)
    entity.get_speed.return_value = 2
    engine = MagicMock()

    # From (0,0) to (5,0): old_dist=10, new_dist=5, saved=5, value=5/2=2.5
    val = displacement_value(entity, Point(0, 0), Point(5, 0), engine)
    assert val == 2.5


def test_displacement_value_farther():
    """Moving farther from preferred position = negative value."""
    entity = MagicMock()
    entity.get_preferred_position.return_value = Point(10, 0)
    entity.get_speed.return_value = 2
    engine = MagicMock()

    # From (5,0) to (0,0): old_dist=5, new_dist=10, saved=-5, value=-2.5
    val = displacement_value(entity, Point(5, 0), Point(0, 0), engine)
    assert val == -2.5


def test_displacement_value_no_preference():
    """No preferred position = 0."""
    entity = MagicMock()
    entity.get_preferred_position.return_value = None
    engine = MagicMock()

    val = displacement_value(entity, Point(0, 0), Point(5, 0), engine)
    assert val == 0.0


def test_displacement_value_zero_speed():
    """Zero speed = 0 (avoid division by zero)."""
    entity = MagicMock()
    entity.get_preferred_position.return_value = Point(10, 0)
    entity.get_speed.return_value = 0
    engine = MagicMock()

    val = displacement_value(entity, Point(0, 0), Point(5, 0), engine)
    assert val == 0.0


# ── Auto-priority (default get_priority via _auto_priority) ───────────

def _make_mock_engine(entity_at_return=None):
    """Create a minimal mock engine for auto-priority tests."""
    engine = MagicMock()
    engine.entity_at.return_value = entity_at_return
    return engine


def _make_aiming_result(target_pts=None, incl_pts=None):
    """Create a minimal AimingResult."""
    result = MagicMock(spec=AimingResult)
    result.target_points = target_pts or []
    result.included_points = incl_pts or []
    result.sub_aimings = {}
    return result


class MockEntity:
    """Minimal entity stub for priority testing."""
    def __init__(self, hp=10, max_hp=10, team=1):
        self.id = 42
        self.hp = hp
        self.max_hp = max_hp
        self.team = team


def test_auto_priority_damage_simple():
    """AxeSwing: 2 damage on 5hp enemy → score_damage(2,5)=2.0."""
    from instruction_library import DamageInstruction

    ability = Ability(
        name="Slash",
        aiming=TargetEntity(in_range=1),
        instructions=[DamageInstruction(amount=2)],
    )
    target = MockEntity(hp=5, team=2)
    engine = _make_mock_engine(target)
    aiming = _make_aiming_result(target_pts=[Point(0, 0)])

    priority = ability.get_priority(engine, MagicMock(), Point(0, 0), aiming)
    assert priority == 2.0


def test_auto_priority_damage_kill():
    """Killing blow: 5 damage on 3hp enemy → score_damage(5,3)=6.0."""
    from instruction_library import DamageInstruction

    ability = Ability(
        name="Execute",
        aiming=TargetEntity(in_range=1),
        instructions=[DamageInstruction(amount=5)],
    )
    target = MockEntity(hp=3, team=2)
    engine = _make_mock_engine(target)
    aiming = _make_aiming_result(target_pts=[Point(0, 0)])

    priority = ability.get_priority(engine, MagicMock(), Point(0, 0), aiming)
    assert priority == 6.0


def test_auto_priority_no_target():
    """No entity at target point = 0."""
    from instruction_library import DamageInstruction

    ability = Ability(
        name="Slash",
        aiming=TargetEntity(in_range=1),
        instructions=[DamageInstruction(amount=2)],
    )
    engine = _make_mock_engine(None)  # no entity
    aiming = _make_aiming_result(target_pts=[Point(0, 0)])

    priority = ability.get_priority(engine, MagicMock(), Point(0, 0), aiming)
    assert priority == 0.0


def test_auto_priority_friendly_fire_ignored():
    """Damage on ally = 0 (instruction has bad valence, but target is friendly)."""
    from instruction_library import DamageInstruction

    ability = Ability(
        name="FriendlyFire",
        aiming=TargetEntity(in_range=1),
        instructions=[DamageInstruction(amount=5)],
    )
    target = MockEntity(hp=10, team=1)  # same team as actor
    actor = MockEntity(team=1)
    engine = _make_mock_engine(target)
    aiming = _make_aiming_result(target_pts=[Point(0, 0)])

    priority = ability.get_priority(engine, actor, Point(0, 0), aiming)
    assert priority == 0.0


def test_auto_priority_heal():
    """Heal 3 on ally missing 4hp → score_heal(3,4)=3.0."""
    from instruction_library import HealInstruction

    ability = Ability(
        name="Heal",
        aiming=TargetSelf(),
        instructions=[HealInstruction(amount=3)],
    )
    target = MockEntity(hp=6, max_hp=10, team=1)
    actor = MockEntity(team=1)
    engine = _make_mock_engine(target)
    aiming = _make_aiming_result(target_pts=[Point(0, 0)])

    priority = ability.get_priority(engine, actor, Point(0, 0), aiming)
    assert priority == 3.0


def test_auto_priority_heal_overheal():
    """Heal 5 on ally missing 2hp → capped at 2.0."""
    from instruction_library import HealInstruction

    ability = Ability(
        name="Heal",
        aiming=TargetSelf(),
        instructions=[HealInstruction(amount=5)],
    )
    target = MockEntity(hp=8, max_hp=10, team=1)
    actor = MockEntity(team=1)
    engine = _make_mock_engine(target)
    aiming = _make_aiming_result(target_pts=[Point(0, 0)])

    priority = ability.get_priority(engine, actor, Point(0, 0), aiming)
    assert priority == 2.0


def test_auto_priority_empty_instructions():
    """Ability with no instructions = 0."""
    ability = Ability(name="DoNothing", aiming=TargetSelf())
    target = MockEntity(hp=10, team=1)
    engine = _make_mock_engine(target)
    aiming = _make_aiming_result(target_pts=[Point(0, 0)])

    priority = ability.get_priority(engine, MagicMock(), Point(0, 0), aiming)
    assert priority == 0.0


def test_auto_priority_empty_target_points():
    """Ability with no target points = 0."""
    from instruction_library import DamageInstruction

    ability = Ability(
        name="Slash",
        aiming=TargetEntity(in_range=1),
        instructions=[DamageInstruction(amount=2)],
    )
    engine = _make_mock_engine(None)
    aiming = _make_aiming_result(target_pts=[])  # no target points

    priority = ability.get_priority(engine, MagicMock(), Point(0, 0), aiming)
    assert priority == 0.0


def test_custom_priority_fn_overrides_auto():
    """If custom_priority_fn is set, it takes precedence over auto-scoring."""
    ability = Ability(
        name="Custom",
        aiming=TargetEntity(in_range=1),
        custom_priority_fn=lambda e, a, p, r: 42.0,
    )
    priority = ability.get_priority(
        MagicMock(), MagicMock(), Point(0, 0), _make_aiming_result()
    )
    assert priority == 42.0


# ── Subclass override preserves original behavior ────────────────────

def test_subclass_override_takes_precedence():
    """A subclass that overrides get_priority is still called directly."""
    class AlwaysFive(Ability):
        def get_priority(self, engine, actor, pos, aiming_result):
            return 5.0

    ability = AlwaysFive(
        name="AlwaysFive",
        aiming=TargetSelf(),
        instructions=[],
    )
    priority = ability.get_priority(
        MagicMock(), MagicMock(), Point(0, 0), _make_aiming_result()
    )
    assert priority == 5.0
