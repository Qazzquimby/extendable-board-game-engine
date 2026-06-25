from typing import Optional, Type

from abilities import Ability
from engine import Engine
from entities import Entity, Summon
from events import Event
from grid import Direction
from logger import log
from mod_value import ModInt
from modifiers import Modifier
from point import Point


class ChangeLocationEvent(Event):
    def __init__(self, subject: "Entity", new_pos: Optional["Point"]):
        super().__init__(engine=subject.engine, subject=subject)
        self.new_pos = new_pos

    def _resolve(self) -> None:
        self.subject.pos = self.new_pos


class PushEvent(Event):
    def __init__(self, subject: "Entity", distance: int, direction: "Direction"):
        super().__init__(engine=subject.engine, subject=subject)
        self.distance = ModInt(distance)
        self.direction = direction

    def _resolve(self) -> None:
        if not getattr(self.subject, "pos", None):
            return

        dist = max(0, self.distance.value)
        if dist > 0:
            path = self.subject.engine.grid.get_push_path(
                subject=self.subject,
                direction=self.direction,
                distance=dist,
            )
            if path:
                log(f"Pushing {self.subject.name} to {path[-1]}")
                for point in path:
                    ChangeLocationEvent(self.subject, point).resolve()


class PullEvent(Event):
    def __init__(self, subject: "Entity", distance: int, toward_point: "Point"):
        super().__init__(engine=subject.engine, subject=subject)
        self.distance = ModInt(distance)
        self.toward_point = toward_point

    def _resolve(self) -> None:
        if not getattr(self.subject, "pos", None):
            return
        dist = max(0, self.distance.value)
        if dist > 0:
            path = self.subject.engine.grid.get_pull_path(
                subject=self.subject,
                pull_to=self.toward_point,
                distance=dist,
            )
            if path:
                log(f"Pulling {self.subject.name} to {path[-1]}")
                for point in path:
                    ChangeLocationEvent(self.subject, point).resolve()


class DeployEvent(Event):
    def __init__(self, subject: "Entity"):
        super().__init__(engine=subject.engine, subject=subject)

    def _resolve(self) -> None:
        pass


class TurnStartEvent(Event):
    def __init__(self, subject: "Entity"):
        super().__init__(engine=subject.engine, subject=subject)

    def _resolve(self) -> None:
        self.subject.engine.current_turn_hero.start_turn()


class TurnEndEvent(Event):
    def __init__(self, subject: "Entity"):
        super().__init__(engine=subject.engine, subject=subject)

    def _resolve(self) -> None:
        for ability in self.subject.abilities:
            if ability.taps:
                if not ability.tapped_this_turn:
                    ability.is_tapped = False
                ability.tapped_this_turn = False


class RoundStartEvent(Event):
    def __init__(self, engine: "Engine"):
        super().__init__(engine=engine)

    def _resolve(self) -> None:
        self.engine.round_num += 1


class DamageEvent(Event):
    def __init__(
        self,
        source: Optional["Entity"],
        subject: "Entity",
        amount: int | ModInt,
        ability: Optional["Ability"] = None,
    ):
        super().__init__(engine=subject.engine, subject=subject)
        self.source = source
        self.amount = ModInt(amount)
        self.ability = ability

    def _resolve(self) -> None:
        if self.subject.has_armor():
            self.amount.add(-1)

        final_damage = max(0, self.amount.value)
        old_hp = self.subject.hp
        new_hp = max(0, self.subject.hp - final_damage)
        self.subject.hp = new_hp

        source_name = self.source.name if self.source else "Environment"
        with log(f"{source_name} dealt {final_damage} damage to {self.subject.name}."):
            if self.subject.hp <= 0 and old_hp > 0:
                DeathEvent(subject=self.subject, killer=self.source).resolve()


class DeathEvent(Event):
    # For on-kill use on-death and filter by killer
    def __init__(self, subject: "Entity", killer: Optional["Entity"] = None):
        super().__init__(engine=subject.engine, subject=subject)
        self.killer = killer

    def _resolve(self) -> None:
        log(f"{self.subject.name} died.")
        self.subject.pos = None


class SummonEvent(Event):
    def __init__(self, summoner: "Entity", subject: "Summon"):
        super().__init__(engine=subject.engine, subject=subject)
        self.summoner = summoner

    def _resolve(self) -> None:
        pass  # should maybe set the summon's pos here?
        # If this is doing nothing it means the summoning couldn't be modified or cancelled by the before stage


class HealEvent(Event):
    def __init__(self, subject: "Entity", amount: int | ModInt):
        super().__init__(engine=subject.engine, subject=subject)
        self.amount = ModInt(amount)

    def _resolve(self) -> None:
        final_heal = max(0, self.amount.value)
        self.subject.hp += final_heal
        log(f"{self.subject.name} healed {final_heal} HP.")


class AddModifierEvent(Event):
    def __init__(
        self, subject: "Entity", modifier_class: Type["Modifier"], modifier_kwargs: dict
    ):
        super().__init__(engine=subject.engine, subject=subject)
        self.modifier_class = modifier_class
        self.modifier_kwargs = modifier_kwargs

    def _resolve(self):
        log(f"{self.subject.name} gained {self.modifier_class.__name__}.")
        self.subject.add_modifier(modifier=self.modifier_class(**self.modifier_kwargs))


class RemoveModifierEvent(Event):
    def __init__(self, subject: "Entity", modifier_class: Type["Modifier"]):
        super().__init__(engine=subject.engine, subject=subject)
        self.modifier_class = modifier_class

    def _resolve(self):
        log(f"{self.subject.name} lost {self.modifier_class.__name__}.")
        existing_modifier = next(
            (
                mod
                for mod in self.subject.modifiers
                if mod.name == self.modifier_class.__name__
            ),
            None,
        )
        if existing_modifier:
            self.subject.remove_modifier(existing_modifier)


class AddTokenEvent(Event):
    def __init__(
        self,
        subject: "Entity",
        token_class: Type["Token"],
        amount: int = 1,
        token_kwargs: Optional[dict] = None,
    ):
        super().__init__(engine=subject.engine, subject=subject)
        self.token_class = token_class
        self.amount = amount
        if not token_kwargs:
            token_kwargs = {}
        self.token_kwargs = token_kwargs

    def _resolve(self):
        log(f"{self.subject.name} gained {self.amount} {self.token_class.__name__}.")
        for modifier in self.subject.modifiers:
            if isinstance(modifier, self.token_class):
                modifier.add(self.amount)
                return
        new_token = self.token_class(amount=self.amount, **self.token_kwargs)
        self.subject.add_modifier(new_token)


class RemoveTokenEvent(Event):
    def __init__(
        self,
        subject: "Entity",
        token_class: Type["Token"],
        amount: int,
    ):
        super().__init__(engine=subject.engine, subject=subject)
        self.token_class = token_class
        self.amount = amount

    def _resolve(self):
        log(f"{self.subject.name} lost {self.amount} {self.token_class.__name__}.")
        for modifiers in self.subject.modifiers:
            if isinstance(modifiers, self.token_class):
                modifiers.remove(self.amount)
                return
