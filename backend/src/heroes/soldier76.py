"""
Soldier 76 — sustained DPS rifleman with healing field.

Simplified for the grid engine:
- Heavy Pulse Rifle: Range 4, 3dmg
- Helix Rockets: Range 3, Burst 1, 2dmg (AoE)
- Biotic Field: Heal 2, 1/Game
- Tactical Visor (Ultimate 4): Default attacks undefendable, +1 range
"""

from abilities import (
    Ability,
    ActionCost,
    Instruction,
    ActionContext,
)
from instruction_library import (
    DamageInstruction,
    HealInstruction,
    AddModifierInstruction,
)
from aimings import TargetEntity, IncludeArea, TargetSelf
from areas import Burst
from engine import Engine
from entities import Hero, Entity
from modifiers import Modifier
from events import after
from event_library import TurnEndEvent, DamageEvent
from valence import Valence
from point import Point
from typing import Union
from aimings import AimingResult, MultipleAimingResults


class VisorModifier(Modifier):
    """Default attacks are undefendable and have +1 range."""

    valence = Valence.GOOD
    duration: int = 2  # turns

    def apply_undefendable(self) -> bool:
        return True

    def modify_range(self, base_range: int) -> int:
        return base_range + 1


class Soldier76(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Soldier 76", hp=8, speed=4, pos=pos, team=team
        )

        self.abilities.append(
            Ability(
                name="Heavy Pulse Rifle",
                aiming=TargetEntity(in_range=4),
                instructions=[DamageInstruction(amount=3)],
                is_default=True,
                owner_id=self.id,
            )
        )

        self.abilities.append(
            Ability(
                name="Helix Rockets",
                aiming=IncludeArea(area=Burst(radius=1, in_range=3)),
                instructions=[DamageInstruction(amount=2)],
                taps=True,
                owner_id=self.id,
            )
        )

        self.abilities.append(
            Ability(
                name="Biotic Field",
                aiming=TargetSelf(),
                instructions=[HealInstruction(amount=2)],
                taps=True,
                owner_id=self.id,
            )
        )

        self.abilities.append(
            Ability(
                name="Tactical Visor",
                aiming=TargetSelf(),
                instructions=[AddModifierInstruction(modifier_class=VisorModifier)],
                is_ultimate=True,
                ultimate_turn=4,
                owner_id=self.id,
            )
        )


class HelixRocketsAbility(Ability):
    def __init__(self, owner_id: str):
        super().__init__(
            name="Helix Rockets",
            aiming=IncludeArea(area=Burst(radius=1, in_range=3)),
            instructions=[DamageInstruction(amount=2)],
            taps=True,
            owner_id=owner_id,
        )

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        included = aiming_result.included_points
        enemies_hit = sum(
            1
            for pt in included
            if engine.entity_at(pt) and engine.entity_at(pt).team != actor.team
        )
        return 1.5 * enemies_hit
