from dataclasses import dataclass
from typing import Set, Iterator

from engine import (
    Engine,
    Hero,
    TurnEndEvent,
    before,
    Immobile,
    InnateArmor,
    Token,
    Modifier,
    after,
    DeathEvent,
    HealEvent,
    DamageEvent,
    PushEvent,
    PullEvent,
    query,
    QueryDefense,
    Entity,
)
from abilities import (
    Ability,
    DamageInstruction,
    GiveTokenInstruction,
    ApplyModifierInstruction,
    TargetUnit,
    TargetSelf,
    TargetArea,
    Instruction,
    ActionContext,
    RemoveTokenInstruction,
    RefreshAbilityInstruction,
    PushInstruction,
    ActionCost,
)
from grid import Grid
from mod_value import div
from targeting import Square, Line, PathArea
from point import Point


class MeleeHero(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Melee Hero", hp=10, speed=3, pos=pos, team=team
        )
        self.abilities.append(
            Ability(
                name="Melee Attack",
                targeting=TargetUnit(in_range=1),
                instructions=[DamageInstruction(amount=2)],
                is_default=True,
                owner=self,
            )
        )
        self.abilities.append(
            Ability(
                name="Do Nothing", targeting=TargetSelf(), instructions=[], owner=self
            )
        )


class RangedHero(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Ranged Hero", hp=6, speed=3, pos=pos, team=team
        )
        self.abilities.append(
            Ability(
                name="Ranged Attack",
                targeting=TargetUnit(in_range=3),
                instructions=[DamageInstruction(amount=2)],
                is_default=True,
                owner=self,
            )
        )
        self.abilities.append(
            Ability(
                name="Do Nothing", targeting=TargetSelf(), instructions=[], owner=self
            )
        )


class PhotonBeamToken(Token):
    pass


class Symmetra(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Symmetra", hp=8, speed=3, pos=pos, team=team
        )
        # TODO:
        #  Missing End of Activation triggers
        #  Missing Action Types (Free Action, Ultimate, Reaction)
        #  Missing Object / Marker creation (Turrets, Teleporter, Barriers)
        #  Missing Delayed effects (e.g. At the beginning of your next activation)
        #  Missing Facing and Edges for objects (Floating Barrier)
        #  Missing Aura mechanics for maximum health buffs (Shield Generator)

        self.abilities.append(
            Ability(
                name="Photon Beam",
                targeting=TargetUnit(in_range=2),
                instructions=[
                    DamageInstruction(
                        amount=lambda ctx: 2
                        + (
                            2
                            * getattr(ctx.target, "get_token_count", lambda t: 0)(
                                PhotonBeamToken
                            )
                        ),
                        undefendable=True,
                    ),
                    GiveTokenInstruction(token_class=PhotonBeamToken, amount=1),
                ],
                is_default=True,
                owner=self,
            )
        )


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

        path = [ctx.source.pos] + ctx.included
        last_point = path[-1]
        second_last_point = path[-2]

        for point in ctx.included:
            entity = ctx.engine.entity_at(point)
            if not entity:
                continue
            if not first_enemy:
                first_enemy = entity
                DamageEvent(
                    engine=ctx.engine,
                    source=ctx.source,
                    target=entity,
                    amount=6,
                    ability=ctx.ability,
                ).resolve()
                entity.add_modifier(Immobile())
                entity.pos = last_point
            else:
                DamageEvent(
                    engine=ctx.engine,
                    source=ctx.source,
                    target=entity,
                    amount=1,
                    ability=ctx.ability,
                ).resolve()

        if first_enemy:
            ctx.source.pos = second_last_point
        else:
            ctx.source.pos = last_point


