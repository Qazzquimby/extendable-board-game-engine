from typing import List, Optional, Dict, Any, TYPE_CHECKING

from abilities import Ability, ActionContext
from aimings import TargetEntity, IncludeArea, TargetSelf, AimingResult
from entities import Entity
from point import Point
from queries import QueryLegalAimings

if TYPE_CHECKING:
    from engine import Engine


class Choice:
    def __init__(self, features: Dict[str, Any]):
        self.features = features


class PlausibleMoveAndAction(Choice):
    def __init__(
        self,
        move_pos: Point,
        target: Optional["Entity"],
        ability: "Ability",
        movement_name: str = "",
        engine: "Engine" = None,
        actor: "Entity" = None,
        aiming_result: "AimingResult" = None,
    ):
        # todo right now aoe uses target None.
        #  Probably better to have a list of targets. Ml will need adjusting
        self.move_pos = move_pos
        self.target = target
        self.ability = ability
        self.movement_name = movement_name
        self.aiming_result = aiming_result

        features = (
            self._compute_features(actor, engine)
            if engine and actor and aiming_result
            else {}
        )
        super().__init__(features=features)

    def _compute_features(self, actor: "Entity", engine: "Engine") -> Dict[str, Any]:
        features = {f"new_location_{actor.name}_{actor.id}": self.move_pos}
        if self.move_pos != actor.pos:
            features[f"moved_{actor.name}_{actor.id}"] = True

        all_points = set(self.aiming_result.target_points) | set(
            self.aiming_result.included_points
        )

        for instruction in self.ability.instructions:
            for point in all_points:
                ctx = ActionContext(
                    engine=engine,
                    source=actor,
                    subject_point=point,
                    target_points=self.aiming_result.target_points,
                    included_points=self.aiming_result.included_points,
                    ability=self.ability,
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
            new_pos_key = f"new_location_{entity.name}_{entity.id}"
            entity_pos = features.get(new_pos_key, entity.pos)
            if not entity_pos:
                continue

            for other_entity in engine.entities:
                if entity.id >= other_entity.id:
                    continue

                other_pos_key = f"new_location_{other_entity.name}_{other_entity.id}"
                other_pos = features.get(other_pos_key, other_entity.pos)
                if not other_pos:
                    continue

                dist = engine.grid.get_path(start=entity.pos, target=other_pos)
                key = f"distance_{entity.name}_{entity.id}_to_{other_entity.name}_{other_entity.id}"
                features[key] = dist

        return features


def get_plausible_move_and_actions(
    actor: "Entity", engine: "Engine"
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
                    attack_range = ability.aiming.area.in_range

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
    actor: "Entity", engine: "Engine", move_pos: Point, movement_name: str
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
            )
        )
        plausible_actions_after_movement.update(
            plausible_uses_of_ability_after_movement
        )
    return plausible_actions_after_movement


def get_plausible_uses_of_ability_after_movement(
    actor: Entity,
    engine: "Engine",
    move_pos: Point,
    movement_name: str,
    ability: "Ability",
) -> dict[tuple, PlausibleMoveAndAction]:
    plausible_uses_of_ability_after_movement = {}
    plausibly_positive = any(
        instruction.plausibly_positive for instruction in ability.instructions
    )
    plausibly_negative = any(
        instruction.plausibly_negative for instruction in ability.instructions
    )

    raw_aimings = ability.aiming.get_all_aimings(
        engine=engine, actor=actor, start_pos=move_pos, require_los=True
    )

    legal_aimings = engine.ask(
        QueryLegalAimings(subject=actor, ability=ability, result=raw_aimings)
    )

    for aiming_res in legal_aimings:
        if isinstance(ability.aiming, TargetEntity) or isinstance(
            ability.aiming, TargetSelf
        ):
            for t_point in aiming_res.target_points:
                target = engine.entity_at(t_point)
                if not target:
                    continue
                if isinstance(ability.aiming, TargetEntity) and target == actor:
                    continue
                if (
                    not plausibly_positive
                    and target.team == actor.team
                    and isinstance(ability.aiming, TargetEntity)
                ):
                    continue
                if (
                    not plausibly_negative
                    and target.team != actor.team
                    and isinstance(ability.aiming, TargetEntity)
                ):
                    continue

                key = (move_pos, t_point, ability.get_hash())
                if key not in plausible_uses_of_ability_after_movement:
                    plausible_uses_of_ability_after_movement[key] = (
                        PlausibleMoveAndAction(
                            move_pos=move_pos,
                            target=target,
                            ability=ability,
                            movement_name=movement_name,
                            engine=engine,
                            actor=actor,
                            aiming_result=aiming_res,
                        )
                    )
        elif isinstance(ability.aiming, IncludeArea):
            affected_entities = {
                e for e in engine.entities if e.pos in aiming_res.included_points
            }
            if not affected_entities:
                continue

            key = (
                move_pos,
                frozenset(e.pos for e in affected_entities),
                ability.get_hash(),
            )
            if key not in plausible_uses_of_ability_after_movement:
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

                plausible_uses_of_ability_after_movement[key] = PlausibleMoveAndAction(
                    move_pos=move_pos,
                    target=None,
                    ability=ability,
                    movement_name=movement_name,
                    engine=engine,
                    actor=actor,
                    aiming_result=aiming_res,
                )

    return plausible_uses_of_ability_after_movement
