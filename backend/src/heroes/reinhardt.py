"""
Reinhardt — heavy tank with charge and barrier shield.

Shield: placed on the edge in front of Reinhardt, blocks enemy LOS.
Moves with Reinhardt along the Y axis.
Entities positioned behind the shield benefit from cover.
"""

from dataclasses import dataclass
from typing import Iterator, Set

from abilities import (
    Ability,
    ActionCost,
)
from valence import Valence
from instruction_library import (
    DamageInstruction,
    AddTokenInstruction,
    ApplyModifierInstruction,
)
from aimings import IncludeArea, TargetSelf
from areas import Square, PathArea, Line
from engine import Engine
from entities import Hero, Marker
from events import before, after
from modifiers import Immobile, ImmobileToken, Modifier
from abilities import ActionContext, Instruction

from event_library import PushEvent, PullEvent, DamageEvent, ChangeLocationEvent
from grid import Grid, Direction
from point import Point


class PathAllInRangeArea(PathArea):
    def __init__(self, length: int, in_range: int = 0):
        super().__init__(length=length, in_range=in_range)

    def get_selections(self, grid: Grid, start: Point) -> Iterator[Set[Point]]:
        unlimited_selections = super().get_selections(grid=grid, start=start)
        points_in_range_1 = grid.get_points_in_range(
            start=start, max_range=self.in_range
        )
        for selection in unlimited_selections:
            if all([point in points_in_range_1 for point in selection]):
                yield selection


@dataclass(kw_only=True)
class ChargeInstruction(Instruction):
    valence: Valence = Valence.BAD

    def score(self, engine, actor, target, ctx) -> float:
        if target.team == actor.team:
            return 0.0
        from abilities import score_damage
        return score_damage(6, target.hp)

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        source = engine.get_entity_by_id(ctx.source_id)
        if not source:
            return
        path_points = list(ctx.included_points)
        if not path_points:
            return

        # Find first enemy in path
        first_enemy = None
        first_enemy_idx = -1
        for i, pt in enumerate(path_points):
            entity = engine.entity_at(pt)
            if entity and entity != source:
                first_enemy = entity
                first_enemy_idx = i
                break

        if first_enemy:
            engine.event_queue.enqueue(
                DamageEvent(source=source, subject=first_enemy, amount=6)
            )
            # Push first enemy to end of path (last empty cell)
            dest_idx = len(path_points) - 1
            while dest_idx >= 0 and engine.entity_at(path_points[dest_idx]):
                dest_idx -= 1
            if dest_idx >= 0:
                first_enemy.pos = path_points[dest_idx]
                engine.event_queue.enqueue(
                    ChangeLocationEvent(subject=first_enemy, new_pos=path_points[dest_idx])
                )
            # Reinhardt moves to just behind the enemy's starting position
            rein_pos = path_points[max(0, first_enemy_idx - 1)]
            source.pos = rein_pos
            engine.event_queue.enqueue(
                ChangeLocationEvent(subject=source, new_pos=rein_pos)
            )
        else:
            source.pos = path_points[-1]
            engine.event_queue.enqueue(
                ChangeLocationEvent(subject=source, new_pos=path_points[-1])
            )


class CannotBePushedOrPulled(Modifier):
    @before(PushEvent)
    def prevent_movement(self, engine: "Engine", event):
        event.canceled = True

    @before(PullEvent)
    def prevent_movement(self, engine: "Engine", event):
        event.canceled = True


# ── Barrier Shield ──

@dataclass(kw_only=True)
class BarrierShieldModifier(Modifier):
    """Blocks LOS for enemies. The shield sits on the edge in front of Reinhardt."""

    valence = Valence.GOOD

    def blocks_los_for(self, engine: "Engine", viewer: "Entity") -> bool:
        owner = engine.get_entity_by_id(self.owner_id)
        if not owner:
            return False
        # Find Reinhardt (the modifier's owner is the marker, we need Reinhardt)
        rein = None
        for e in engine.entities:
            if isinstance(e, Reinhardt) and hasattr(e, 'shield_marker') and e.shield_marker.id == self.owner_id:
                rein = e
                break
        if rein and viewer.team != rein.team:
            return True
        return False


class Reinhardt(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Reinhardt", hp=12, speed=3, pos=pos, team=team
        )

        self.add_modifier(engine, CannotBePushedOrPulled())

        # Create barrier shield marker on the left edge (team 0 defends left)
        edge_x = 0 if team == 0 else (engine.grid.width - 1)
        shield_pos = Point(edge_x, pos.y)
        self.shield_marker = Marker(
            engine=engine,
            name=f"{'Allies' if team == 0 else 'Enemies'}_Barrier",
            pos=shield_pos,
            team=team,
            summoner_id=self.id,
        )
        shield_mod = BarrierShieldModifier()
        self.shield_marker.modifiers.append(shield_mod)
        shield_mod.owner_id = self.shield_marker.id
        engine.router.subscribe(shield_mod)

        self.abilities.append(
            Ability(
                name="Rocket Hammer",
                aiming=IncludeArea(
                    area=PathAllInRangeArea(length=3, in_range=1),
                ),
                instructions=[DamageInstruction(amount=2)],
                is_default=True,
                owner_id=self.id,
            )
        )
        self.abilities.append(
            Ability(
                name="Charge",
                aiming=IncludeArea(area=Line(length=6, in_range=0)),
                instructions=[ChargeInstruction()],
                action_cost=ActionCost.MOVE_AND_STANDARD,
                max_charges=1,
                owner_id=self.id,
            )
        )
        self.abilities.append(
            Ability(
                name="Fire Strike",
                aiming=IncludeArea(area=Line(length=99)),
                instructions=[DamageInstruction(amount=3)],
                taps=True,
                owner_id=self.id,
            )
        )
        self.abilities.append(
            Ability(
                name="Earthshatter",
                aiming=IncludeArea(area=Square(side_length=3, in_range=2)),
                instructions=[ApplyModifierInstruction(modifier_class=Immobile)],
                is_ultimate=True,
                ultimate_turn=4,
                owner_id=self.id,
            )
        )

    def start_turn(self):
        super().start_turn()
        # Move shield marker to track Reinhardt's Y position
        if self.pos and self.shield_marker and self.shield_marker.pos is not None:
            edge_x = self.shield_marker.pos.x
            new_pos = Point(edge_x, self.pos.y)
            self.shield_marker.pos = new_pos
