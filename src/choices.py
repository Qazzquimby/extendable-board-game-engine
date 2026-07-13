from typing import List, Optional, Dict, Any, TYPE_CHECKING, Union

from abilities import Ability, ActionCost
from aimings import TargetEntity, IncludeArea, TargetSelf, AimingResult, MultipleAiming
from point import Point
from queries import QueryLegalAimings, QuerySpeed
from util import UniqueTuple, DO_NOTHING
from valence import Valence

if TYPE_CHECKING:
    from engine import Engine
    from entities import Entity


class Choice:
    def __init__(self, features: Dict[str, Any] = None, priority: float = 1.0):
        if features is None:
            features = {}
        self.features = features
        self.priority = priority

    def __hash__(self):
        try:
            return hash(frozenset(self.features.items()))
        except TypeError:
            return id(self)

    def __eq__(self, other):
        if type(self) is not type(other):
            return False
        return self.features == other.features


class PlausibleMoveAndAction(Choice):
    def __init__(
        self,
        move_path: List[Point],
        target: Optional["Entity"],  # TODO use ID
        ability: "Ability",
        movement_name: str = "",
        actor: "Entity" = None,
        aiming_result: "AimingResult" = None,
        priority: float = 1.0,
    ):
        # todo right now aoe uses target None.
        #  Probably better to have a list of targets. Ml will need adjusting
        self.move_path = move_path
        if move_path:
            self.move_pos = move_path[-1]
        else:
            self.move_pos = actor.pos
        self.target = target
        self.ability = ability
        self.movement_name = movement_name
        self.aiming_result = aiming_result
        self.actor = actor
        super().__init__(features={}, priority=priority)

    def __str__(self):
        return f"{self.ability.owner_id} go to {self.move_pos} and use {self.ability.name} on {self.target.pos if self.target else None}"

    def __hash__(self):
        return hash(
            (self.ability.name, self.movement_name, self.move_pos, self.aiming_result)
        )

    def __eq__(self, other):
        if not isinstance(other, PlausibleMoveAndAction):
            return False
        return (
            self.ability.name,
            self.movement_name,
            self.move_pos,
            self.aiming_result,
        ) == (
            other.ability.name,
            other.movement_name,
            other.move_pos,
            other.aiming_result,
        )


def get_plausible_move_and_actions(
    actor: "Entity",
    engine: "Engine",
) -> List[PlausibleMoveAndAction]:
    proposed_moves = get_plausible_movements(
        actor=actor,
        engine=engine,
    )
    # 2. For each move position, find all possible actions
    actions_map = {}  # Use dict to store unique actions
    for move_pos, movement_name in proposed_moves.items():
        plausible_actions_after_movement = get_plausible_actions_after_movement(
            actor=actor,
            engine=engine,
            move_pos=move_pos,
            movement_name=movement_name,
        )
        actions_map.update(plausible_actions_after_movement)

    actions = list(actions_map.values())
    assert actions
    return actions


def get_plausible_movements(
    actor: "Entity",
    engine: "Engine",
) -> Dict[Point, str]:
    enemies = [e for e in engine.entities if e.team != actor.team and e.hp > 0]
    allies = [
        e for e in engine.entities if e.team == actor.team and e != actor and e.hp > 0
    ]
    reachable_points = engine.grid.get_movable_spaces(
        engine=engine,
        actor=actor,
        max_movement=QuerySpeed(actor).resolve(engine).value,
    )

    occupied_points = {
        e.pos for e in engine.entities if e != actor and e.pos is not None and e.hp > 0
    }
    reachable_points = {p for p in reachable_points if p not in occupied_points}

    proposed_moves = {actor.pos: "Stay"}
    if reachable_points:
        # For each enemy, find a good position to approach
        for enemy in enemies:
            best_close_to_enemy = min(
                reachable_points,
                key=lambda point: (
                    point.get_distance(enemy.pos) * 100 + point.get_distance(actor.pos),
                    point.x,
                    point.y,
                ),
            )
            proposed_moves[best_close_to_enemy] = f"Approach {enemy.name} {enemy.id}"

        for ability in actor.abilities:
            proposed_moves.update(
                ability.get_movement(engine, actor, reachable_points, enemies, allies)
            )

        # For each ally, find a good position to "guard" them from nearest enemy
        for ally in allies:
            if enemies:
                nearest_enemy_to_ally = min(
                    enemies, key=lambda e: ally.pos.get_distance(e.pos)
                )
                ally_dist_to_enemy = ally.pos.get_distance(nearest_enemy_to_ally.pos)

                def betweenness_score(point: Point):
                    distance_to_ally = point.get_distance(ally.pos)
                    distance_to_enemy = point.get_distance(nearest_enemy_to_ally.pos)
                    detour = (distance_to_ally + distance_to_enemy) - ally_dist_to_enemy
                    return detour * 10 + distance_to_enemy, point.x, point.y

                best_guard_ally = min(reachable_points, key=betweenness_score)
                proposed_moves[best_guard_ally] = (
                    f"Guard {ally.name} {ally.id} from {nearest_enemy_to_ally.name} {nearest_enemy_to_ally.id}"
                )
    return proposed_moves


