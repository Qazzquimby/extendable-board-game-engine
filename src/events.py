import abc
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Type, Callable, Any, List, TYPE_CHECKING

from logger import log
from mod_value import ModInt

if TYPE_CHECKING:
    from engine import Engine
    from abilities import Ability
    from modifiers import Modifier, Token
    from entities import Entity, Summon
    from point import Point
    from grid import Direction


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


@dataclass(frozen=True)
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

    def publish(self, event: Event, phase: EventPhase) -> None:
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
