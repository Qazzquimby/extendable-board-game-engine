"""
Scoring — priority calculation functions for ability evaluation.

Extracted from abilities.py to keep modules under 400 lines.
Contains scoring heuristics, displacement valuation, and
reaction-value calculations used by the AI.
"""

from typing import Callable, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from engine import Engine
    from entities import Entity
    from point import Point
    from abilities import ActionContext, DynamicInt, AimingResult


def resolve_int(val: "DynamicInt", ctx: "ActionContext") -> int:
    return val(ctx) if callable(val) else val


def best_move_for_score(
    reachable_points: set["Point"],
    actor_pos: "Point",
    score_fn: Callable[["Point"], float],
    reason: str,
) -> dict["Point", str]:
    """Score each reachable point and return the best one with a reason string.

    Uses the standard tiebreaker: prefer the point closest to the actor.
    Returns an empty dict if no point scores > 0.
    """
    if not reachable_points:
        return {}
    best = max(
        reachable_points,
        key=lambda pt: (score_fn(pt), -pt.get_distance(actor_pos)),
    )
    tied = [pt for pt in reachable_points if score_fn(pt) == score_fn(best)]
    if tied and len(tied) > 1:
        return {min(tied, key=lambda pt: pt.get_distance(actor_pos)): reason}
    if score_fn(best) > 0:
        return {best: reason}
    return {}


def displacement_value(
    entity: "Entity",
    from_pos: "Point",
    to_pos: "Point",
    engine: "Engine",
) -> float:
    """How many movement-actions this displacement saves (or costs if negative).

    Positive = the entity ends up closer to its preferred position
    (its nearest enemy), saving future movement actions.
    Negative = the entity ends up farther away, needing extra actions to get back.

    Value = (old_distance - new_distance) / speed.
    """
    pref = entity.get_preferred_position(engine)
    if pref is None:
        return 0.0
    saved_distance = from_pos.get_distance(pref) - to_pos.get_distance(pref)
    speed = entity.get_speed(engine)
    if speed == 0:
        return 0.0
    return saved_distance / speed


def score_damage(amount: int, target_hp: int) -> float:
    """Score for dealing `amount` damage to a target with `target_hp`.

    Automatically values kills: damage is doubled if amount >= target_hp.
    Capped at target_hp (can't overkill for extra score).
    """
    effective = min(amount, target_hp)
    if amount >= target_hp:
        effective += 1.5  # killing is better than leaving low health
    return float(effective)


def score_expected_damage(
    amount: int,
    target_hp: int,
    target_defense: int = 0,
    ability_defense: int = 0,
    attacker_crit: int = 0,
) -> float:
    """Score for dealing `amount` damage, adjusted for miss/crit probability.

    Uses the 1d6 combat roll: hit if roll > defense, crit if roll >= 7-crit_chance.
    Accounts for the fact that crit is a subset of hit.
    """
    total_defense = min(4, target_defense + ability_defense)
    hit_values = max(0, 6 - total_defense)
    crit_values = min(attacker_crit, 6 - total_defense)
    exp_dmg = (hit_values - crit_values) / 6.0 * amount + crit_values / 6.0 * amount * 2
    if exp_dmg <= 0:
        return 0.0
    return score_damage(int(round(exp_dmg)), target_hp)


def score_heal(amount: int, missing_hp: int) -> float:
    """Score for healing `amount` on a target missing `missing_hp` HP.

    Capped at missing_hp (can't overheal for extra score).
    """
    return float(min(amount, missing_hp))


def score_add_token(token_class: "Type"):
    """Base priority for applying a token/modifier to a single target.

    Uses individual valence and duration for contextual valuation.
    Bad modifiers on enemies = 2 + min(duration, 3) * 0.5
    Good modifiers on allies = 1 + min(duration, 3) * 0.25
    """
    from valence import Valence

    if token_class.valence == Valence.BAD:
        duration = getattr(token_class, 'duration', None)
        duration_bonus = min(duration or 0, 3) * 0.5
        return 2.0 + duration_bonus
    elif token_class.valence == Valence.GOOD:
        duration = getattr(token_class, 'duration', None)
        duration_bonus = min(duration or 0, 3) * 0.25
        return 1.0 + duration_bonus
    return 0.0


def score_targets_in_area(
    aiming_result: "AimingResult",
    engine: "Engine",
    actor: "Entity",
    team_filter: str = "enemy",
) -> int:
    """Count valid targets in an aiming result's included/target points."""
    all_pts = list(aiming_result.target_points) + list(aiming_result.included_points)
    count = 0
    for pt in all_pts:
        target = engine.entity_at(pt)
        if target:
            if team_filter == "enemy" and target.team != actor.team:
                count += 1
            elif team_filter == "ally" and target.team == actor.team:
                count += 1
            elif team_filter == "any":
                count += 1
    return count


def score_missing_hp(actor: "Entity") -> float:
    """Priority based on how much HP the actor is missing.
    Returns 0.0 at full HP, scales up to 3.0 when near death.
    """
    missing = actor.max_hp - actor.hp
    if missing <= 0:
        return 0.0
    return min(missing * 0.5, 3.0)


