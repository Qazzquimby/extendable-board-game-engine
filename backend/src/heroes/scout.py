"""
Scout (TF2) — high mobility, low health, high melee damage.

Simplified for grid engine:
- Scattergun: Range 1, 4dmg, push 1
- Bonk Atomic Punch: Self immune to damage (1/Game, lasts 1 turn)
- Crit-a-Cola: Self buff, deal +50% damage, receive +50% damage (1/Game)
- Fan O'War: Range 1, target takes +50% damage
"""

from abilities import (
    Ability,
    Instruction,
    ActionContext,
    score_damage,
)
from instruction_library import (
    DamageInstruction,
    ApplyModifierInstruction,
    PushInstruction,
)
from aimings import (
    TargetEntity,
    TargetSelf,
)
from engine import Engine
from entities import Hero, Entity
from modifiers import Modifier
from events import before, after
from event_library import DamageEvent, TurnEndEvent
from valence import Valence
from point import Point
from typing import Union
from aimings import AimingResult, MultipleAimingResults


class BonkedModifier(Modifier):
    """Immune to all damage."""

    valence = Valence.GOOD
    duration: int = 1  # turns

    def apply_immunity(self) -> bool:
        return True

    @before(DamageEvent)
    def block_damage(self, engine: "Engine", event: "DamageEvent") -> None:
        owner = engine.get_entity_by_id(self.owner_id)
        if event.subject_id == self.owner_id:
            with self.log_trigger(engine=engine, event=event):
                event.canceled = True


class CritAColaDebuff(Modifier):
    """Receive +50% damage."""

    valence = Valence.BAD
    duration: int = 1

    def apply_vulnerable(self) -> int:
        return 50


class CritAColaBuff(Modifier):
    """Deal +50% damage."""

    valence = Valence.GOOD
    duration: int = 1

    def apply_damage_buff(self) -> int:
        return 50


class FanOWarDebuff(Modifier):
    """Target takes +50% damage."""

    valence = Valence.BAD
    duration: int = 2

    def apply_vulnerable(self) -> int:
        return 50


class Scout(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Scout", hp=6, speed=5, pos=pos, team=team
        )

        self.abilities.append(
            Ability(
                name="Scattergun",
                aiming=TargetEntity(in_range=1),
                instructions=[
                    DamageInstruction(amount=4),
                    PushInstruction(distance=1),
                ],
                is_default=True,
                owner_id=self.id,
            )
        )

        self.abilities.append(
            Ability(
                name="Bonk Atomic Punch",
                aiming=TargetSelf(),
                instructions=[
                    ApplyModifierInstruction(
                        modifier_class=BonkedModifier
                    )
                ],
                taps=True,
                owner_id=self.id,
            )
        )

        self.abilities.append(
            Ability(
                name="Crit-a-Cola",
                aiming=TargetSelf(),
                instructions=[
                    ApplyModifierInstruction(
                        modifier_class=CritAColaBuff
                    ),
                    ApplyModifierInstruction(
                        modifier_class=CritAColaDebuff
                    ),
                ],
                taps=True,
                owner_id=self.id,
            )
        )

        self.abilities.append(
            Ability(
                name="Fan O'War",
                aiming=TargetEntity(in_range=1),
                instructions=[
                    ApplyModifierInstruction(
                        modifier_class=FanOWarDebuff
                    )
                ],
                owner_id=self.id,
            )
        )


class ScattergunAbility(Ability):
    def __init__(self, owner_id: str):
        super().__init__(
            name="Scattergun",
            aiming=TargetEntity(in_range=1),
            instructions=[
                DamageInstruction(amount=4),
                PushInstruction(distance=1),
            ],
            is_default=True,
            owner_id=owner_id,
        )
