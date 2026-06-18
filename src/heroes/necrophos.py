from dataclasses import dataclass
from typing import TYPE_CHECKING

from aimings import (
    TargetEntity,
    TargetSelf,
    MultipleAiming,
    IncludeArea,
    is_enemy_aim_condition,
)
from areas import Burst
from engine import (
    Engine,
    Hero,
)
from modifiers import Modifier, Token, ArmorToken, StunnedToken, Armor, SlowToken
from events import (
    TurnEndEvent,
    DamageEvent,
    after,
    DeathEvent,
    before,
    TurnStartEvent,
    HealEvent,
    AddTokenEvent,
    query,
)
from abilities import (
    Ability,
    DamageInstruction,
    AddTokenInstruction,
    RefreshAbilityInstruction,
    ActionCost,
    Instruction,
    ActionContext,
    UseAnAbilityInstruction,
    AddModifierInstruction,
)
from mod_value import div, ModInt
from point import Point
from queries import QueryLegalAimings
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
class NecroGhostShroud(Token):
    text = """\
    Until the end of your next turn:
     You cannot be affected by default abilities.
     You deal +100% healing.
      You receive +1 damage."""
    valence = Valence.MIXED

    @query(QueryLegalAimings)
    def cannot_target_with_default(self, q: "QueryLegalAimings"):
        if q.ability.is_default:
            q.result = False

    @query(QueryLegalAimings)
    def avoid_inclusion_in_default(self, q: "QueryLegalAimings"):
        if q.ability.is_default:
            q.result = True

    @before(HealEvent)
    def receive_double_heal(self, event: "HealEvent"):
        event.amount.mult(2)

    @before(DamageEvent)
    def take_1_more_damage(self, event: "DamageEvent"):
        event.amount += 1

    @after(DeathEvent, only_self=False)
    def gain_kill_counter(self, event: "DeathEvent") -> None:
        if event.killer == self.owner and event.subject.max_hp >= 4:
            with self.log_trigger(event):
                AddTokenEvent(subject=self.owner, token_class=KillCounter).resolve()


@dataclass
class DeathPulse(Instruction):
    valence = Valence.MIXED

    def execute(self, ctx: ActionContext) -> None:
        for point in ctx.included_points:
            entity = ctx.engine.entity_at(point)
            if entity.team == ctx.source.team:
                HealEvent(subject=entity, amount=1)
            else:
                DamageEvent(source=ctx.source, subject=entity, amount=1)


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
                name="Ghost Shroad",
                text="""\
        1/Game, Instant +3
Until the end of your next turn:
  You cannot be affected by default abilities.
  You deal +100% healing.
  You receive +1 damage..""",
                aiming=TargetSelf(),
                instructions=[
                    AddModifierInstruction(
                        aiming_name="self_target", modifier_class=GhostShroudToken
                    ),
                ],
                owner=self,
                action_cost=ActionCost.FREE,
            )
        )

        self.abilities.append(
            Ability(
                name="Battle Hunger",
                text="""\
                1/Game:
        Range 3, give the 2 DoT and a Battle Hunger token:
          When they kill a unit, they lose the token and clear all DoT.
                """,
                aiming=TargetEntity(in_range=3),
                instructions=[
                    AddTokenInstruction(token_class=SlowToken),
                    AddTokenInstruction(
                        token_class=DamageOverTimeToken,
                        amount=2,
                    ),
                    AddTokenInstruction(token_class=BattleHungerToken),
                ],
                max_charges=1,
                owner=self,
            )
        )
        self.abilities.append(
            Ability(
                name="Culling Blade",
                text="""\
                1/Game
        Range 1, 3dmg irreducible
        On kill:
          The target does not trigger any on-death reactions.
          Refresh this.
          If the kill was a hero, for the rest of the game you have Armor.
                """,
                aiming=TargetEntity(in_range=1),
                instructions=[CullingBladeInstruction()],
                is_ultimate=True,
                max_charges=1,
                owner=self,
            )
        )
