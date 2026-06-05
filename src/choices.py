from typing import List, Optional, Dict, Any, TYPE_CHECKING, Union

from abilities import Ability, ActionContext, ActionCost
from ai.feature_definitions import NEW_LOCATION
from aimings import TargetEntity, IncludeArea, TargetSelf, AimingResult, MultipleAiming
from entities import Entity
from point import Point
from queries import QueryLegalAimings

if TYPE_CHECKING:
    from engine import Engine
    from features import ChoiceFeatureEvaluator


class Choice:
    def __init__(self, features: Dict[str, Any]):
        self.features = features


class PlausibleMoveAndAction(Choice):
    def __init__(
        self,
        move_path: List[Point],
        target: Optional["Entity"],
        ability: "Ability",
        movement_name: str = "",
        engine: "Engine" = None,
        actor: "Entity" = None,
        aiming_result: "AimingResult" = None,
        feature_evaluator: Optional["ChoiceFeatureEvaluator"] = None,
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

        features = (
            self._compute_features(actor, engine, feature_evaluator)
            if engine and actor and aiming_result
            else {}
        )
        super().__init__(features=features)

    def _compute_features(
        self,
        actor: "Entity",
        engine: "Engine",
        feature_evaluator: Optional["ChoiceFeatureEvaluator"] = None,
    ) -> Dict[str, Any]:
        base_features = {NEW_LOCATION(name=actor.name): self.move_pos}
        return _compute_ability_features(
            actor=actor,
            engine=engine,
            ability=self.ability,
            aiming_result=self.aiming_result,
            feature_evaluator=feature_evaluator,
            base_features=base_features,
            choice=self,
        )


def get_plausible_move_and_actions(
    actor: "Entity",
    engine: "Engine",
    feature_evaluator: Optional["ChoiceFeatureEvaluator"] = None,
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
            feature_evaluator=feature_evaluator,
        )
        actions_map.update(plausible_actions_after_movement)

    actions = list(actions_map.values())
    assert actions
    return actions


def get_plausible_movements(
    actor: "Entity",
    engine: "Engine",
):
    enemies = [e for e in engine.entities if e.team != actor.team and e.hp > 0]
    allies = [
        e for e in engine.entities if e.team == actor.team and e != actor and e.hp > 0
    ]
    enemy_points = {e.pos for e in enemies if e.pos is not None}
    ally_points = {e.pos for e in allies if e.pos is not None}
    reachable_points = engine.grid.get_movable_spaces(
        start=actor.pos,
        max_movement=actor.speed,
        enemy_points=enemy_points,
        ally_points=ally_points,
    )
    reachable_points.add(actor.pos)

    proposed_moves = {actor.pos: "Stay"}
    if reachable_points:
        # For each enemy, find a good position to approach
        for enemy in enemies:
            best_close_to_enemy = min(
                reachable_points,
                key=lambda point: (
                    point.get_distance(enemy.pos) * 100 + point.get_distance(actor.pos)
                ),
            )
            proposed_moves[best_close_to_enemy] = f"Approach {enemy.name} {enemy.id}"

            # For each ability that can target units/areas, find a spot at optimal range
            for ability in actor.abilities:
                attack_range = 0
                if isinstance(ability.aiming, TargetEntity):
                    attack_range = ability.aiming.in_range
                elif isinstance(ability.aiming, IncludeArea):
                    attack_range = ability.aiming.area.in_range  # todo plus radius

                if attack_range > 0:
                    best_at_range = min(
                        reachable_points,
                        key=lambda point: abs(
                            point.get_distance(enemy.pos) - attack_range
                        )
                        * 100
                        + point.get_distance(actor.pos),
                    )
                    proposed_moves[best_at_range] = (
                        f"Range {attack_range} for {ability.name}"
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
                    return detour * 10 + distance_to_enemy

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
    feature_evaluator: Optional["ChoiceFeatureEvaluator"] = None,
) -> dict[tuple, PlausibleMoveAndAction]:
    plausible_actions_after_movement = {}
    for ability in actor.abilities:
        plausible_uses_of_ability_after_movement = (
            get_plausible_uses_of_ability_after_movement(
                actor=actor,
                engine=engine,
                move_pos=move_pos,
                movement_name=movement_name,
                ability=ability,
                feature_evaluator=feature_evaluator,
            )
        )
        plausible_actions_after_movement.update(
            plausible_uses_of_ability_after_movement
        )
    # assert plausible_actions_after_movement
    if not plausible_actions_after_movement:
        print("Impossible")
        get_plausible_uses_of_ability_after_movement(
            actor=actor,
            engine=engine,
            move_pos=move_pos,
            movement_name=movement_name,
            ability=actor.abilities[0],
            feature_evaluator=feature_evaluator,
        )

    # including pass turn
    return plausible_actions_after_movement


def _compute_ability_features(
    actor: "Entity",
    engine: "Engine",
    ability: "Ability",
    aiming_result: "AimingResult",
    feature_evaluator: Optional["ChoiceFeatureEvaluator"],
    base_features: Dict[str, Any],
    choice: "PlausibleActionOrMoveAndAction",
) -> Dict[str, Any]:
    features = base_features.copy()

    feature_name_parts = [f"use {ability.name}"]
    if aiming_result.sub_aimings:
        # MultipleAiming case
        for aiming_name, sub_aiming_result in aiming_result.sub_aimings.items():
            target_names = set()
            all_sub_points = set(sub_aiming_result.target_points) | set(
                sub_aiming_result.included_points
            )
            for p in all_sub_points:
                entity = engine.entity_at(p)
                if entity:
                    target_names.add(entity.name)

            for target_name in target_names:
                features[f"{ability.name} {aiming_name} on {target_name}"] = 1
    else:
        # Single aiming case
        target_names = set()
        all_points = set(aiming_result.target_points) | set(
            aiming_result.included_points
        )
        for p in all_points:
            entity = engine.entity_at(p)
            if entity:
                target_names.add(entity.name)
        for target_name in target_names:
            features[f"{ability.name} on {target_name}"] = 1

    all_points = set(aiming_result.target_points) | set(aiming_result.included_points)

    for instruction in ability.instructions:
        for point in all_points:
            ctx = ActionContext(
                engine=engine,
                source=actor,
                subject_point=point,
                target_points=aiming_result.target_points,
                included_points=aiming_result.included_points,
                ability=ability,
                is_hit=True,
                is_crit=False,
            )
            instruction_features = instruction.get_features(ctx)

            for key, value in instruction_features.items():
                if key in features:
                    if isinstance(value, (int, float)):
                        features[key] += value
                    else:
                        features[key] = value
                else:
                    features[key] = value

    # Derived features
    for entity in engine.entities:
        new_pos_key = f"new_location_{entity.name}"
        entity_pos = features.get(new_pos_key, entity.pos)
        if not entity_pos:
            continue

        for other_entity in engine.entities:
            if entity.id >= other_entity.id:
                continue

            other_pos_key = f"new_location_{other_entity.name}"
            other_pos = features.get(other_pos_key, other_entity.pos)
            if not other_pos:
                continue

            dist = engine.grid.get_range(entity_pos, other_pos)
            key = f"distance_{entity.name}_to_{other_entity.name}"
            features[key] = dist

    if feature_evaluator:
        eval_features = feature_evaluator.evaluate(
            engine=engine,
            actor=actor,
            choice=choice,
            core_features=features,
        )
        features.update(eval_features)

    return features


class PlausibleFreeAction(Choice):
    def __init__(
        self,
        target: Optional["Entity"],
        ability: "Ability",
        engine: "Engine",
        actor: "Entity",
        aiming_result: "AimingResult",
        feature_evaluator: Optional["ChoiceFeatureEvaluator"] = None,
        **kwargs,
    ):
        self.target = target
        self.ability = ability
        self.aiming_result = aiming_result

        features = self._compute_features(actor, engine, feature_evaluator)
        super().__init__(features=features)

    @property
    def ends_turn(self) -> bool:
        return False

    def _compute_features(
        self,
        actor: "Entity",
        engine: "Engine",
        feature_evaluator: Optional["ChoiceFeatureEvaluator"] = None,
    ) -> Dict[str, Any]:
        return _compute_ability_features(
            actor=actor,
            engine=engine,
            ability=self.ability,
            aiming_result=self.aiming_result,
            feature_evaluator=feature_evaluator,
            base_features={},
            choice=self,
        )


PlausibleActionOrMoveAndAction = Union[PlausibleFreeAction, PlausibleMoveAndAction]


def get_plausible_free_actions(
    actor: "Entity",
    engine: "Engine",
    feature_evaluator: Optional["ChoiceFeatureEvaluator"] = None,
) -> List[PlausibleFreeAction]:
    plausible_actions = {}
    for ability in actor.abilities:
        if ability.action_cost != ActionCost.FREE:
            continue

        plausible_uses = _get_plausible_uses_of_ability_at_pos(
            actor=actor,
            engine=engine,
            pos=actor.pos,
            ability=ability,
            feature_evaluator=feature_evaluator,
            choice_class=PlausibleFreeAction,
        )
        plausible_actions.update(plausible_uses)

    return list(plausible_actions.values())


def get_plausible_uses_of_ability_after_movement(
    actor: Entity,
    engine: "Engine",
    move_pos: Point,
    movement_name: str,
    ability: "Ability",
    feature_evaluator: Optional["ChoiceFeatureEvaluator"] = None,
) -> dict[tuple, PlausibleMoveAndAction]:
    if move_pos == actor.pos:
        move_path = []
    else:
        move_path = engine.grid.get_path(start=actor.pos, target=move_pos)

    return _get_plausible_uses_of_ability_at_pos(
        actor=actor,
        engine=engine,
        pos=move_pos,
        ability=ability,
        feature_evaluator=feature_evaluator,
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
        if self._new_pos == self._original_pos:
            return self._engine.entity_at(pos)

        if pos == self._new_pos:
            return self._actor
        if pos == self._original_pos:
            return None
        return self._engine.entity_at(pos)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._engine, name)


def _get_plausible_uses_of_ability_at_pos(
    actor: Entity,
    engine: "Engine",
    pos: Point,
    ability: "Ability",
    feature_evaluator: Optional["ChoiceFeatureEvaluator"],
    choice_class: type,
    **choice_kwargs,
) -> dict[tuple, PlausibleMoveAndAction]:
    plausible_uses = {}
    with _ActorMovedView(engine, actor, pos) as sim_engine:
        if ability.instructions:
            plausibly_positive = any(
                instruction.plausibly_positive for instruction in ability.instructions
            )
            plausibly_negative = any(
                instruction.plausibly_negative for instruction in ability.instructions
            )
            assert plausibly_positive or plausibly_negative
        else:  # passing
            plausibly_positive = True
            plausibly_negative = True

        raw_aimings = ability.aiming.get_all_aimings(
            engine=sim_engine, actor=actor, start_pos=pos, require_los=True
        )

        legal_aimings = sim_engine.ask(
            QueryLegalAimings(subject=actor, ability=ability, base_result=raw_aimings)
        )

        for aiming_res in legal_aimings:
            if isinstance(ability.aiming, MultipleAiming):
                all_points = set(aiming_res.target_points) | set(
                    aiming_res.included_points
                )
                if not all_points:
                    continue

                key = (pos, frozenset(all_points), ability.get_hash())
                if key not in plausible_uses:
                    plausible_uses[key] = choice_class(
                        target=None,
                        ability=ability,
                        engine=sim_engine,
                        actor=actor,
                        aiming_result=aiming_res,
                        feature_evaluator=feature_evaluator,
                        **choice_kwargs,
                    )
            elif isinstance(ability.aiming, TargetEntity) or isinstance(
                ability.aiming, TargetSelf
            ):
                # target self just targets self. Ignore aiming_res.
                key = (pos, actor.pos, ability.get_hash())
                if key not in plausible_uses:
                    plausible_uses[key] = choice_class(
                        target=actor,
                        ability=ability,
                        engine=sim_engine,
                        actor=actor,
                        aiming_result=aiming_res,
                        feature_evaluator=feature_evaluator,
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
                    frozenset(e.pos for e in affected_entities),
                    ability.get_hash(),
                )
                if key not in plausible_uses:
                    if plausibly_positive:
                        valid_targets = [
                            e for e in affected_entities if e.team == actor.team
                        ]
                    elif plausibly_negative:
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
                        engine=sim_engine,
                        actor=actor,
                        aiming_result=aiming_res,
                        feature_evaluator=feature_evaluator,
                        **choice_kwargs,
                    )

    return plausible_uses
