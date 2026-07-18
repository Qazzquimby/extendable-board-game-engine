"""
Zenyatta — slow heal, damage buff, burst damage.

Simplified for grid engine:
- Snap Kick: Range 1, 2dmg, push 2
- Orb of Destruction: Range 4, 2dmg
- Orb of Harmony: Range 4, Heal 2 (single-target restore)
- Orb of Discord: Range 4, target takes +50% damage (modifier)
- Transcendence (Ultimate 3): Heal 5 AoE
"""

from abilities import (
    Ability,
    ActionCost,
    Instruction,
    ActionContext,
    score_damage,
)
from instruction_library import (
    DamageInstruction,
    HealInstruction,
    ApplyModifierInstruction,
    PushInstruction,
)
from aimings import (
    TargetEntity,
    TargetSelf,
    IncludeArea,
    is_ally_aim_condition,
)
from areas import Burst
from engine import Engine
from entities import Hero, Entity
from modifiers import Modifier
from events import before, after
from event_library import DamageEvent, TurnEndEvent
from valence import Valence
from point import Point
from typing import Union
from aimings import AimingResult, MultipleAimingResults


class OrbOfDiscordModifier(Modifier):
    """Target takes +50% damage."""

    valence = Valence.BAD
    duration: int = 2  # turns

    def apply_vulnerable(self) -> int:
        return 50  # +50% damage


class OrbOfHarmonyModifier(Modifier):
    """Heal 2 at start of turn."""

    valence = Valence.GOOD
    duration: int = 2

    @after(TurnEndEvent)
    def heal_owner(self, engine: "Engine", event: "TurnEndEvent") -> None:
        owner = engine.get_entity_by_id(self.owner_id)
        if owner and owner.hp < owner.max_hp:
            with self.log_trigger(engine=engine, event=event):
                owner.heal(2, engine)


class Zenyatta(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Zenyatta", hp=8, speed=3, pos=pos, team=team
        )

        self.abilities.append(
            Ability(
                name="Snap Kick",
                aiming=TargetEntity(in_range=1),
                instructions=[
                    DamageInstruction(amount=2),
                    PushInstruction(distance=2),
                ],
                owner_id=self.id,
            )
        )
        self.abilities.append(
            Ability(
                name="Orb of Destruction",
                aiming=TargetEntity(in_range=4),
                instructions=[DamageInstruction(amount=2)],
                is_default=True,
                owner_id=self.id,
            )
        )
        self.abilities.append(
            Ability(
                name="Orb of Harmony",
                aiming=TargetEntity(in_range=4, condition=is_ally_aim_condition),
                instructions=[HealInstruction(amount=2)],
                taps=True,
                owner_id=self.id,
            )
        )
        self.abilities.append(
            Ability(
                name="Orb of Discord",
                aiming=TargetEntity(in_range=4),
                instructions=[
                    ApplyModifierInstruction(
                        modifier_class=OrbOfDiscordModifier
                    )
                ],
                taps=True,
                owner_id=self.id,
            )
        )
        self.abilities.append(
            Ability(
                name="Transcendence",
                aiming=IncludeArea(area=Burst(radius=1, in_range=0)),
                instructions=[HealInstruction(amount=5)],
                is_ultimate=True,
                ultimate_turn=3,
                owner_id=self.id,
            )
        )

    def start_turn(self):
        super().start_turn()
        # Clear expired Orb modifiers (handled by duration)
