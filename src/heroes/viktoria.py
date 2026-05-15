from dataclasses import dataclass

from aimings import TargetEntity
from engine import (
    Engine,
    Hero,
    Modifier,
    after,
    HealEvent,
    query,
    ActionContext,
    Instruction,
)
from queries import QueryDefense
from events import DeathEvent
from abilities import (
    Ability,
    DamageInstruction,
)
from point import Point


class AllViktoriasHealWhenAnyViktoriaKills(Modifier):
    @after(DeathEvent, only_self=False)
    def on_kill(self, event: DeathEvent):
        if event.killer == self.owner:
            for entity in self.owner.engine.living_entities:
                if entity.name == "Viktoria":
                    HealEvent(self.owner.engine, subject=entity, amount=2).resolve()


class DefenseModifier(Modifier):
    def __init__(self, owner, amount):
        super().__init__(owner)
        self.amount = amount

    @query(QueryDefense)
    def modify_defense(self, q: QueryDefense):
        q.result += self.amount


class OtherViktoriasHealAndGain2DefWhenAnyViktoriaDies(Modifier):
    @after(DeathEvent)
    def on_death(self):
        for entity in self.owner.engine.living_entities:
            if entity.name == "Viktoria" and entity != self.owner:
                HealEvent(self.owner.engine, subject=entity, amount=2).resolve()
                self.owner.add_modifier(DefenseModifier(owner=entity, amount=2))


@dataclass
class KatanaBurstInstruction(Instruction):
    def execute(self, ctx: ActionContext) -> None:
        from events import DamageEvent

        if not ctx.target or not hasattr(ctx.target, "pos"):
            return
        points_in_range = ctx.engine.grid.get_points_in_range(
            start=ctx.target.pos, max_range=1
        )
        for entity in ctx.engine.living_entities:
            if (
                entity != ctx.target
                and entity.team != ctx.source.team
                and entity.pos in points_in_range
            ):
                DamageEvent(
                    ctx.engine, source=ctx.source, subject=entity, amount=1
                ).resolve()


class Viktoria(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Viktoria", hp=6, speed=3, pos=pos, team=team
        )
        self.add_modifier(AllViktoriasHealWhenAnyViktoriaKills())
        self.add_modifier(OtherViktoriasHealAndGain2DefWhenAnyViktoriaDies())

        self.abilities.append(
            Ability(
                name="Enchanted Katana",
                aiming=TargetEntity(in_range=1),
                instructions=[DamageInstruction(amount=2), KatanaBurstInstruction()],
                crit_chance=2,
                is_default=True,
                owner=self,
            )
        )
