from dataclasses import dataclass

from aimings import (
    TargetEntity,
    TargetSelf,
    IncludeArea,
    is_enemy_aim_condition,
)
from areas import Burst
from engine import (
    Engine,
    Hero,
)
from entities import Entity
from modifiers import Modifier, Token, ImmobileToken
from events import (
    after,
    before,
    query,
)
from event_library import (
    ChangeLocationEvent,
    TurnStartEvent,
    TurnEndEvent,
    DamageEvent,
    DeathEvent,
    HealEvent,
    AddTokenEvent,
)
from abilities import (
    Ability,
    ActionCost,
    Instruction,
    ActionContext,
    UseAnAbilityInstruction,
    AddModifierInstruction,
    AddTokenInstruction,
)
from mod_value import ModInt
from point import Point
from queries import QueryLegalAimings, QueryAvoidInclusion
from valence import Valence


class DamageOverTimeToken(Token):
    valence = Valence.BAD

    @before(TurnEndEvent)
    def take_damage(self, engine: "Engine", event: TurnEndEvent) -> None:
        with self.log_trigger(engine=engine, event=event):
            owner = engine.get_entity_by_id(self.owner_id)
            engine.event_queue.enqueue(
                DamageEvent(source=None, subject=owner, amount=self.amount)
            )


class KillCounter(Token):
    valence = Valence.GOOD


@dataclass(kw_only=True)
class NecroStartTurnAura(Modifier):
    text = "Start of turn: Enemies in Burst 3, irreducible 1dmg + 1dmg per 2 Kill counters. Heal 1 per Kill counter"
    valence = Valence.GOOD

    @after(TurnStartEvent)
    def aura(self, engine: "Engine", event: "TurnStartEvent") -> None:
        subject = engine.get_entity_by_id(event.subject_id)
        num_kill_counters = subject.get_token_count(
            engine=engine, token_class=KillCounter
        )
        with self.log_trigger(engine=engine, event=event):
            owner = engine.get_entity_by_id(self.owner_id)
            points_in_range = engine.grid.get_points_in_range(
                start=owner.pos, max_range=3
            )
            enemies_in_range = []
            allies_in_range = []
            for entity in engine.living_entities:
                if entity.pos in points_in_range:
                    if entity.team == subject.team:
                        allies_in_range.append(entity)
                    else:
                        enemies_in_range.append(entity)

            for enemy in enemies_in_range:
                engine.event_queue.enqueue(
                    DamageEvent(
                        source=subject,
                        subject=enemy,
                        amount=ModInt(1 + num_kill_counters // 2, is_irreducible=True),
                    )
                )
            for ally in allies_in_range:
                HealEvent(subject=ally, amount=ModInt(num_kill_counters))


@dataclass(kw_only=True)
class NecroGetKillCounter(Modifier):
    text = "On killing a unit with 4 or more max health, gain a Kill Counter"
    valence = Valence.GOOD

    @after(DeathEvent, only_self=False)
    def gain_kill_counter(self, engine: "Engine", event: "DeathEvent") -> None:
        if event.killer_id == self.owner_id:
            subject = engine.get_entity_by_id(event.subject_id)
            if subject.max_hp >= 4:
                with self.log_trigger(engine=engine, event=event):
                    owner = engine.get_entity_by_id(self.owner_id)
                    engine.event_queue.enqueue(
                        AddTokenEvent(subject=owner, token_class=KillCounter)
                    )


@dataclass(kw_only=True)
class NecroGhostShroud(Modifier):
    text = """\
    Until the end of your next turn:
     You cannot be affected by default abilities.
     You deal +100% healing.
      You receive +1 damage."""
    valence = Valence.MIXED

    @query(QueryLegalAimings)
    def cannot_target_with_default(self, engine: "Engine", q: "QueryLegalAimings"):
        owner = engine.get_entity_by_id(self.owner_id)
        if q.ability.is_default:
            legal_aimings = [
                aiming for aiming in q.result if owner.pos not in aiming.target_points
            ]
            q.result = legal_aimings

    @query(QueryAvoidInclusion)
    def avoid_inclusion_in_default(self, q: "QueryAvoidInclusion"):
        if q.ability.is_default:
            q.result = True

    @before(HealEvent)
    def receive_double_heal(self, event: "HealEvent"):
        event.amount.mult(2)

    @before(DamageEvent)
    def take_1_more_damage(self, event: "DamageEvent"):
        event.amount.add(1)  # seems like a query


@dataclass
class DeathPulse(Instruction):
    valence = Valence.MIXED

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        for point in ctx.included_points:
            entity = engine.entity_at(point)
            if entity:
                source = engine.get_entity_by_id(ctx.source_id)
                if entity.team == source.team:
                    HealEvent(subject=entity, amount=1)
                else:
                    DamageEvent(source=source, subject=entity, amount=1)


@dataclass
class NecroTeleportAdjacentInstruction(Instruction):
    valence = Valence.MIXED

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        target = ctx.get_target(engine)
        if target:
            points_adjacent = engine.grid.get_points_in_range(
                start=target.pos, max_range=1
            )
            if points_adjacent:
                source = engine.get_entity_by_id(ctx.source_id)
                ChangeLocationEvent(subject=source, new_pos=list(points_adjacent)[0])


@dataclass(kw_only=True)
class ReapersScythe(Token):
    source: "Entity"
    text = """\
    At the start of their next turn, the caster deals irreducible damage to you equal to your missing health. On kill, they gain 2 additional Kill counters."""
    valence = Valence.BAD

    @after(TurnStartEvent)
    def trigger(self, q: "TurnStartEvent"):
        pass


class Necrophos(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Necrophos", hp=8, speed=3, pos=pos, team=team
        )

        self.add_modifier(engine, NecroStartTurnAura())
        self.add_modifier(engine, NecroGetKillCounter())

        self.abilities.append(
            Ability(
                name="Death Pulse",
                text="Enemies in burst 3, 1dmg. You and allies in burst 3, heal 1.",
                aiming=IncludeArea(area=Burst(radius=3)),
                instructions=[DeathPulse()],
                is_default=True,
                owner_id=self.id,
            )
        )

        self.abilities.append(
            Ability(
                name="Ghost Shroud",
                text="""\
        1/Game, Instant +3
Until the end of your next turn:
  You cannot be affected by default abilities.
  You deal +100% healing.
  You receive +1 damage..""",
                aiming=TargetSelf(),
                instructions=[
                    AddModifierInstruction(modifier_class=NecroGhostShroud),
                ],
                owner_id=self.id,
                action_cost=ActionCost.INSTANT,
                instant_speed=3,
                max_charges=1,
            )
        )

        self.abilities.append(
            Ability(
                name="Death Seeker",
                text="""\
               1/Game
Teleport to a space adjacent to an enemy in range 3.
Use a default ability.
                """,
                aiming=TargetEntity(in_range=3, condition=is_enemy_aim_condition),
                instructions=[
                    NecroTeleportAdjacentInstruction(),
                    UseAnAbilityInstruction(default_only=True),
                ],
                max_charges=1,
                owner_id=self.id,
            )
        )

        self.abilities.append(
            Ability(
                name="Reaper's Scythe",
                text="""\
                1/Game
Range 3, immobilize.
At the start of your next turn, deal irreducible damage the target equal to their missing health.
On kill, gain 2 additional Kill counters.
                """,
                aiming=TargetEntity(in_range=3),
                instructions=[
                    AddTokenInstruction(
                        token_class=ImmobileToken,
                    ),
                    AddTokenInstruction(
                        token_class=ReapersScythe, token_kwargs={"source": self}
                    ),
                ],
            )
        )
