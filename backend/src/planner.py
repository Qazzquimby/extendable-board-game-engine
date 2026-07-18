"""
Planner — plausible moves and actions for AI decision-making.

Extracted from choices.py to keep modules under 400 lines.
Contains movement planning, action evaluation, and the
_ActorMovedView utility for simulating position changes.
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any, TYPE_CHECKING, Union

from aimings import TargetEntity, IncludeArea, TargetSelf, TargetPoint, AimingResult, MultipleAiming
from point import Point
from queries import QueryLegalAimings, QuerySpeed
from util import UniqueTuple, DO_NOTHING
from valence import Valence

if TYPE_CHECKING:
    from engine import Engine
    from entities import Entity
    from choices import PlausibleMoveAndAction, PlausibleFreeAction, Choice


def get_plausible_move_and_actions(
    actor: "Entity",
    engine: "Engine",
) -> List[PlausibleMoveAndAction]:
    proposed_moves = get_plausible_movements(actor=actor, engine=engine)

    actions_map = {}
    for move_pos, movement_name in proposed_moves.items():
        actions_map.update(
            get_plausible_actions_after_movement(
                actor=actor,
                engine=engine,
                move_pos=move_pos,
                movement_name=movement_name,
            )
        )

    actions = list(actions_map.values())
    assert actions
    return actions


def get_plausible_movements(
    actor: "Entity",
    engine: "Engine",
) -> Dict[Point, str]:
    living = engine.living_entities
    enemies = [e for e in living if e.team != actor.team]
    allies = [e for e in living if e.team == actor.team and e != actor]

    reachable_points = engine.grid.get_movable_spaces(
        engine=engine,
        actor=actor,
        max_movement=QuerySpeed(actor).resolve(engine).value,
    )

    occupied_points = {e.pos for e in living if e != actor and e.pos is not None}
    reachable_points = {p for p in reachable_points if p not in occupied_points}

    proposed_moves = {actor.pos: "Stay"}
    if reachable_points:
        for ability in actor.abilities:
            if ability.is_available(round_num=engine.round_num):
                proposed_moves.update(
                    ability.get_movement(
                        engine, actor, reachable_points, enemies, allies
                    )
                )

        if len(proposed_moves) == 1:
            pref_pos = actor.get_preferred_position(engine)
            if pref_pos:
                best_move = min(
                    reachable_points,
                    key=lambda p: (
                        p.get_distance(pref_pos),
                        p.get_distance(actor.pos),
                    ),
                )
                if best_move != actor.pos:
                    proposed_moves = {best_move: "Move towards preferred position"}

    return proposed_moves


def get_plausible_actions_after_movement(
    actor: "Entity",
    engine: "Engine",
    move_pos: Point,
    movement_name: str,
) -> dict[tuple, PlausibleMoveAndAction]:
    actions = {}
    for ability in actor.abilities:
        if not ability.is_available(round_num=engine.round_num):
            continue
        from abilities import ActionCost
        if ability.action_cost == ActionCost.INSTANT:
            continue
        actions.update(
            get_plausible_uses_of_ability_after_movement(
                actor=actor,
                engine=engine,
                move_pos=move_pos,
                movement_name=movement_name,
                ability=ability,
            )
        )

    non_passing_actions = {
        k: v for k, v in actions.items() if v.ability.name != DO_NOTHING
    }
    if non_passing_actions and any(
        v.ability.valence in (Valence.GOOD, Valence.BAD)
        for v in non_passing_actions.values()
    ):
        actions = non_passing_actions

    assert actions, f"No valid actions for {actor.name} at {move_pos}"
    return actions


def get_plausible_uses_of_ability_after_movement(
    actor: "Entity",
    engine: "Engine",
    move_pos: Point,
    movement_name: str,
    ability: "Ability",
) -> dict[tuple, "PlausibleMoveAndAction"]:
    from choices import PlausibleMoveAndAction

    if move_pos == actor.pos:
        move_path = []
    else:
        move_path = engine.grid.get_path(
            engine=engine, start=actor.pos, target=move_pos, actor=actor
        )
        if not move_path or move_path[-1] != move_pos:
            return {}

    return _get_plausible_uses_of_ability_at_pos(
        actor=actor,
        engine=engine,
        pos=move_pos,
        ability=ability,
        choice_class=PlausibleMoveAndAction,
        move_path=move_path,
        movement_name=movement_name,
    )


class _ActorMovedView:
    """A view of the engine that also acts as a context manager
    to temporarily move an actor to a new position."""

    def __init__(self, engine: "Engine", actor: "Entity", new_pos: Point):
        self._engine = engine
        self._actor = actor
        self._new_pos = new_pos
        self._original_pos = actor.pos

    def __enter__(self):
        if self._new_pos != self._original_pos:
            self._actor.pos = self._new_pos
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._new_pos != self._original_pos:
            self._actor.pos = self._original_pos

    def entity_at(self, pos: Point) -> Optional["Entity"]:
        return self._engine.entity_at(pos)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._engine, name)


def _get_plausible_uses_of_ability_at_pos(
    actor: "Entity",
    engine: "Engine",
    pos: Point,
    ability: "Ability",
    choice_class: type,
    **choice_kwargs,
) -> dict[tuple, PlausibleMoveAndAction]:
    plausible_uses = {}
    with _ActorMovedView(engine, actor, pos) as sim_engine:
        if ability.instructions:
            valences = set(instruction.valence for instruction in ability.instructions)
            has_good = Valence.GOOD in valences or Valence.MIXED in valences
            has_bad = Valence.BAD in valences or Valence.MIXED in valences
            if has_good and has_bad:
                valence = Valence.MIXED
            elif has_good:
                valence = Valence.GOOD
            elif has_bad:
                valence = Valence.BAD
            else:
                assert False
        else:
            valence = Valence.MIXED

        raw_aimings = ability.aiming.get_all_aimings(
            engine=sim_engine, actor=actor, start_pos=pos, require_los=True
        )

        legal_aimings = sim_engine.ask(
            QueryLegalAimings(subject=actor, ability=ability, base_result=raw_aimings)
        )

        for aiming_res in legal_aimings:
            priority = ability.evaluate_priority(engine, actor, pos, aiming_res)
            if priority <= 0 and ability.name != DO_NOTHING:
                continue

            if isinstance(ability.aiming, MultipleAiming):
                all_points = aiming_res.target_points + aiming_res.included_points

                if not all_points:
                    continue

                key = (pos, UniqueTuple(all_points), ability.get_hash())
                if key not in plausible_uses:
                    plausible_uses[key] = choice_class(
                        target=None,
                        ability=ability,
                        actor=actor,
                        aiming_result=aiming_res,
                        priority=priority,
                        **choice_kwargs,
                    )
            elif isinstance(ability.aiming, TargetEntity):
                for target_point in aiming_res.target_points:
                    target = engine.entity_at(target_point)
                    if not target:
                        continue
                    if (
                        valence == Valence.BAD
                        and target.team == actor.team
                        and isinstance(ability.aiming, TargetEntity)
                    ):
                        continue
                    if (
                        valence == Valence.GOOD
                        and target.team != actor.team
                        and isinstance(ability.aiming, TargetEntity)
                    ):
                        continue

                    key = (pos, target_point, ability.get_hash())
                    if key not in plausible_uses:
                        plausible_uses[key] = choice_class(
                            target=target,
                            ability=ability,
                            actor=actor,
                            aiming_result=aiming_res,
                            priority=priority,
                            **choice_kwargs,
                        )
            elif isinstance(ability.aiming, TargetSelf):
                key = (pos, actor.pos, ability.get_hash())
                if key not in plausible_uses:
                    plausible_uses[key] = choice_class(
                        target=actor,
                        ability=ability,
                        actor=actor,
                        aiming_result=aiming_res,
                        priority=priority,
                        **choice_kwargs,
                    )
            elif isinstance(ability.aiming, TargetPoint):
                for target_point in aiming_res.target_points:
                    key = (pos, target_point, ability.get_hash())
                    if key not in plausible_uses:
                        plausible_uses[key] = choice_class(
                            target=None,
                            ability=ability,
                            actor=actor,
                            aiming_result=aiming_res,
                            priority=priority,
                            **choice_kwargs,
                        )
            elif isinstance(ability.aiming, IncludeArea):
                affected_entities = {
                    e
                    for e in sim_engine.entities
                    if e.pos in aiming_res.included_points
                }
                if not affected_entities:
                    continue

                key = (
                    pos,
                    UniqueTuple(sorted(e.pos for e in affected_entities)),
                    ability.get_hash(),
                )
                if key not in plausible_uses:
                    if valence in (Valence.GOOD, Valence.MIXED):
                        valid_targets = [
                            e for e in affected_entities if e.team == actor.team
                        ]
                    elif valence in (Valence.BAD, Valence.MIXED):
                        valid_targets = [
                            e for e in affected_entities if e.team != actor.team
                        ]
                    else:
                        valid_targets = list(affected_entities)

                    if not valid_targets:
                        continue

                    plausible_uses[key] = choice_class(
                        target=None,
                        ability=ability,
                        actor=actor,
                        aiming_result=aiming_res,
                        priority=priority,
                        **choice_kwargs,
                    )

    return plausible_uses
