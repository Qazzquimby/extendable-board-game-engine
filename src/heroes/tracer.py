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
from logger import log
from modifiers import Modifier, Token, ArmorToken, StunnedToken, Armor, SlowToken
from events import TurnEndEvent, DamageEvent, after, DeathEvent, before
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


class Tracer(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Tracer", hp=6, speed=4, pos=pos, team=team
        )
