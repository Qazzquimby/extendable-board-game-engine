import abc
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Type, Callable, Any, List, TYPE_CHECKING

from aimings import AimingResult
from schemas import EventDescription
from util import UniqueTuple, EntityId

if TYPE_CHECKING:
    from engine import Engine
    from abilities import Ability
    from modifiers import Modifier
    from entities import Entity
    from choices import Choice


class EventQueue:
    __slots__ = ("_queue", "is_processing")

    def __init__(self):
        self._queue: List["Event"] = []
        self.is_processing = False

    def enqueue_front(self, event: "Event"):
        self._queue.insert(0, event)

    def enqueue(self, event: "Event"):
        if self.is_processing:
            self._queue.insert(0, event)
        else:
            self._queue.append(event)

    def process_one(self, engine: "Engine") -> None:
        if not self._queue:
            return
        self.is_processing = True
        try:
            event = self._queue.pop(0)
            event.process(engine=engine)
        finally:
            self.is_processing = False

    def __hash__(self):
        return hash((tuple(self._queue), self.is_processing))


class Event(abc.ABC):
    __slots__ = ("subject_id", "canceled", "state")

    def __init__(self, subject: Optional["Entity"] = None):
        self.subject_id = subject.id if subject else None
        self.canceled = False
        self.state = "BEFORE"

    def describe(self, engine: "Engine") -> Optional["EventDescription"]:
        """Return an EventDescription for the game log, or None to skip."""
        return None

    def __str__(self):
        return f"{self.__class__.__name__} {self.state}"

    def process(self, engine: "Engine") -> None:
        if self.state == "BEFORE":
            self.state = "RESOLVE"
            engine.event_queue.enqueue(self)
            engine.router.publish(engine=engine, event=self, phase=EventPhase.BEFORE)
        elif self.state == "RESOLVE":
            self.state = "AFTER"
            engine.event_queue.enqueue(self)
            if not self.canceled:
                self._resolve(engine=engine)
        elif self.state == "AFTER":
            self.state = "DONE"
            engine.router.publish(engine=engine, event=self, phase=EventPhase.AFTER)

    def _resolve(self, engine: "Engine") -> None:
        raise NotImplementedError("Events must implement _resolve()")

    def get_hash_info(self):
        return (
            str(self.subject_id),  # str is unique here.
            self.canceled,
            self.state,
            self.__class__.__name__,
            # todo probably need to iterate over __dict__ for subclass params
        )

    def __hash__(self):
        return hash(self.get_hash_info())

    def __eq__(self, other):
        if type(self) != type(other):
            return False
        return hash(self) == hash(other)


class DecisionEvent(Event):
    __slots__ = ()

    def process(self, engine: "Engine") -> None:
        pass  # Handled externally by Engine

    def _resolve(self, engine: "Engine") -> None:
        pass

    @abc.abstractmethod
    def get_choices(self) -> UniqueTuple["Choice"]:
        pass

    @abc.abstractmethod
    def resolve_choice(self, choice: "Choice") -> None:
        pass


class ReactionOpportunityEvent(Event):
    __slots__ = ("triggering_event", "phase", "entity_idx", "declined_entities")

    def __init__(self, triggering_event: Event, phase: str):
        super().__init__()
        self.triggering_event = triggering_event
        self.phase = phase
        self.entity_idx = 0
        self.declined_entities = set()

    def get_hash_info(self):
        return super().get_hash_info() + (
            self.phase,
            self.entity_idx,
            tuple(sorted(self.declined_entities)),
        )

    def get_choices(
        self, engine: "Engine"
    ) -> tuple[UniqueTuple["Choice"], Optional["Entity"]]:
        while self.entity_idx < len(engine.entities):
            entity = engine.entities[self.entity_idx]
            if entity.id in self.declined_entities or entity.hp <= 0:
                self.entity_idx += 1
                continue

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
                    and react_ability.is_available(round_num=engine.round_num)
                ):
                    if react_ability.reaction_condition:
                        if not react_ability.reaction_condition(
                            engine, self.triggering_event, entity, react_ability
                        ):
                            continue

                    plausible_uses = _get_plausible_uses_of_ability_at_pos(
                        actor=entity,
                        engine=engine,
                        pos=entity.pos,
                        ability=react_ability,
                        choice_class=PlausibleFreeAction,
                    )
                    entity_reactions.extend(plausible_uses.values())

            if entity_reactions:
                pass_choice = Choice(features={"pass_reaction": 1})
                pass_choice.actor = entity
                return UniqueTuple(entity_reactions + [pass_choice]), entity
            else:
                self.entity_idx += 1

        return UniqueTuple(), None

    def process(self, engine: "Engine") -> None:
        pass

    def _resolve(self, engine: "Engine") -> None:
        pass


class AbilityUseEvent(Event):
    __slots__ = ("ability", "aiming_result", "roll_result", "is_reaction")

    def __init__(
        self,
        source: "Entity",
        ability: "Ability",
        aiming_result: "AimingResult",
        is_reaction: bool = False,
    ):
        super().__init__(subject=source)
        self.ability = ability
        self.aiming_result = aiming_result
        self.roll_result = None
        self.is_reaction = is_reaction

    def describe(self, engine: "Engine") -> Optional["EventDescription"]:
        source_entity = engine.get_entity_by_id(self.subject_id)
        return EventDescription(
            type="ability_use",
            actor_id=self.subject_id,
            ability_name=self.ability.name,
            source_pos=source_entity.pos if source_entity else None,
        )

    def get_hash_info(self):
        return super().get_hash_info() + (
            self.ability.name,
            self.is_reaction,
        )

    def process(self, engine: "Engine") -> None:
        if self.state == "BEFORE":
            self.state = "RESOLVE"
            engine.event_queue.enqueue(self)
            if not self.is_reaction:
                engine.event_queue.enqueue(
                    ReactionOpportunityEvent(triggering_event=self, phase="before")
                )
            engine.router.publish(engine=engine, event=self, phase=EventPhase.BEFORE)
        elif self.state == "RESOLVE":
            if not self.canceled:
                self.state = "AFTER"
                engine.event_queue.enqueue(self)
                self._resolve(engine=engine)
        elif self.state == "AFTER":
            self.state = "DONE"
            if not self.is_reaction:
                engine.event_queue.enqueue(
                    ReactionOpportunityEvent(triggering_event=self, phase="after")
                )
            engine.router.publish(engine=engine, event=self, phase=EventPhase.AFTER)

    def _resolve(self, engine: "Engine") -> None:
        subject = engine.get_entity_by_id(self.subject_id)
        self.roll_result = self.ability.get_roll_result(
            aiming_result=self.aiming_result, engine=engine, source=subject
        )
        self.ability.execute_instructions(
            engine=engine,
            source=engine.get_entity_by_id(self.subject_id),
            aiming_result=self.aiming_result,
            roll_result=self.roll_result,
        )


class EventPhase(Enum):
    BEFORE = auto()
    AFTER = auto()
    QUERY = auto()


@dataclass(frozen=True, slots=True)
class Subscription:
    modifier: "Modifier"
    event_type: Type
    phase: EventPhase
    only_self: bool
    func: Callable[["Engine", "Event"], None]


class Router:
    __slots__ = ("subscribers",)

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

    def publish(self, engine: "Engine", event: Event, phase: EventPhase) -> None:
        for sub in list(self.subscribers):  # iterate copy
            if sub.event_type == type(event) and sub.phase == phase:
                if sub.only_self:
                    if event.subject_id != sub.modifier.owner_id:
                        continue
                sub.func(engine, event)


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
