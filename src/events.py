import abc
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Type, Callable, Any, List, TYPE_CHECKING

if TYPE_CHECKING:
    from engine import Engine
    from abilities import Ability
    from modifiers import Modifier
    from entities import Entity


class Event(abc.ABC):
    def __init__(self, engine: "Engine", subject: Optional["Entity"] = None):
        self.engine = engine
        self.subject = subject
        self.canceled = False
        self.state = "BEFORE"

    def resolve(self) -> None:
        self.engine.queue_event(self)

    def process(self) -> None:
        if self.state == "BEFORE":
            self.state = "RESOLVE"
            self.engine.queue_event(self)
            self.engine.router.publish(self, EventPhase.BEFORE)
        elif self.state == "RESOLVE":
            self.state = "AFTER"
            self.engine.queue_event(self)
            if not self.canceled:
                self._resolve()
        elif self.state == "AFTER":
            self.state = "DONE"
            self.engine.router.publish(self, EventPhase.AFTER)

    def _resolve(self) -> None:
        raise NotImplementedError("Events must implement _resolve()")


class ReactionOpportunityEvent(Event):
    def __init__(self, engine: "Engine", triggering_event: Event, phase: str):
        super().__init__(engine=engine)
        self.triggering_event = triggering_event
        self.phase = phase
        self.entity_idx = 0
        self.declined_entities = set()

    def process(self) -> None:
        if self.entity_idx >= len(self.engine.entities):
            return

        entity = self.engine.entities[self.entity_idx]

        if entity.id in self.declined_entities or entity.hp <= 0:
            self.entity_idx += 1
            self.engine.queue_event(self)
            return

        from choices import (
            PlausibleFreeAction,
            _get_plausible_uses_of_ability_at_pos,
            Choice,
        )
        from abilities import ActionCost

        entity_reactions = []
        for react_ability in entity.abilities:
            if (
                react_ability.action_cost == ActionCost.INSTANT
                and react_ability.is_available()
            ):
                plausible_uses = _get_plausible_uses_of_ability_at_pos(
                    actor=entity,
                    engine=self.engine,
                    pos=entity.pos,
                    ability=react_ability,
                    choice_class=PlausibleFreeAction,
                )
                entity_reactions.extend(plausible_uses.values())

        if entity_reactions:
            pass_choice = Choice(features={"pass_reaction": 1})
            choices = tuple(entity_reactions + [pass_choice])

            self.engine.current_reaction_choices = choices
            self.engine.current_reaction_team = entity.team
            self.engine.current_reaction_entity = entity
            self.engine.queue_event(self)
        else:
            self.entity_idx += 1
            self.engine.queue_event(self)


class AbilityUseEvent(Event):
    def __init__(
        self, source: "Entity", ability: "Ability", aiming_result: "AimingResult"
    ):
        super().__init__(engine=source.engine, subject=source)
        self.ability = ability
        self.aiming_result = aiming_result
        self.roll_result = None

    def process(self) -> None:
        if self.state == "BEFORE":
            self.state = "RESOLVE"
            self.engine.queue_event(self)
            self.engine.queue_event(
                ReactionOpportunityEvent(self.engine, self, "before")
            )
            self.engine.router.publish(self, EventPhase.BEFORE)
        elif self.state == "RESOLVE":
            self.state = "AFTER"
            self.engine.queue_event(self)
            if not self.canceled:
                self._resolve()
        elif self.state == "AFTER":
            self.state = "DONE"
            self.engine.queue_event(
                ReactionOpportunityEvent(self.engine, self, "after")
            )
            self.engine.router.publish(self, EventPhase.AFTER)

    def _resolve(self) -> None:
        self.roll_result = self.ability.get_roll_result(
            aiming_result=self.aiming_result, engine=self.engine, source=self.subject
        )
        self.ability.execute_instructions(
            engine=self.engine,
            source=self.subject,
            aiming_result=self.aiming_result,
            roll_result=self.roll_result,
        )


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