def reaction_value_of_instructions(
    trigger_event: object,
    actor: "Entity",
    engine: "Engine",
    target_pos: "Point",
) -> float:
    """Total value of harmful instructions the trigger event would apply to `actor`.

    Determines which instruction sub-aimings include `target_pos` (the actor's
    original position), then scores each instruction by type. Composable so any
    dodge ability (Blink, Recall, etc.) can use the same logic.
    """
    from instruction_library import (
        DamageInstruction,
        AddTokenInstruction,
        AddModifierInstruction,
        PullInstruction,
        TeleportInstruction,
    )
    from events import AbilityUseEvent
    from valence import Valence

    if not isinstance(trigger_event, AbilityUseEvent):
        return 0.0

    total = 0.0
    aiming = trigger_event.aiming_result

    for inst in trigger_event.ability.instructions:
        if inst.aiming_name and aiming.sub_aimings:
            inst_aiming = aiming.sub_aimings.get(inst.aiming_name)
        else:
            inst_aiming = aiming

        if inst_aiming is None:
            continue

        all_pts = list(inst_aiming.target_points) + list(inst_aiming.included_points)
        if actor.pos not in all_pts:
            continue

        if isinstance(inst, DamageInstruction):
            dmg = inst.amount if isinstance(inst.amount, int) else 0
            total += score_damage(dmg, actor.hp) * 0.8
        elif isinstance(inst, AddTokenInstruction):
            token_val = score_add_token(inst.token_class)
            if token_val > 0 and inst.token_class.valence == Valence.BAD:
                total += token_val
        elif isinstance(inst, AddModifierInstruction):
            mod_val = score_add_token(inst.modifier_class)
            if mod_val > 0 and inst.modifier_class.valence == Valence.BAD:
                total += mod_val
        elif isinstance(inst, PullInstruction):
            dist = inst.distance if isinstance(inst.distance, int) else 0
            total += dist * 0.5
        elif isinstance(inst, TeleportInstruction):
            total += 0.5

    return total


def point_is_in_aiming_result(point: "Point", aiming_result: "AimingResult") -> bool:
    """True if `to_pos` is outside ALL of the trigger event's target/included points."""
    all_trigger_points = set()
    if aiming_result.sub_aimings:
        for res in aiming_result.sub_aimings.values():
            all_trigger_points.update(res.target_points)
            all_trigger_points.update(res.included_points)
    else:
        all_trigger_points.update(aiming_result.target_points)
        all_trigger_points.update(aiming_result.included_points)

    return point in all_trigger_points


def reaction_resource_conservation(
    ability: "Ability",
    engine: "Engine",
) -> float:
    """Penalty for using a charged/limited ability now vs saving for later.

    Returns a value 0..N that should be subtracted from the ability's priority.
    Higher when the ability is scarce (few charges) and the game is early.
    Lower when the game is nearly over or the ability has many charges.
    """
    if (
        ability.charges is None
        or ability.max_charges is None
        or ability.max_charges <= 0
    ):
        return 0.0

    charges_left = ability.charges
    game_progress = min(engine.round_num / 7.0, 1.0)
    used_fraction = 1.0 - (charges_left / ability.max_charges)

    if charges_left <= 1:
        conservation_factor = max(0, 1.0 - game_progress)
        return 1.5 * conservation_factor
    elif charges_left <= 2:
        conservation_factor = max(0, 1.0 - game_progress * 1.5)
        return 0.8 * conservation_factor

    return 0.0


def resolve_roll_result(
    ability: "Ability",
    aiming_result: "AimingResult",
    engine: "Engine",
    source: "Entity",
):
    """Resolve attack rolls for all target points in an aiming result.

    Returns a RollResult with hit/crit points determined by the 1d6 combat roll.
    Extracted from Ability.get_roll_result to reduce module size.
    """
    from ability_base import RollResult
    from queries import QueryRoll
    from logger import log
    from util import UniqueTuple

    if isinstance(aiming_result, dict):
        all_target_points = []
        for aiming_result_set in aiming_result.values():
            all_target_points += aiming_result_set.target_points
            all_target_points = UniqueTuple(all_target_points)
    else:
        all_target_points = aiming_result.target_points
    hit_target_points = []
    crit_target_points = []

    roll = None
    for target_point in all_target_points:
        target = engine.entity_at(target_point)
        if target:
            defense = target.get_defense(
                engine=engine, attack_source=source, ability=ability
            )
            defense += ability.defense
            defense = min(4, defense)
            crit_chance = source.get_crit(
                engine=engine, subject=target, ability=ability
            )

            if defense > 0 or crit_chance > 0:
                if not roll:
                    roll = QueryRoll(rng=engine.rng, subject=source).resolve(
                        engine=engine
                    )

                if roll > defense:
                    hit_target_points.append(target_point)
                    if roll >= 7 - crit_chance:
                        crit_target_points.append(target_point)
                        log(
                            f"Crit {target} with a roll of {roll} on crit chance {crit_chance}"
                        )
                else:
                    log(
                        f"Missed {target} with a roll of {roll} less than defense {defense}"
                    )
            else:
                hit_target_points.append(target_point)

    return RollResult(
        roll=roll,
        hit_points=UniqueTuple(hit_target_points),
        crit_points=UniqueTuple(crit_target_points),
    )
