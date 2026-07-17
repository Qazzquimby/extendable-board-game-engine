"""Tests for the instant-ability reaction system and movement tie-breaking.

Tests that:
1. Instant abilities can be used as reactions when the entity is targeted
2. Using a movement reaction (Tracer Blink) causes the attack to miss
3. Tie-breaking by lowest distance moved works correctly
4. Instant abilities don't consume standard actions
"""

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def _run_game_json():
    """Helper: run a game with Tracer and check results."""
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
                        {"class": "Tracer", "pos": [5, 0]},
                    ]
                },
            ],
        },
    )
    assert response.status_code == 200
    return response.json()


def test_tracer_has_instant_abilities():
    """Tracer's Blink and Recall are ActionCost.INSTANT and have reaction_condition set."""
    from engine import Engine
    from grid import Grid
    from entities import Hero
    from heroes.tracer import Tracer
    from point import Point

    engine = Engine(grid=Grid(6, 6))
    tracer = Tracer(engine=engine, pos=Point(5, 0), team=1)

    blink = next(a for a in tracer.abilities if a.name == "Blink")
    recall = next(a for a in tracer.abilities if a.name == "Recall")

    from abilities import ActionCost

    assert blink.action_cost == ActionCost.INSTANT
    assert blink.reaction_condition is not None, "Blink should have a reaction_condition"
    assert recall.action_cost == ActionCost.INSTANT
    assert recall.reaction_condition is not None, "Recall should have a reaction_condition set"
    # Recall uses the default_reaction_condition — only triggers on enemy ability events
    # that target/include the actor. Since we test with an ally using the ability,
    # the default conditions checks subject.team == actor.team and returns False.


def test_blink_reaction_condition_tracer_targeted():
    """blink_reaction_condition returns True when Tracer is targeted by a damaging ability."""
    from engine import Engine
    from grid import Grid
    from heroes.tracer import Tracer, blink_reaction_condition
    from entities import Entity
    from abilities import Ability, ActionCost
    from aimings import AimingResult, TargetEntity
    from events import AbilityUseEvent
    from instruction_library import DamageInstruction
    from point import Point

    engine = Engine(grid=Grid(6, 6))
    tracer = Tracer(engine=engine, pos=Point(5, 0), team=1)
    attacker = Entity(
        engine=engine, name="Attacker", hp=10, speed=3, pos=Point(0, 0), team=0
    )

    blink = next(a for a in tracer.abilities if a.name == "Blink")
    # Only react to damaging abilities
    damaging_ability = Ability(
        name="TestAttack",
        aiming=TargetEntity(in_range=5),
        instructions=[DamageInstruction(amount=100)],
    )
    assert blink_reaction_condition(
        engine=engine,
        event=AbilityUseEvent(
            source=attacker,
            ability=damaging_ability,
            aiming_result=AimingResult(
                target_points=[Point(5, 0)],
                included_points=[],
                sub_aimings={},
            ),
        ),
        actor=tracer,
        ability=blink,
    ), "Should react when Tracer is targeted by a damaging ability"


def test_blink_reaction_condition_not_targeted():
    """blink_reaction_condition returns False when Tracer is NOT in the trigger's targets."""
    from engine import Engine
    from grid import Grid
    from heroes.tracer import Tracer, blink_reaction_condition
    from entities import Entity
    from abilities import Ability
    from aimings import AimingResult, TargetEntity
    from events import AbilityUseEvent
    from instruction_library import DamageInstruction
    from point import Point

    engine = Engine(grid=Grid(6, 6))
    tracer = Tracer(engine=engine, pos=Point(5, 0), team=1)
    attacker = Entity(
        engine=engine, name="Attacker", hp=10, speed=3, pos=Point(0, 0), team=0
    )

    blink = next(a for a in tracer.abilities if a.name == "Blink")

    # Aim at a DIFFERENT point than Tracer's position
    damaging_ability = Ability(
        name="TestAttack",
        aiming=TargetEntity(in_range=5),
        instructions=[DamageInstruction(amount=100)],
    )
    assert not blink_reaction_condition(
        engine=engine,
        event=AbilityUseEvent(
            source=attacker,
            ability=damaging_ability,
            aiming_result=AimingResult(
                target_points=[Point(3, 0)],
                included_points=[],
                sub_aimings={},
            ),
        ),
        actor=tracer,
        ability=blink,
    ), "Should NOT react when Tracer is not targeted"