class Reinhardt(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Reinhardt", hp=12, speed=3, pos=pos, team=team
        )

        class CannotBePushedOrPulled(Modifier):
            @before(PushEvent)
            def prevent_movement(self, event):
                event.canceled = True

            @before(PullEvent)
            def prevent_movement(self, event):
                event.canceled = True

        self.add_modifier(CannotBePushedOrPulled())

        self.abilities.append(
            Ability(
                name="Rocket Hammer",
                targeting=TargetArea(
                    area=PathAllInRangeArea(
                        length=3,
                        in_range=1,
                    )
                ),
                instructions=[DamageInstruction(amount=2)],
                is_default=True,
                owner=self,
            )
        )
        self.abilities.append(
            Ability(
                name="Charge",
                targeting=TargetArea(area=Line(length=99, in_range=0)),
                instructions=[ChargeInstruction()],
                action_cost=ActionCost.MOVE_AND_STANDARD,
                max_charges=1,
                owner=self,
            )
        )
        self.abilities.append(
            Ability(
                name="Fire Strike",
                targeting=TargetArea(area=Line(length=99)),
                instructions=[DamageInstruction(amount=3)],
                taps=True,
                owner=self,
            )
        )
        self.abilities.append(
            Ability(
                name="Earthshatter",
                targeting=TargetArea(area=Square(side_length=3, in_range=2)),
                instructions=[ApplyModifierInstruction(modifier_class=Immobile)],
                is_ultimate=True,
                ultimate_turn=4,
                max_charges=1,
                owner=self,
            )
        )


class AllViktoriasHealWhenAnyViktoriaKills(Modifier):
    @after(DeathEvent, target_self=False)
    def on_kill(self, event: DeathEvent):
        if event.killer == self.owner:
            for entity in self.owner.engine.living_entities:
                if entity.name == "Viktoria":
                    HealEvent(self.owner.engine, target=entity, amount=2).resolve()


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
                HealEvent(self.owner.engine, target=entity, amount=2).resolve()
                self.owner.add_modifier(DefenseModifier(owner=entity, amount=2))


@dataclass
class KatanaBurstInstruction(Instruction):
    def execute(self, ctx: ActionContext) -> None:
        from engine import DamageEvent

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
                    ctx.engine, source=ctx.source, target=entity, amount=1
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
                targeting=TargetUnit(in_range=1),
                instructions=[DamageInstruction(amount=2), KatanaBurstInstruction()],
                crit_chance=2,
                is_default=True,
                owner=self,
            )
        )


class KillCounter(Token):
    pass


class DamageOverTimeToken(Token):
    @before(TurnEndEvent)
    def take_damage(self, event: TurnEndEvent) -> None:
        from engine import DamageEvent

        DamageEvent(
            engine=event.engine, source=None, target=self.owner, amount=self.amount
        ).resolve()


class Spy(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(engine=engine, name="Spy", hp=6, speed=3, pos=pos, team=team)
        # TODO:
        #  Missing query_is_ally
        #  Missing Redirect ability target
        #  Missing Reactions to enemy movement
        #  Missing Removal from board and hidden info (Face down markers)
        #  Missing Damage over Time (DoT)
        #  Missing Damage Resistance and conditional trigger prevention (Deadringer)

        def revolver_damage(ctx: ActionContext) -> int:
            if ctx.target.get_token_count(KillCounter) > 0:
                return 4
            return 2

        self.abilities.append(
            Ability(
                name="Revolver",
                targeting=TargetUnit(),
                instructions=[
                    DamageInstruction(amount=revolver_damage, irreducible=True),
                    RemoveTokenInstruction(token_class=KillCounter, amount=1),
                ],
                is_default=True,
                owner=self,
            )
        )


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
            target=ctx.target,
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
                        self.owner.engine, source=self.owner, target=entity, amount=1
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
                    target=event.source,
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
                targeting=TargetUnit(in_range=1),
                instructions=[DamageInstruction(amount=2)],
                is_default=True,
                owner=self,
            )
        )
        self.abilities.append(
            Ability(
                name="Berserker's Call",
                targeting=TargetSelf(),
                instructions=[ApplyModifierInstruction(modifier_class=InnateArmor)],
                action_cost=ActionCost.FREE,
                max_charges=1,
                owner=self,
            )
        )
        self.abilities.append(
            Ability(
                name="Battle Hunger",
                targeting=TargetUnit(in_range=3),
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
                targeting=TargetUnit(in_range=1),
                instructions=[CullingBladeInstruction()],
                max_charges=1,
                owner=self,
            )
        )
