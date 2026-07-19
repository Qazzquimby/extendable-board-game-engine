from typing import Optional, Type, TYPE_CHECKING
from events import Event
from logger import log
from mod_value import ModInt
from point import Point
from schemas import EventDescription

if TYPE_CHECKING:
    from abilities import Ability
    from engine import Engine
    from entities import Entity, Summon
    from grid import Direction
    from modifiers import Modifier, Token


class ChangeLocationEvent(Event):
    def __init__(self, subject: "Entity", new_pos: Optional["Point"]):
        super().__init__(subject=subject)
        self.new_pos = new_pos

    def describe(self, engine: "Engine") -> Optional[EventDescription]:
        subject = engine.get_entity_by_id(self.subject_id)
        return EventDescription(
            type="move",
            source_id=self.subject_id,
            target_id=self.subject_id,
            target_pos=self.new_pos,
            source_pos=subject.pos if subject else None,
        )

    def _resolve(self, engine: "Engine") -> None:
        subject = engine.get_entity_by_id(self.subject_id)
        subject.pos = self.new_pos

        if subject.pos is None:
            return

        has_more_moves = any(
            isinstance(e, ChangeLocationEvent) and e.subject_id == subject.id
            for e in engine.event_queue._queue
        )

        if has_more_moves:
            return

        occupied = any(
            e
            for e in engine.entities
            if e != subject and e.pos == subject.pos and e.hp > 0
        )
        if not occupied:
            return
        # Shunt to open space
        from collections import deque

        queue = deque([subject.pos])
        visited = {subject.pos}

        while queue:
            curr = queue.popleft()
            is_occupied = any(
                e
                for e in engine.entities
                if e != subject and e.pos == curr and e.hp > 0
            )
            if not is_occupied and curr not in engine.grid.walls:
                subject.pos = curr
                log(
                    f"{subject.name} was displaced to {curr} because their space was occupied."
                )
                break

            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                nx, ny = curr.x + dx, curr.y + dy
                if 0 <= nx < engine.grid.width and 0 <= ny < engine.grid.height:
                    n = Point(nx, ny)
                    if n not in visited:
                        visited.add(n)
                        queue.append(n)


class PushEvent(Event):
    def __init__(self, subject: "Entity", distance: int, direction: "Direction"):
        super().__init__(subject=subject)
        self.distance = ModInt(distance)
        self.direction = direction

    def _resolve(self, engine: "Engine") -> None:
        subject = engine.get_entity_by_id(self.subject_id)
        if not getattr(subject, "pos", None):
            return

        dist = max(0, self.distance.value)
        if dist > 0:
            path = engine.grid.get_push_path(
                subject=subject,
                direction=self.direction,
                distance=dist,
            )
            if path:
                log(f"Pushing {subject.name} to {path[-1]}")
                for point in path:
                    engine.event_queue.enqueue(
                        ChangeLocationEvent(subject=subject, new_pos=point)
                    )


class PullEvent(Event):
    def __init__(self, subject: "Entity", distance: int, toward_point: "Point"):
        super().__init__(subject=subject)
        self.distance = ModInt(distance)
        self.toward_point = toward_point

    def _resolve(self, engine: "Engine") -> None:
        subject = engine.get_entity_by_id(self.subject_id)
        if not getattr(subject, "pos", None):
            return
        dist = max(0, self.distance.value)
        if dist > 0:
            path = engine.grid.get_pull_path(
                subject=subject,
                pull_to=self.toward_point,
                distance=dist,
            )
            if path:
                # Filter out positions that are already occupied by another entity
                occupied = {
                    e.pos
                    for e in engine.living_entities
                    if e.id != subject.id and e.pos
                }
                final_path = [p for p in path if p not in occupied]
                if final_path:
                    log(f"Pulling {subject.name} to {final_path[-1]}")
                    for point in final_path:
                        engine.event_queue.enqueue(
                            ChangeLocationEvent(subject=subject, new_pos=point)
                        )


class DeployEvent(Event):
    def __init__(self, subject: "Entity"):
        super().__init__(subject=subject)

    def _resolve(self, engine: "Engine") -> None:
        pass


class TurnStartEvent(Event):
    def __init__(self, subject: "Entity"):
        super().__init__(subject=subject)

    def _resolve(self, engine: "Engine") -> None:
        subject = engine.get_entity_by_id(self.subject_id)
        engine.current_turn_hero.start_turn()


class TurnEndEvent(Event):
    def __init__(self, subject: "Entity"):
        super().__init__(subject=subject)

    def _resolve(self, engine: "Engine") -> None:
        subject = engine.get_entity_by_id(self.subject_id)
        for ability in subject.abilities:
            if ability.taps:
                if not ability.tapped_this_turn:
                    ability.is_tapped = False
                ability.tapped_this_turn = False


class RoundStartEvent(Event):
    def __init__(self):
        super().__init__()

    def _resolve(self, engine: "Engine") -> None:
        engine.round_num += 1