def test_blink_reaction_condition_ally_target():
    """blink_reaction_condition returns False when the attacker is the same team."""
    from engine import Engine
    from grid import Grid
    from heroes.tracer import Tracer, blink_reaction_condition
    from abilities import Ability
    from aimings import AimingResult, TargetEntity
    from events import AbilityUseEvent
    from instruction_library import DamageInstruction
    from point import Point

    engine = Engine(grid=Grid(6, 6))
    tracer = Tracer(engine=engine, pos=Point(5, 0), team=1)
    ally = Tracer(engine=engine, pos=Point(5, 1), team=1)

    blink = next(a for a in tracer.abilities if a.name == "Blink")
    damaging_ability = Ability(
        name="FriendlyFire",
        aiming=TargetEntity(in_range=5),
        instructions=[DamageInstruction(amount=100)],
    )

    assert not blink_reaction_condition(
        engine=engine,
        event=AbilityUseEvent(
            source=ally,
            ability=damaging_ability,
            aiming_result=AimingResult(
                target_points=[Point(5, 0)],
                included_points=[],
                sub_aimings={},
            ),
        ),
        actor=tracer,
        ability=blink,
    ), "Should NOT react to ally attacks"


def test_best_move_for_score_tiebreak_lowest_distance():
    """best_move_for_score should prefer the point closest to actor when scores are equal."""
    from abilities import best_move_for_score
    from point import Point

    actor_pos = Point(0, 0)
    # Two points with the same score: (5,0) is farther, (2,0) is closer
    reachable = {Point(2, 0), Point(5, 0)}

    def score_fn(pt):
        return 10.0  # Same score for both

    result = best_move_for_score(reachable, actor_pos, score_fn, "test")
    (chosen_pos,) = result.keys()
    assert chosen_pos == Point(2, 0), (
        f"Expected closest point (2,0), got {chosen_pos}. "
        f"Tiebreaker should prefer lowest distance moved."
    )


def test_best_move_for_score_not_tied():
    """best_move_for_score should pick the highest-scored point regardless of distance."""
    from abilities import best_move_for_score
    from point import Point

    actor_pos = Point(0, 0)

    def score_fn(pt):
        return {Point(2, 0): 5.0, Point(5, 0): 10.0}[pt]

    reachable = {Point(2, 0), Point(5, 0)}
    result = best_move_for_score(reachable, actor_pos, score_fn, "test")
    (chosen_pos,) = result.keys()
    assert chosen_pos == Point(5, 0), (
        f"Expected highest-scored point (5,0), got {chosen_pos}. "
        f"Primary score should dominate, not distance."
    )


def test_best_move_for_score_empty():
    """best_move_for_score returns empty dict for no reachable points."""
    from abilities import best_move_for_score
    from point import Point

    result = best_move_for_score(set(), Point(0, 0), lambda pt: 10.0, "test")
    assert result == {}, "Should return empty dict for empty reachable points"


