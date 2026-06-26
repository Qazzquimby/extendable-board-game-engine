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
    def take_damage(self, event: TurnEndEvent) -> None:
        with self.log_trigger(event):
            DamageEvent(source=None, subject=self.owner, amount=self.amount).resolve()


class KillCounter(Token):
    valence = Valence.GOOD


@dataclass(kw_only=True)
class NecroStartTurnAura(Modifier):
    text = "Start of turn: Enemies in Burst 3, irreducible 1dmg + 1dmg per 2 Kill counters. Heal 1 per Kill counter"
    valence = Valence.GOOD

    @after(TurnStartEvent)
    def aura(self, event: "TurnStartEvent") -> None:
        num_kill_counters = event.subject.get_token_count(KillCounter)
        with self.log_trigger(event):
            points_in_range = self.owner.engine.grid.get_points_in_range(
                start=self.owner.pos, max_range=3
            )
            enemies_in_range = []
            allies_in_range = []
            for entity in self.owner.engine.living_entities:
                if entity.pos in points_in_range:
                    if entity.team == event.subject.team:
                        allies_in_range.append(entity)
                    else:
                        enemies_in_range.append(entity)

            for enemy in enemies_in_range:
                DamageEvent(
                    source=event.subject,
                    subject=enemy,
                    amount=ModInt(1 + num_kill_counters // 2, is_irreducible=True),
                ).resolve()
            for ally in allies_in_range:
                HealEvent(subject=ally, amount=ModInt(num_kill_counters))


@dataclass(kw_only=True)
class NecroGetKillCounter(Modifier):
    text = "On killing a unit with 4 or more max health, gain a Kill Counter"
    valence = Valence.GOOD

    @after(DeathEvent, only_self=False)
    def gain_kill_counter(self, event: "DeathEvent") -> None:
        if event.killer == self.owner and event.subject.max_hp >= 4:
            with self.log_trigger(event):
                AddTokenEvent(subject=self.owner, token_class=KillCounter).resolve()


@dataclass(kw_only=True)
class NecroGhostShroud(Modifier):
    text = """\
    Until the end of your next turn:
     You cannot be affected by default abilities.
     You deal +100% healing.
      You receive +1 damage."""
    valence = Valence.MIXED

    @query(QueryLegalAimings)
    def cannot_target_with_default(self, q: "QueryLegalAimings"):
        if q.ability.is_default:
            legal_aimings = [
                aiming
                for aiming in q.result
                if self.owner.pos not in aiming.target_points
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

    def execute(self, ctx: ActionContext) -> None:
        for point in ctx.included_points:
            entity = ctx.engine.entity_at(point)
            if entity:
                if entity.team == ctx.source.team:
                    HealEvent(subject=entity, amount=1)
                else:
                    DamageEvent(source=ctx.source, subject=entity, amount=1)


@dataclass
class NecroTeleportAdjacentInstruction(Instruction):
    valence = Valence.MIXED

    def execute(self, ctx: ActionContext) -> None:
        points_adjacent = ctx.engine.grid.get_points_in_range(
            start=ctx.target.pos, max_range=1
        )
        if points_adjacent:
            ChangeLocationEvent(subject=ctx.source, new_pos=list(points_adjacent)[0])


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

        self.add_modifier(NecroStartTurnAura())
        self.add_modifier(NecroGetKillCounter())

        self.abilities.append(
            Ability(
                name="Death Pulse",
                text="Enemies in burst 3, 1dmg. You and allies in burst 3, heal 1.",
                aiming=IncludeArea(area=Burst(radius=3)),
                instructions=[DeathPulse()],
                is_default=True,
                owner=self,
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
                owner=self,
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
                owner=self,
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
