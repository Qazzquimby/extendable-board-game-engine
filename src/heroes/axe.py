from dataclasses import dataclass

from typing import Union
from aimings import (
    TargetEntity,
    TargetSelf,
    MultipleAiming,
    IncludeArea,
    is_enemy_aim_condition,
    AimingResult,
    MultipleAimingResults,
)
from areas import Burst
from engine import (
    Engine,
    Hero,
)
from entities import Entity
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


class AxeSwing(Ability):
    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        return 2


class BerserkersCall(Ability):
    def get_movement(
        self,
        engine: "Engine",
        actor: "Entity",
        reachable_points: set["Point"],
        enemies: list["Entity"],
        allies: list["Entity"],
    ) -> dict["Point", str]:
        proposed_moves = {}
        if not reachable_points or not enemies:
            return proposed_moves

        def enemies_in_burst(pt: Point) -> int:
            return sum(1 for e in enemies if pt.get_distance(e.pos) <= 1)

        best_pt = max(
            reachable_points,
            key=lambda pt: (enemies_in_burst(pt), -pt.get_distance(actor.pos)),
        )
        if enemies_in_burst(best_pt) > 0:
            proposed_moves[best_pt] = "Maximize Berserker's Call targets"
        return proposed_moves

    def is_plausible(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> bool:
        included = aiming_result.sub_aimings["nearby_enemies"].included_points
        return any(
            engine.entity_at(pt) and engine.entity_at(pt).team != actor.team
            for pt in included
        )

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        included = aiming_result.sub_aimings["nearby_enemies"].included_points
        num_enemies_hit = sum(
            1
            for pt in included
            if engine.entity_at(pt) and engine.entity_at(pt).team != actor.team
        )
        return 1.9 * num_enemies_hit


class BattleHunger(Ability):
    def is_plausible(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> bool:
        target = engine.entity_at(aiming_result.target_points[0])
        if target:
            return not target.get_modifier(BattleHungerToken)
        return False

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        target = engine.entity_at(aiming_result.target_points[0])
        if not target:
            return 1

        turns_remaining = 7 - engine.round_num
        total_damage = min(turns_remaining * 2, target.hp)
        return 0.7 * total_damage


class CullingBlade(Ability):
    def get_movement(
        self,
        engine: "Engine",
        actor: "Entity",
        reachable_points: set["Point"],
        enemies: list["Entity"],
        allies: list["Entity"],
    ) -> dict["Point", str]:
        proposed_moves = {}
        if not reachable_points:
            return proposed_moves

        killable_enemies = [e for e in enemies if e.hp <= 3]
        if killable_enemies:
            for enemy in killable_enemies:
                best_pt = min(
                    reachable_points,
                    key=lambda pt: (
                        abs(pt.get_distance(enemy.pos) - 1),
                        pt.get_distance(actor.pos),
                    ),
                )
                if best_pt.get_distance(enemy.pos) == 1:
                    proposed_moves[best_pt] = f"Move to cull {enemy.name}"
        else:
            for enemy in enemies:
                best_pt = min(
                    reachable_points,
                    key=lambda pt: (
                        abs(pt.get_distance(enemy.pos) - 1),
                        pt.get_distance(actor.pos),
                    ),
                )
                proposed_moves[best_pt] = f"Move to range 1 of {enemy.name}"

        return proposed_moves

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        target = engine.entity_at(aiming_result.target_points[0])
        if not target:
            return 1

        if target.hp <= 3:
            return 5
        else:
            return 2  # less than damage because opportunity cost


class Axe(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(engine=engine, name="Axe", hp=10, speed=3, pos=pos, team=team)

        self.add_modifier(engine=engine, modifier=AxeCounterHelix())
        self.add_modifier(engine, AxeReflectHalfOfDamageFromDefaults())

        self.abilities.append(
            AxeSwing(
                name="Axe Swing",
                text="Range 1, 2dmg",
                aiming=TargetEntity(in_range=1),
                instructions=[DamageInstruction(amount=2)],
                is_default=True,
                owner_id=self.id,
            )
        )

        self.abilities.append(
            BerserkersCall(
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
            BattleHunger(
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
            CullingBlade(
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