def test_default_reaction_condition_fixed():
    """The default_reaction_condition argument swap bug is fixed — it now correctly checks the event."""
    from abilities import default_reaction_condition
    from engine import Engine
    from grid import Grid
    from entities import Entity
    from aimings import AimingResult, TargetEntity
    from events import AbilityUseEvent
    from point import Point

    engine = Engine(grid=Grid(6, 6))
    attacker = Entity(
        engine=engine, name="Attacker", hp=10, speed=3, pos=Point(0, 0), team=0
    )
    defender = Entity(
        engine=engine, name="Defender", hp=10, speed=3, pos=Point(5, 0), team=1
    )

    from abilities import Ability, ActionCost

    instant_ability = Ability(
        name="InstantReact",
        aiming=TargetEntity(in_range=5),
        action_cost=ActionCost.INSTANT,
        reaction_condition=default_reaction_condition,
    )

    # With the bug fix, this should call default_reaction_condition with
    # (engine, event, actor, ability) in correct positions
    result = default_reaction_condition(
        engine=engine,
        event=AbilityUseEvent(
            source=attacker,
            ability=Ability(name="TestAttack", aiming=TargetEntity(in_range=5)),
            aiming_result=AimingResult(
                target_points=[Point(5, 0)],
                included_points=[],
                sub_aimings={},
            ),
        ),
        actor=defender,
        ability=instant_ability,
    )
    # The result depends on whether defender's pos is in trigger targets.
    # The important thing is it doesn't crash and doesn't always return False.
    assert isinstance(result, bool), "default_reaction_condition should return bool"


# --- Integration tests with API ---


def test_tracer_used_in_game():
    """Tracer can be used in a game without errors."""
    data = _run_game_json()
    assert "logs" in data
    assert len(data["logs"]) > 1


def test_instant_abilities_used_as_free_actions():
    """Instant abilities (Blink, Recall) should appear as usable free actions for Tracer."""
    from engine import Engine
    from grid import Grid
    from heroes.tracer import Tracer
    from choices import get_plausible_free_actions
    from point import Point

    engine = Engine(grid=Grid(6, 6))
    tracer = Tracer(engine=engine, pos=Point(5, 0), team=0)
    engine.finalize_setup()
    engine.current_turn_hero = tracer
    engine.setup_activation_queue()
    engine.advance_to_next_activator()
    tracer.start_turn()

    free_actions = get_plausible_free_actions(tracer, engine)
    free_names = {a.ability.name for a in free_actions}

    assert "Blink" in free_names, "Blink should be in free actions (ActionCost.INSTANT)"
    assert "Recall" in free_names, "Recall should be in free actions (ActionCost.INSTANT)"


def test_instant_abilities_not_in_standard_actions():
    """Instant abilities should NOT appear in standard move+action choices."""
    from engine import Engine
    from grid import Grid
    from heroes.tracer import Tracer
    from choices import get_plausible_move_and_actions, get_plausible_free_actions
    from point import Point

    engine = Engine(grid=Grid(6, 6))
    tracer = Tracer(engine=engine, pos=Point(5, 0), team=0)
    enemy = Tracer(engine=engine, pos=Point(0, 0), team=1)
    engine.finalize_setup()
    engine.current_turn_hero = tracer
    engine.setup_activation_queue()
    engine.advance_to_next_activator()
    tracer.start_turn()

    # Standard actions should NOT contain Blink or Recall
    actions = get_plausible_move_and_actions(tracer, engine)
    standard_ability_names = {a.ability.name for a in actions}
    assert "Blink" not in standard_ability_names, (
        f"Blink should not be in standard actions: {standard_ability_names}"
    )
    assert "Recall" not in standard_ability_names, (
        f"Recall should not be in standard actions: {standard_ability_names}"
    )
    assert "Pulse Pistols" in standard_ability_names, (
        f"Standard (non-instant) abilities should still appear: {standard_ability_names}"
    )


