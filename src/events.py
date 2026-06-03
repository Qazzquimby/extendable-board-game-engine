import abc
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Type, Callable, Any, List, TYPE_CHECKING

from mod_value import ModInt

if TYPE_CHECKING:
    from engine import Engine
    from abilities import Ability
    from modifiers import Modifier, Token
    from entities import Entity, Summon
    from point import Point


class Event(abc.ABC):
    def __init__(self, engine: "Engine", subject: Optional["Entity"] = None):
        self.engine = engine
        self.subject = subject
        self.canceled = False

    def resolve(self) -> None:
        self.engine.router.publish(self, EventPhase.BEFORE)

        if self.canceled:
            return
        self._resolve()

        self.engine.router.publish(self, EventPhase.AFTER)

    def _resolve(self) -> None:
        raise NotImplementedError("Events must implement resolve()")


class EventPhase(Enum):
    BEFORE = auto()
    AFTER = auto()
    QUERY = auto()


@dataclass
class Subscription:
    modifier: "Modifier"
    event_type: Type
    phase: EventPhase
    only_self: bool
    func: Callable[[Any], None]


class Router:
    def __init__(self) -> None:
        self.subscribers: List[Subscription] = []

    def subscribe(self, modifier: "Modifier") -> None:
        for name in dir(modifier):
            method = getattr(modifier, name)
            if hasattr(method, "_listen_event"):
                self.subscribers.append(
                    Subscription(
                        modifier=modifier,
                        event_type=method._listen_event,
                        phase=method._listen_phase,
                        only_self=method._listen_only_self,
                        func=method,
                    )
                )

    def unsubscribe(self, modifier: "Modifier") -> None:
        self.subscribers = [sub for sub in self.subscribers if sub.modifier != modifier]

    def publish(self, event: Any, phase: EventPhase) -> None:
        for sub in list(self.subscribers):  # iterate copy
            if sub.event_type == type(event) and sub.phase == phase:
                if sub.only_self:
                    if event.subject != sub.modifier.owner:
                        continue
                sub.func(event)


def before(event_type: Type, only_self: bool = True) -> Callable:
    def decorator(func: Callable) -> Callable:
        func._listen_event = event_type
        func._listen_phase = EventPhase.BEFORE
        func._listen_only_self = only_self
        return func

    return decorator


def after(event_type: Type, only_self: bool = True) -> Callable:
    def decorator(func: Callable) -> Callable:
        func._listen_event = event_type
        func._listen_phase = EventPhase.AFTER
        func._listen_only_self = only_self
        return func

    return decorator


def query(event_type: Type, only_self: bool = True) -> Callable:
    def decorator(func: Callable) -> Callable:
        func._listen_event = event_type
        func._listen_phase = EventPhase.QUERY
        func._listen_only_self = only_self
        return func

    return decorator


class ChangeLocationEvent(Event):
    def __init__(self, subject: "Entity", new_pos: Optional["Point"]):
        super().__init__(engine=subject.engine, subject=subject)
        self.new_pos = new_pos

    def _resolve(self) -> None:
        self.subject.pos = self.new_pos


# class PushEvent(Event):
#     def __init__(
#         self,
#
#         subject: "Entity",
#         distance: int,
#         source: Optional["Entity"] = None,
#     ):
#         super().__init__(subject=subject)
#         self.distance = ModInt(distance)
#         self.source = source
#
#     def _resolve(self) -> None:
#         # Pushing is calculated based on pathing away from the source
#         if (
#             getattr(self.subject, "pos", None) is not None
#             and self.source
#             and getattr(self.source, "pos", None) is not None
#         ):
#             dist = max(0, self.distance.value)
#             if dist > 0:
#                 path = self.subject.engine.grid.get_push_path(  # todo
#                     start=self.subject.pos, target=None, push_from=self.source.pos
#                 )
#                 if path and len(path) >= dist:
#                     self.subject.pos = path[dist - 1]


class PullEvent(Event):
    def __init__(
        self,
        subject: "Entity",
        distance: int,
        source: Optional["Entity"] = None,
    ):
        super().__init__(engine=subject.engine, subject=subject)
        self.distance = ModInt(distance)
        self.source = source

    def _resolve(self) -> None:
        if (
            getattr(self.subject, "pos", None) is not None
            and self.source
            and getattr(self.source, "pos", None) is not None
        ):
            dist = max(0, self.distance.value)
            if dist > 0:
                path = self.subject.engine.grid.get_pull_path(
                    self.subject.pos, self.source.pos, self.source.pos
                )
                if path and len(path) >= dist:
                    self.subject.pos = path[dist - 1]


class TurnStartEvent(Event):
    def __init__(self, subject: "Entity"):
        super().__init__(engine=subject.engine, subject=subject)

    def _resolve(self) -> None:
        self.subject.engine.current_hero.start_turn()


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
        pass


class RoundEndEvent(Event):
    def __init__(self, engine: "Engine"):
        super().__init__(engine=engine)

    def _resolve(self) -> None:
        pass


class DamageEvent(Event):
    def __init__(
        self,
        source: Optional["Entity"],
        subject: "Entity",
        amount: int,
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
        new_hp = max(0, self.subject.hp - final_damage)
        self.subject.hp = new_hp

        if self.subject.hp <= 0:
            DeathEvent(subject=self.subject, killer=self.source).resolve()


class DeathEvent(Event):
    # For on-kill use on-death and filter by killer
    def __init__(self, subject: "Entity", killer: Optional["Entity"] = None):
        super().__init__(engine=subject.engine, subject=subject)
        self.killer = killer

    def _resolve(self) -> None:
        self.subject.pos = None


class SummonEvent(Event):
    def __init__(self, summoner: "Entity", subject: "Summon"):
        super().__init__(engine=subject.engine, subject=subject)
        self.summoner = summoner

    def _resolve(self) -> None:
        pass  # should maybe set the summon's pos here?
        # If this is doing nothing it means the summoning couldn't be modified or cancelled by the before stage


class HealEvent(Event):
    def __init__(self, subject: "Entity", amount: int):
        super().__init__(engine=subject.engine, subject=subject)
        self.amount = ModInt(amount)

    def _resolve(self) -> None:
        final_heal = max(0, self.amount.value)
        self.subject.hp += final_heal


### TOKENS
class AddTokenEvent(Event):
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
        for modifier in self.subject.modifiers:
            if isinstance(modifier, self.token_class):
                modifier.add(self.amount)
                return
        new_token = self.token_class(self.amount)
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
        for modifiers in self.subject.modifiers:
            if isinstance(modifiers, self.token_class):
                modifiers.remove(self.amount)
                return