class DamageEvent(Event):
    def __init__(
        self,
        source: Optional["Entity"],
        subject: "Entity",
        amount: int | ModInt,
        ability: Optional["Ability"] = None,
    ):
        super().__init__(subject=subject)
        self.source = source
        self.amount = ModInt(amount)
        self.ability = ability

    def describe(self, engine: "Engine") -> Optional[EventDescription]:
        target = engine.get_entity_by_id(self.subject_id)
        return EventDescription(
            type="damage",
            source_id=self.source.id if self.source else None,
            target_id=self.subject_id,
            amount=self.amount.value,
            target_pos=target.pos if target else None,
            source_pos=self.source.pos if self.source else None,
        )

    def _resolve(self, engine: "Engine") -> None:
        from queries import QueryVulnerable, QueryDamageBuff

        subject = engine.get_entity_by_id(self.subject_id)
        if subject.has_armor(engine=engine):
            self.amount.add(-1)

        # Query damage amplification
        q_vuln = QueryVulnerable(subject=subject)
        q_vuln.resolve(engine=engine)
        vuln_pct = int(q_vuln.result)
        if vuln_pct > 0 and self.source:
            bonus = (self.amount.value * vuln_pct) // 100
            if bonus > 0:
                self.amount.add(bonus)

        if self.source:
            q_buff = QueryDamageBuff(subject=self.source)
            q_buff.resolve(engine=engine)
            buff_pct = int(q_buff.result)
            if buff_pct > 0:
                bonus = (self.amount.value * buff_pct) // 100
                if bonus > 0:
                    self.amount.add(bonus)

        final_damage = max(0, self.amount.value)
        old_hp = subject.hp
        new_hp = max(0, subject.hp - final_damage)
        subject.hp = new_hp

        source_name = self.source.name if self.source else "Environment"
        with log(f"{source_name} dealt {final_damage} damage to {subject.name}."):
            if subject.hp <= 0 and old_hp > 0:
                engine.event_queue.enqueue(
                    DeathEvent(subject=subject, killer=self.source)
                )


class DeathEvent(Event):
    # For on-kill use on-death and filter by killer
    def __init__(self, subject: "Entity", killer: Optional["Entity"] = None):
        super().__init__(subject=subject)
        self.killer_id = killer.id if killer else None

    def describe(self, engine: "Engine") -> Optional[EventDescription]:
        target = engine.get_entity_by_id(self.subject_id)
        return EventDescription(
            type="death",
            target_id=self.subject_id,
            source_id=self.killer_id,
            target_pos=target.pos if target else None,
        )

    def _resolve(self, engine: "Engine") -> None:
        subject = engine.get_entity_by_id(self.subject_id)
        log(f"{subject.name} died.")
        subject.pos = None


class SummonEvent(Event):
    def __init__(self, summoner: "Entity", subject: "Summon"):
        super().__init__(subject=subject)
        self.summoner_id = summoner.id if summoner else None

    def _resolve(self, engine: "Engine") -> None:
        pass  # should maybe set the summon's pos here?
        # If this is doing nothing it means the summoning couldn't be modified or cancelled by the before stage


class HealEvent(Event):
    def __init__(self, subject: "Entity", amount: int | ModInt):
        super().__init__(subject=subject)
        self.amount = ModInt(amount)

    def describe(self, engine: "Engine") -> Optional[EventDescription]:
        target = engine.get_entity_by_id(self.subject_id)
        return EventDescription(
            type="heal",
            target_id=self.subject_id,
            amount=self.amount.value,
            target_pos=target.pos if target else None,
        )

    def _resolve(self, engine: "Engine") -> None:
        final_heal = max(0, self.amount.value)
        subject = engine.get_entity_by_id(self.subject_id)
        subject.hp = min(subject.max_hp, subject.hp + final_heal)
        log(f"{subject.name} healed {final_heal} HP.")


class AddModifierEvent(Event):
    def __init__(
        self,
        subject: "Entity",
        modifier_class: Type["Modifier"],
        modifier_kwargs: dict,
    ):
        super().__init__(subject=subject)
        self.modifier_class = modifier_class
        self.modifier_kwargs = modifier_kwargs

    def _resolve(self, engine: "Engine") -> None:
        subject = engine.get_entity_by_id(self.subject_id)
        log(f"{subject.name} gained {self.modifier_class.__name__}.")
        subject.add_modifier(
            engine=engine, modifier=self.modifier_class(**self.modifier_kwargs)
        )


class RemoveModifierEvent(Event):
    def __init__(self, subject: "Entity", modifier_class: Type["Modifier"]):
        super().__init__(subject=subject)
        self.modifier_class = modifier_class

    def _resolve(self, engine: "Engine"):
        subject = engine.get_entity_by_id(self.subject_id)
        log(f"{subject.name} lost {self.modifier_class.__name__}.")
        existing_modifier = next(
            (
                mod
                for mod in subject.modifiers
                if mod.name == self.modifier_class.__name__
            ),
            None,
        )
        if existing_modifier:
            subject.remove_modifier(engine=engine, modifier=existing_modifier)


class AddTokenEvent(Event):
    def __init__(
        self,
        subject: "Entity",
        token_class: Type["Token"],
        amount: int = 1,
        token_kwargs: Optional[dict] = None,
    ):
        super().__init__(subject=subject)
        self.token_class = token_class
        self.amount = amount
        if not token_kwargs:
            token_kwargs = {}
        self.token_kwargs = token_kwargs

    def _resolve(self, engine: "Engine"):
        subject = engine.get_entity_by_id(self.subject_id)
        log(f"{subject.name} gained {self.amount} {self.token_class.__name__}.")
        for modifier in subject.modifiers:
            if isinstance(modifier, self.token_class):
                modifier.add(self.amount)
                return
        new_token = self.token_class(amount=self.amount, **self.token_kwargs)
        subject.add_modifier(engine=engine, modifier=new_token)


class RemoveTokenEvent(Event):
    def __init__(
        self,
        subject: "Entity",
        token_class: Type["Token"],
        amount: int,
    ):
        super().__init__(subject=subject)
        self.token_class = token_class
        self.amount = amount

    def _resolve(self, engine: "Engine"):
        subject = engine.get_entity_by_id(self.subject_id)
        log(f"{subject.name} lost {self.amount} {self.token_class.__name__}.")
        for modifier in subject.modifiers:
            if isinstance(modifier, self.token_class):
                modifier.remove(
                    engine=engine, amount=self.amount
                )  # safe because is token
                return
