from engine import Entity, Engine
from abilities import (
    Ability,
    DamageInstruction,
    GiveTokenInstruction,
    ApplyModifierInstruction,
    TargetUnit,
    TargetSelf,
    TargetArea,
)
from targeting import Burst, Square, Line
from point import Point
from engine import Immobile, InnateArmor


class MeleeHero(Entity):
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


class RangedHero(Entity):
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


class Symmetra(Entity):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Symmetra", hp=8, speed=3, pos=pos, team=team
        )
        # ENGINE INSUFFICIENT:
        # - Missing End of Activation triggers
        # - Missing Action Types (Free Action, Ultimate, Reaction)
        # - Missing Object / Marker creation (Turrets, Teleporter, Barriers)
        # - Missing "Unlimited" range targeting
        # - Missing Delayed effects (e.g. At the beginning of your next activation)
        # - Missing Facing and Edges for objects (Floating Barrier)
        # - Missing Aura mechanics for maximum health buffs (Shield Generator)

        # Approximated Default Ability
        self.abilities.append(
            Ability(
                name="Photon Beam",
                targeting=TargetUnit(in_range=2),
                instructions=[
                    DamageInstruction(amount=2, undefendable=True),
                    GiveTokenInstruction(token_name="Photon Beam", amount=1),
                ],  # Missing token scaling
                is_default=True,
                owner=self,
            )
        )


class Reinhardt(Entity):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Reinhardt", hp=12, speed=3, pos=pos, team=team
        )
        # ENGINE INSUFFICIENT:
        # - Missing Forced Movement (Push/Pull) and immunity to it
        # - Missing Stances and Movement restrictions (Slow condition)
        # - Missing Collision detection during movement (Charge)
        # - Missing Tap/Exhaust resource mechanic (Fire Strike)
        # - Missing Ultimate charge mechanics (Earthshatter)

        self.abilities.append(
            Ability(
                name="Rocket Hammer",
                targeting=TargetArea(area=Burst(radius=2, in_range=1)),
                # todo, no, targeting is a path of '3 adjacent spaces within range 1'.
                instructions=[DamageInstruction(amount=2)],
                is_default=True,
                owner=self,
            )
        )
        self.abilities.append(
            Ability(
                name="Fire Strike",
                targeting=TargetArea(area=Line(length=99)),
                instructions=[DamageInstruction(amount=3)],
                owner=self,
            )
        )
        self.abilities.append(
            Ability(
                name="Earthshatter",
                targeting=TargetArea(area=Square(side_length=3, in_range=2)),
                instructions=[ApplyModifierInstruction(modifier_class=Immobile)],
                # todo immobile until end of their next turn.
                owner=self,
            )
        )


class Viktoria(Entity):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Viktoria", hp=6, speed=3, pos=pos, team=team
        )
        # ENGINE INSUFFICIENT:
        # - Missing Summoning/Deploy mechanics without abilities
        # - Missing Global team-wide triggers (All Viktorias heal 2)
        # - Missing Death events / On-Kill events
        # - Missing Critical Hit mechanics
        # - Missing Teleport movement

        self.abilities.append(
            Ability(
                name="Enchanted Katana",
                targeting=TargetUnit(in_range=1),
                instructions=[
                    DamageInstruction(amount=2)
                ],  # Missing Crit and Burst AoE
                is_default=True,
                owner=self,
            )
        )


class Spy(Entity):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(engine=engine, name="Spy", hp=6, speed=3, pos=pos, team=team)
        # ENGINE INSUFFICIENT:
        # - Missing Target spoofing (Treat as ally, redirect target)
        # - Missing Reactions to enemy movement
        # - Missing Removal from board and hidden info (Face down markers)
        # - Missing Damage over Time (DoT)
        # - Missing Damage Resistance and conditional trigger prevention (Deadringer)

        self.abilities.append(
            Ability(
                name="Revolver",
                targeting=TargetUnit(),
                instructions=[
                    DamageInstruction(amount=2, irreducible=True)
                ],  # Missing kill counter scaling
                is_default=True,
                owner=self,
            )
        )


class Axe(Entity):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(engine=engine, name="Axe", hp=10, speed=3, pos=pos, team=team)
        # ENGINE INSUFFICIENT:
        # - Missing On-Damage received events (Counter Helix)
        # - Missing tracking of Ability Types (Default vs non-Default in event context)
        # - Missing Movement cost modifiers (Battle Hunger)
        # - Missing Temporary Condition tracking (Berserker's Call duration)
        # - Missing "Target must use X" forcing mechanics
        # - Missing "Refresh ability" mechanic
        # - Missing Hero/Summon unit typing

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
                cost_standard_action=False,
                owner=self,
            )
        )
        self.abilities.append(
            Ability(
                name="Battle Hunger",
                targeting=TargetUnit(in_range=3),
                instructions=[
                    GiveTokenInstruction(token_name="Damage over Time", amount=2),
                    GiveTokenInstruction(token_name="Battle Hunger", amount=1),
                ],
                owner=self,
            )
        )
        self.abilities.append(
            Ability(
                name="Culling Blade",
                targeting=TargetUnit(in_range=1),
                instructions=[DamageInstruction(amount=3, irreducible=True)],
                owner=self,
            )
        )