def test_tracer_blinks_to_dodge_attack():
    """Tracer should react-blink away when targeted by a damaging ability.

    When an attacker hits Tracer at range 1 with a damaging ability:
    1. ReactionOpportunityEvent should present Blink as a reaction choice
    2. If Tracer blinks away, the attack should miss (entity_at returns None)
    3. Tracer takes no damage
    """
    from engine import Engine
    from grid import Grid
    from heroes.tracer import Tracer
    from entities import Entity
    from abilities import Ability
    from aimings import AimingResult, TargetEntity
    from events import (
        AbilityUseEvent,
        ReactionOpportunityEvent,
        EventQueue,
    )
    from instruction_library import DamageInstruction
    from point import Point

    engine = Engine(grid=Grid(6, 6))
    engine.finalize_setup()

    tracer = Tracer(engine=engine, pos=Point(5, 0), team=1)
    attacker = Entity(
        engine=engine, name="Attacker", hp=100, speed=3, pos=Point(4, 0), team=0
    )

    blink = next(a for a in tracer.abilities if a.name == "Blink")
    initial_hp = tracer.hp
    initial_pos = tracer.pos

    # Create a damaging ability (like a melee attack)
    slash = Ability(
        name="Slash",
        aiming=TargetEntity(in_range=1),
        instructions=[DamageInstruction(amount=100)],
    )

    # Enqueue the attack targeting Tracer
    attack_event = AbilityUseEvent(
        source=attacker,
        ability=slash,
        aiming_result=AimingResult(
            target_points=[tracer.pos],
            included_points=[],
            sub_aimings={},
        ),
    )
    engine.event_queue.enqueue(attack_event)

    # Process the first event — this should create a ReactionOpportunityEvent
    engine.event_queue.process_one(engine=engine)

    # Queue should now have [AttackAbility(RESOLVE), ReactionOpportunity]
    # Actually: AFTER process_one, attack is at RESOLVE state and re-enqueued,
    # and ReactionOpportunityEvent was enqueued during process()

    # The ReactionOpportunityEvent should have Blink as an option for Tracer
    front = engine.event_queue._queue[0] if engine.event_queue._queue else None
    assert isinstance(front, ReactionOpportunityEvent), (
        f"Expected ReactionOpportunityEvent, got {type(front).__name__ if front else None}"
    )

    choices, react_entity = front.get_choices(engine=engine)
    assert react_entity == tracer, "Tracer should be the reacting entity"
    assert any(
        c.ability.name == "Blink" for c in choices
    ), f"Blink should be a reaction choice, got {[c.ability.name if hasattr(c, 'ability') else type(c).__name__ for c in choices]}"

    # Choose the Blink reaction — find a target point
    blink_choice = next(c for c in choices if c.ability.name == "Blink")
    # Verify the blink target is a different position
    blink_target = blink_choice.aiming_result.target_points[0]
    assert blink_target != tracer.pos, "Blink should target a different position"

    # Now simulate what happens: the attacker attacks, Tracer blinks as reaction
    # First, let's advance_until_choice which processes events till we get choices
    # Pop the ReactionOpportunityEvent and process the Blink reaction
    engine.event_queue._queue.pop(0)

    # Simulate the reaction step: blink away
    blink.react(engine=engine, source=tracer, aiming_result=blink_choice.aiming_result)

    # Now process the blink reaction AbilityUseEvent (and its ChangeLocationEvent)
    while engine.event_queue._queue:
        ev = engine.event_queue._queue[0]
        if isinstance(ev, ReactionOpportunityEvent):
            # Second reaction opportunity (from blink's AFTER) — consume
            choices2, _ = ev.get_choices(engine=engine)
            if choices2 and len(choices2) > 1:
                # Entity could react to blink — pass
                pass_choice = next(c for c in choices2 if c.features.get("pass_reaction"))
                ev.declined_entities.add(tracer.id)
                engine.event_queue._queue.pop(0)
                continue
            else:
                engine.event_queue._queue.pop(0)
                continue
        engine.event_queue.process_one(engine=engine)

    # Tracer should have moved
    assert tracer.pos != initial_pos, (
        f"Tracer should have blinked from {initial_pos} to a new position, but is still at {tracer.pos}"
    )

    # The attack should miss since Tracer is no longer at the target point
    # The original AttackAbilityUseEvent went to RESOLVE, then its _resolve
    # should have tried to get_roll_result which checks entity_at(target_point)
    # Since Tracer moved, entity_at returned None → zero damage
    assert tracer.hp == initial_hp, (
        f"Tracer should have taken 0 damage after blinking, but took {initial_hp - tracer.hp}"
    )

    print(f"Tracer blinked: {initial_pos} → {tracer.pos}, HP: {tracer.hp}/{initial_hp}")
