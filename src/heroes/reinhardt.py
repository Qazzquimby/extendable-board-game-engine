from dataclasses import dataclass
from typing import Iterator, Set

from abilities import (
    Ability,
    ActionCost,
)
from instruction_library import (
    DamageInstruction,
    AddTokenInstruction,
    ApplyModifierInstruction,
)
from aimings import IncludeArea
from areas import Square, PathArea, Line
from engine import (
    Immobile,
    Engine,
    Hero,
    before,
    ImmobileToken,
    ActionContext,
    Instruction,
)
from modifiers import Modifier
from event_library import PushEvent, PullEvent, DamageEvent
from grid import Grid
from point import Point


class PathAllInRangeArea(PathArea):
    def __init__(
        self,
        length: int,
        in_range: int = 0,
    ):
        super().__init__(length=length, in_range=in_range)

    def get_selections(self, grid: Grid, start: Point) -> Iterator[Set[Point]]:
        unlimited_selections = super().get_selections(grid=grid, start=start)

        points_in_range_1 = grid.get_points_in_range(
            start=start, max_range=self.in_range
        )
        for selection in unlimited_selections:
            if all([point in points_in_range_1 for point in selection]):
                yield selection


@dataclass
class ChargeInstruction(Instruction):
    def execute(self, ctx: ActionContext) -> None:
        first_enemy = None
        last_point = ctx.source.pos

        # todo
        #  Everything technically targets a point.
        #  need to be able to efficiently get content of point.
        #  Need easy guard against two entities being in same point (markers are not limited that way).
        #  It's usually more convenient to treat targets as entities since its usually immediately resolved.
        #  Don't want to need an expensive lookup many times during event handling.

        # todo
        #  For each space, check if there's a collision. The first collided entity is pushed along with you.
        #  For each space that you or the collided entity is pushed into, try to push its content to the side (choose randomly if both are unoccupied).
        #  If any space cannot be emptied, stop.
        #  The below is teleporting to the end of the range and does nothing to prevent ending on top of another entity.

        path = [ctx.source.pos] + ctx.included_points
        last_point = path[-1]
        second_last_point = path[-2]

        for point in ctx.included_points:
            entity = ctx.engine.entity_at(point)
            if not entity:
                continue
            if not first_enemy:
                first_enemy = entity
                DamageEvent(
                    engine=ctx.engine,
                    source=ctx.source,
                    subject=entity,
                    amount=6,
                    ability=ctx.ability,
                ).resolve()
                AddTokenInstruction(token_class=ImmobileToken).execute(ctx=ctx)
                entity.pos = last_point
            else:
                DamageEvent(
                    engine=ctx.engine,
                    source=ctx.source,
                    subject=entity,
                    amount=1,
                    ability=ctx.ability,
                ).resolve()

        if first_enemy:
            ctx.source.pos = second_last_point
        else:
            ctx.source.pos = last_point


class CannotBePushedOrPulled(Modifier):
    @before(PushEvent)
    def prevent_movement(self, engine: "Engine", event):
        event.canceled = True

    @before(PullEvent)
    def prevent_movement(self, engine: "Engine", event):
        event.canceled = True


class Reinhardt(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Reinhardt", hp=12, speed=3, pos=pos, team=team
        )

        self.add_modifier(CannotBePushedOrPulled())

        self.abilities.append(
            Ability(
                name="Rocket Hammer",
                aiming=IncludeArea(
                    area=PathAllInRangeArea(
                        length=3,
                        in_range=1,
                    )
                ),
                instructions=[DamageInstruction(amount=2)],
                is_default=True,
                owner_id=self.id,
            )
        )
        self.abilities.append(
            Ability(
                name="Charge",
                aiming=IncludeArea(area=Line(length=99, in_range=0)),
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
                max_charges=1,
                owner_id=self.id,
            )
        )