def get_plausible_actions_after_movement(
    actor: "Entity",
    engine: "Engine",
    move_pos: Point,
    movement_name: str,
) -> dict[tuple, PlausibleMoveAndAction]:
    plausible_actions_after_movement = {}
    for ability in actor.abilities:
        if not ability.is_available():
            continue
        plausible_uses_of_ability_after_movement = (
            get_plausible_uses_of_ability_after_movement(
                actor=actor,
                engine=engine,
                move_pos=move_pos,
                movement_name=movement_name,
                ability=ability,
            )
        )
        plausible_actions_after_movement.update(
            plausible_uses_of_ability_after_movement
        )

    # If any without name "Do Nothing" available, remove "Do Nothing"
    non_passing_plausible_actions_after_movement: dict[
        tuple, PlausibleMoveAndAction
    ] = {
        k: v
        for (k, v) in plausible_actions_after_movement.items()
        if v.ability.name != DO_NOTHING
    }
    if non_passing_plausible_actions_after_movement and any(
        v.ability.valence in (Valence.GOOD, Valence.BAD)
        for v in non_passing_plausible_actions_after_movement.values()
    ):
        plausible_actions_after_movement = non_passing_plausible_actions_after_movement
    assert plausible_actions_after_movement
    return plausible_actions_after_movement


class PlausibleFreeAction(Choice):
    def __init__(
        self,
        target: Optional["Entity"],
        ability: "Ability",
        actor: "Entity",
        aiming_result: "AimingResult",
        priority: float = 1.0,
        **kwargs,
    ):
        self.target = target
        self.ability = ability
        self.aiming_result = aiming_result
        self.actor = actor

        super().__init__(priority=priority)

    def __hash__(self):
        return hash((self.ability.name, self.aiming_result))

    def __eq__(self, other):
        if not isinstance(other, PlausibleFreeAction):
            return False
        return (self.ability.name, self.aiming_result) == (
            other.ability.name,
            other.aiming_result,
        )

    @property
    def ends_turn(self) -> bool:
        return False


PlausibleActionOrMoveAndAction = Union[PlausibleFreeAction, PlausibleMoveAndAction]


def get_plausible_free_actions(
    actor: "Entity",
    engine: "Engine",
) -> List[PlausibleFreeAction]:
    plausible_actions = {}
    for ability in actor.abilities:
        if (
            ability.action_cost not in (ActionCost.FREE, ActionCost.INSTANT)
            or not ability.is_available()
        ):
            continue

        plausible_uses = _get_plausible_uses_of_ability_at_pos(
            actor=actor,
            engine=engine,
            pos=actor.pos,
            ability=ability,
            choice_class=PlausibleFreeAction,
        )
        plausible_actions.update(plausible_uses)

    return list(plausible_actions.values())


def get_plausible_uses_of_ability_after_movement(
    actor: "Entity",
    engine: "Engine",
    move_pos: Point,
    movement_name: str,
    ability: "Ability",
) -> dict[tuple, PlausibleMoveAndAction]:
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
            if not ability.is_plausible(engine, actor, pos, aiming_res):
                continue
            priority = ability.get_priority(engine, actor, pos, aiming_res)

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
                # target self just targets self. Ignore aiming_res.
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
