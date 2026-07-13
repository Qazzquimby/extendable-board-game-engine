from dataclasses import dataclass

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
from events import after, before
from event_library import TurnEndEvent, DamageEvent, DeathEvent
from abilities import (
    Ability,
    DamageInstruction,
    AddTokenInstruction,
    RefreshAbilityInstruction,
    ActionCost,
    Instruction,
    ActionContext,
    UseAnAbilityInstruction,
)
from mod_value import div
from point import Point
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


class BattleHungerToken(Token):
    valence = Valence.BAD

    @after(DeathEvent)
    def on_kill_clear_this_and_DoT(self, engine: "Engine", event: DeathEvent) -> None:
        subject = engine.get_entity_by_id(event.subject_id)
        owner = engine.get_entity_by_id(self.owner_id)
        if event.killer_id == self.owner_id and isinstance(subject, Hero):
            with self.log_trigger(engine, event):
                owner.remove_token(engine, BattleHungerToken)
                owner.remove_token(engine, DamageOverTimeToken, amount=99)


@dataclass
class CullingBladeInstruction(Instruction):
    valence = Valence.BAD

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        target = ctx.get_target(engine)
        if not target or not hasattr(target, "hp"):
            return
        source = engine.get_entity_by_id(ctx.source_id)
        event = DamageEvent(
            source=source,
            subject=target,
            amount=3,
            ability=ctx.ability,
        )
        event.amount.is_irreducible = True
        engine.event_queue.enqueue(event)
        if target.hp <= 0:
            RefreshAbilityInstruction().execute(engine=engine, ctx=ctx)
            if ctx.ability and ctx.ability.charges is not None:
                ctx.ability.charges += 1
            if isinstance(target, Hero):
                source.add_modifier(engine, Armor())


@dataclass(kw_only=True)
class AxeCounterHelix(Modifier):
    text = "When you take damage: Enemies in burst 1, 1dmg."
    valence = Valence.GOOD

    # - name: Receive damage
    #   text: |-
    #     Enemies in burst 1, 1dmg
    @after(DamageEvent)
    def burst_damage(self, engine: "Engine", event: "DamageEvent") -> None:
        if event.amount > 0:
            owner = engine.get_entity_by_id(self.owner_id)
            points_in_range = engine.grid.get_points_in_range(
                start=owner.pos, max_range=1
            )
            entities_hit = [
                entity
                for entity in engine.living_entities
                if entity.team != owner.team and entity.pos in points_in_range
            ]
            if entities_hit:
                with self.log_trigger(engine=engine, event=event):
                    for entity in entities_hit:
                        engine.event_queue.enqueue(
                            DamageEvent(source=owner, subject=entity, amount=1)
                        )


class AxeReflectHalfOfDamageFromDefaults(Modifier):
    text = "When you receive damage from a Default Ability: The attacker takes 1/2 the damage received, before Armor."
    valence = Valence.GOOD

    #       name: Receive damage from a Default Ability
    #       text: The attacker takes 1/2 the damage received, before Armor.
    @after(DamageEvent)
    def reflect_default_damage(self, engine: "Engine", event: "DamageEvent") -> None:
        if event.ability and event.ability.is_default and event.source:
            reflect_amt = div(event.amount.value, 2)
            if reflect_amt > 0:
                with self.log_trigger(engine=engine, event=event):
                    owner = engine.get_entity_by_id(self.owner_id)
                    engine.event_queue.enqueue(
                        DamageEvent(
                            source=owner,
                            subject=event.source,
                            amount=reflect_amt,
                        )
                    )


class Axe(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(engine=engine, name="Axe", hp=10, speed=3, pos=pos, team=team)

        self.add_modifier(engine=engine, modifier=AxeCounterHelix())
        self.add_modifier(engine, AxeReflectHalfOfDamageFromDefaults())

        self.abilities.append(
            Ability(
                name="Axe Swing",
                text="Range 1, 2dmg",
                aiming=TargetEntity(in_range=1),
                instructions=[DamageInstruction(amount=2)],
                is_default=True,
                owner_id=self.id,
            )
        )

        self.abilities.append(
            Ability(
                name="Berserker's Call",
                text="""\
        1/Game, Free Action
        Until the beginning of your next turn,
          You have Armor
        All enemies in range 1 of you use a default ability targeting you, if possible, and are stunned.""",
                aiming=MultipleAiming(
                    {
                        "self_target": TargetSelf(),
                        "nearby_enemies": IncludeArea(
                            area=Burst(radius=1), condition=is_enemy_aim_condition
                        ),
                    }
                ),
                instructions=[
                    AddTokenInstruction(
                        aiming_name="self_target", token_class=ArmorToken
                    ),
                    UseAnAbilityInstruction(
                        aiming_name="nearby_enemies", default_only=True
                    ),
                    AddTokenInstruction(
                        aiming_name="nearby_enemies", token_class=StunnedToken
                    ),
                ],
                owner_id=self.id,
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
                owner_id=self.id,
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
                owner_id=self.id,
            )
        )
