from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

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
from modifiers import Modifier, Token, ArmorToken, StunnedToken, Armor
from events import TurnEndEvent, DamageEvent, after, DeathEvent, before
from abilities import (
    Ability,
    DamageInstruction,
    GiveTokenInstruction,
    RefreshAbilityInstruction,
    ActionCost,
    Instruction,
    ActionContext,
    UseAnAbilityInstruction,
)
from mod_value import div
from point import Point

if TYPE_CHECKING:
    from entities import Entity


class DamageOverTimeToken(Token):
    @before(TurnEndEvent)
    def take_damage(self, event: TurnEndEvent) -> None:
        DamageEvent(source=None, subject=self.owner, amount=self.amount).resolve()


class BattleHungerToken(Token):
    # (todo later) Moving away from Axe costs you twice as many spaces.

    @after(DeathEvent)
    def on_kill_clear_this_and_DoT(
        self, engine: "Engine", subject: "Entity", killer: Optional["Entity"] = None
    ) -> None:
        if killer == self.owner and isinstance(subject, Hero):
            self.owner.remove_token(BattleHungerToken)
            self.owner.remove_token(DamageOverTimeToken, amount=99)


@dataclass
class CullingBladeInstruction(Instruction):
    def __post_init__(self):
        self.plausibly_negative = True

    def execute(self, ctx: ActionContext) -> None:
        if not hasattr(ctx.target, "hp"):
            return
        event = DamageEvent(
            source=ctx.source,
            subject=ctx.target,
            amount=3,
            ability=ctx.ability,
        )
        event.amount.is_irreducible = True
        event.resolve()
        if ctx.target.hp <= 0:
            RefreshAbilityInstruction().execute(ctx)
            if ctx.ability and ctx.ability.charges is not None:
                ctx.ability.charges += 1
            if isinstance(ctx.target, Hero):
                ctx.source.add_modifier(Armor())


class AxeCleaveOnTakeDamage(Modifier):

    def __post_init__(self):
        self.plausibly_positive = True

    # - name: Receive damage
    #   text: |-
    #     Enemies in burst 1, 1dmg
    @after(DamageEvent)
    def burst_damage(self, event: "DamageEvent") -> None:
        if event.amount > 0:
            points_in_range = self.owner.engine.grid.get_points_in_range(
                start=self.owner.pos, max_range=1
            )
            for entity in self.owner.engine.living_entities:
                if entity.team != self.owner.team and entity.pos in points_in_range:
                    DamageEvent(source=self.owner, subject=entity, amount=1).resolve()


class AxeReflectHalfOfDamageFromDefaults(Modifier):
    def __post_init__(self):
        self.plausibly_positive = True

    #       name: Receive damage from a Default Ability
    #       text: The attacker takes 1/2 the damage received, before Armor.
    @before(DamageEvent)
    def reflect_default_damage(self, event: "DamageEvent") -> None:
        if event.ability and event.ability.is_default and event.source:
            reflect_amt = div(event.amount.value, 2)
            if reflect_amt > 0:
                DamageEvent(
                    source=self.owner,
                    subject=event.source,
                    amount=reflect_amt,
                ).resolve()


class Axe(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(engine=engine, name="Axe", hp=10, speed=3, pos=pos, team=team)

        self.add_modifier(AxeCleaveOnTakeDamage())
        self.add_modifier(AxeReflectHalfOfDamageFromDefaults())

        self.abilities.append(
            Ability(
                name="Axe",
                aiming=TargetEntity(in_range=1),
                instructions=[DamageInstruction(amount=2)],
                is_default=True,
                owner=self,
            )
        )

        self.abilities.append(
            Ability(
                name="Berserker's Call",
                aiming=MultipleAiming(
                    {
                        "self_target": TargetSelf(),
                        "nearby_enemies": IncludeArea(
                            area=Burst(radius=1), condition=is_enemy_aim_condition
                        ),
                    }
                ),
                instructions=[
                    GiveTokenInstruction(
                        aiming_name="self_target", token_class=ArmorToken
                    ),
                    UseAnAbilityInstruction(
                        aiming_name="nearby_enemies", default_only=True
                    ),
                    GiveTokenInstruction(
                        aiming_name="nearby_enemies", token_class=StunnedToken
                    ),
                ],
                owner=self,
                action_cost=ActionCost.FREE,
            )
        )

        self.abilities.append(
            Ability(
                name="Battle Hunger",
                aiming=TargetEntity(in_range=3),
                instructions=[
                    GiveTokenInstruction(token_class=DamageOverTimeToken, amount=2),
                    GiveTokenInstruction(token_class=BattleHungerToken, amount=1),
                ],
                max_charges=1,
                owner=self,
            )
        )
        self.abilities.append(
            Ability(
                name="Culling Blade",
                aiming=TargetEntity(in_range=1),
                instructions=[CullingBladeInstruction()],
                is_ultimate=True,
                max_charges=1,
                owner=self,
            )
        )
