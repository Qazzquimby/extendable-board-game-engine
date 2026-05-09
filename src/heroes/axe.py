from dataclasses import dataclass

from aimings import TargetEntity, TargetSelf
from engine import (
    Engine,
    Hero,
    TurnEndEvent,
    before,
    InnateArmor,
    Token,
    Modifier,
    after,
    DamageEvent,
)
from abilities import (
    Ability,
    DamageInstruction,
    GiveTokenInstruction,
    ApplyModifierInstruction,
    Instruction,
    ActionContext,
    RefreshAbilityInstruction,
    ActionCost,
)
from mod_value import div
from point import Point


class DamageOverTimeToken(Token):
    @before(TurnEndEvent)
    def take_damage(self, event: TurnEndEvent) -> None:
        from engine import DamageEvent

        DamageEvent(
            engine=event.engine, source=None, receiver=self.owner, amount=self.amount
        ).resolve()


class BattleHungerToken(Token):
    pass


@dataclass
class CullingBladeInstruction(Instruction):

    def execute(self, ctx: ActionContext) -> None:
        if not hasattr(ctx.target, "hp"):
            return
        event = DamageEvent(
            engine=ctx.engine,
            source=ctx.source,
            receiver=ctx.target,
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
                ctx.source.add_modifier(InnateArmor())


class AxeCleaveOnTakeDamage(Modifier):
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
                    DamageEvent(
                        self.owner.engine, source=self.owner, receiver=entity, amount=1
                    ).resolve()


class AxeReflectHalfOfDamageFromDefaults(Modifier):
    #       name: Receive damage from a Default Ability
    #       text: The attacker takes 1/2 the damage received, before Armor.
    @before(DamageEvent)
    def reflect_default_damage(self, event: "DamageEvent") -> None:
        if event.ability and event.ability.is_default and event.source:
            reflect_amt = div(event.amount.value, 2)
            if reflect_amt > 0:
                DamageEvent(
                    self.owner.engine,
                    source=self.owner,
                    receiver=event.source,
                    amount=reflect_amt,
                ).resolve()


class Axe(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(engine=engine, name="Axe", hp=10, speed=3, pos=pos, team=team)
        # TODO:
        # TODO Missing Movement cost modifiers (Battle Hunger)
        # TODO Missing Temporary Condition tracking (Berserker's Call duration)
        # TODO Missing "Refresh ability" mechanic

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
                aiming=TargetSelf(),
                instructions=[ApplyModifierInstruction(modifier_class=InnateArmor)],
                action_cost=ActionCost.FREE,
                max_charges=1,
                owner=self,
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
                max_charges=1,
                owner=self,
            )
        )
