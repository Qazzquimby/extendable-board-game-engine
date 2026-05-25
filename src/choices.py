from typing import List, Optional, Dict

from abilities import Ability, HealInstruction, DamageInstruction
from aimings import TargetEntity, IncludeArea
from engine import Engine
from entities import Entity
from point import Point
from queries import QueryLegalAimings


class Choice:
    def __init__(self, features: Dict[str, float]):
        self.features = features


class PlausibleMoveAndAction(Choice):
    def __init__(
        self,
        move_pos: Point,
        target: Optional["Entity"],
        ability: "Ability",
        movement_name: str = "",
    ):
        # todo right now aoe uses target None.
        #  Probably better to have a list of targets. Ml will need adjusting
        self.move_pos = move_pos
        self.target = target
        self.ability = ability
        self.movement_name = movement_name

        features = {} # todo we basically want to go through all instructions. Each instructions has features. Sum the features. Summing logic may vary per instruction. State context is needed to determine features, eg which is the target of the instruction.
        super().__init__(features=features)


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
    engine: Engine,
    move_pos: Point,
    movement_name: str,
    ability: "Ability",
) -> dict[tuple, PlausibleMoveAndAction]:
    plausible_uses_of_ability_after_movement = {}
    is_positive = any(instruction.is_negative for instruction in ability.instructions)
    is_negative = any(instruction.is_positive for instruction in ability.instructions)

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
                    not is_positive
                    and target.team == actor.team
                    and isinstance(ability.aiming, TargetEntity)
                ):
                    continue
                if (
                    not is_negative
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
                if is_positive:
                    valid_targets = [
                        e for e in affected_entities if e.team == actor.team
                    ]
                elif is_negative:
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
                )

    return plausible_uses_of_ability_after_movement
