from aimings import TargetEntity, MultipleAiming
from areas import Burst
from engine import (
    Engine,
    Hero,
    query,
)
from modifiers import Modifier
from queries import QueryDefense
from events import DeathEvent, after, HealEvent, TurnStartEvent, PullEvent
from abilities import (
    Ability,
    DamageInstruction,
    Instruction,
    ActionContext,
)
from point import Point


class OnFirstTurnSpawnOtherViktoria(Modifier):
    text = "Deploy: Create a copy of this in your deploy zone, without this ability."

    @after(TurnStartEvent)
    def spawn_viktoria(self, event: TurnStartEvent):
        if hasattr(event.subject, "is_original") and event.subject.is_original:
            pass
            # todo choose adjacent space
            #  create viktoria with is_original=False


class OnStartOfTurnMayTeleportAnotherViktoriaHereThenTeleport1(Modifier):
    text = "Start of turn: Another Viktoria in range 4 may teleport adjacent to this. Teleport 1."

    @after(TurnStartEvent)
    def start_of_turn(self, event: TurnStartEvent):
        pass  # get other viktorias, they can choose to teleport to any space in burst1. Then you can choose to teleport burst 1.


class OnKillAllViktoriasHeal(Modifier):
    @after(DeathEvent, only_self=False)
    def on_kill(self, event: DeathEvent):
        if event.killer == self.owner:
            for entity in self.owner.engine.living_entities:
                if entity.name == "Viktoria":
                    HealEvent(subject=entity, amount=2).resolve()


class DefenseModifier(Modifier):
    def __init__(self, owner, amount):
        super().__init__(owner)
        self.amount = amount

    @query(QueryDefense)
    def modify_defense(self, q: QueryDefense):
        q.result += self.amount


class OnDeathOtherViktoriasHealAndGainDef(Modifier):
    @after(DeathEvent)
    def on_death(self):
        for entity in self.owner.engine.living_entities:
            if entity.name == "Viktoria" and entity != self.owner:
                HealEvent(subject=entity, amount=2).resolve()
                self.owner.add_modifier(DefenseModifier(owner=entity, amount=2))


class DragonsBreathPull(Instruction):
    def __post__init__(self):
        self.plausibly_negative = True

    def execute(self, ctx: ActionContext) -> None:
        if not ctx.target or not hasattr(ctx.target, "hp"):
            return
        burst_4_area = ctx.engine.grid.get_points_in_range(
            start=ctx.target_point, max_range=4
        )
        viktorias_in_range = []
        for point in burst_4_area:
            entity = ctx.engine.entity_at(point)
            if entity and entity.name == "Viktoria":
                viktorias_in_range.append(entity)
        for viktoria in viktorias_in_range:
            PullEvent(viktoria, distance=4, toward_point=ctx.target_point)


class Viktoria(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int, is_original=True):
        self.is_original = is_original
        super().__init__(
            engine=engine, name="Viktoria", hp=6, speed=3, pos=pos, team=team
        )
        self.add_modifier(OnFirstTurnSpawnOtherViktoria())
        self.add_modifier(OnKillAllViktoriasHeal())
        self.add_modifier(OnDeathOtherViktoriasHealAndGainDef())

        self.abilities.append(
            Ability(
                name="Enchanted Katana",
                text="Range 1, 2dmg +2Crit. Other enemies in burst 1, 1dmg",
                aiming=MultipleAiming(
                    {"target": TargetEntity(in_range=1), "burst": Burst(radius=1)}
                ),  # todo, how to do "all in burst except target
                instructions=[
                    DamageInstruction(aiming_name="target", amount=2),
                    DamageInstruction(aiming_name="burst", amount=1),
                    # todo check no crit or miss on aoe. Included, not target.
                ],
                crit_chance=2,
                is_default=True,
                owner=self,
            )
        )
        self.abilities.append(
            Ability(
                name="Dragon's Breath",
                text="Target enemy in range 4. All Viktorias in range 4 of the target pull 4 towards it.",
                aiming=TargetEntity(in_range=4),
                instructions=[DragonsBreathPull()],
            )
        )
        # todo dragonsbreath
