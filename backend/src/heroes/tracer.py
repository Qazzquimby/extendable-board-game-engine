from dataclasses import dataclass
from typing import Optional, Union
from aimings import (
    TargetEntity,
    TargetPoint,
    TargetSelf,
    AimingResult,
    MultipleAimingResults,
)
from engine import Engine
from entities import Hero, Entity, Marker
from abilities import (
    Ability,
    ActionCost,
    Instruction,
    ActionContext,
)
from instruction_library import DamageInstruction, TeleportInstruction
from events import after, before, query
from event_library import (
    TurnEndEvent,
    TurnStartEvent,
    DamageEvent,
    HealEvent,
    ChangeLocationEvent,
)
from modifiers import Modifier
from point import Point
from queries import QueryDefense
from util import EntityId
from valence import Valence


class RecallTracker(Modifier):
    def __init__(self):
        self.recorded_hp = 6
        self.recorded_pos = None

    @after(TurnEndEvent)
    def record_state(self, engine: "Engine", event: TurnEndEvent):
        if event.subject_id == self.owner_id:
            owner = engine.get_entity_by_id(self.owner_id)
            self.recorded_hp = owner.hp
            self.recorded_pos = owner.pos


@dataclass(kw_only=True)
class RecallInstruction(Instruction):
    valence: Valence = Valence.GOOD

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        owner = engine.get_entity_by_id(ctx.source_id)
        tracker = owner.get_modifier(RecallTracker)
        if tracker:
            if tracker.recorded_hp > owner.hp:
                engine.event_queue.enqueue(
                    HealEvent(subject=owner, amount=tracker.recorded_hp - owner.hp)
                )
            elif tracker.recorded_hp < owner.hp:
                owner.hp = tracker.recorded_hp

            if tracker.recorded_pos:
                from collections import deque

                queue = deque([tracker.recorded_pos])
                visited = {tracker.recorded_pos}
                best_pos = None
                while queue:
                    curr = queue.popleft()
                    if not engine.entity_at(curr) and curr not in engine.grid.walls:
                        best_pos = curr
                        break
                    for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                        nx, ny = curr.x + dx, curr.y + dy
                        if 0 <= nx < engine.grid.width and 0 <= ny < engine.grid.height:
                            n = Point(nx, ny)
                            if n not in visited:
                                visited.add(n)
                                queue.append(n)
                if best_pos:
                    engine.event_queue.enqueue(
                        ChangeLocationEvent(subject=owner, new_pos=best_pos)
                    )


# todo prioritize reactions


class Recall(Ability):
    def __init__(self, owner_id: str):
        super().__init__(
            name="Recall",
            text="1/Game, Instant +3: Reset your health to what it was at the end of your last turn. Teleport as close as possible to where you were at the end of your last turn.",
            aiming=TargetSelf(),
            instructions=[RecallInstruction()],
            action_cost=ActionCost.INSTANT,
            instant_speed=3,
            max_charges=1,
            owner_id=owner_id,
        )

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        tracker = actor.get_modifier(RecallTracker)
        if not tracker:
            return 0.0
        hp_lost = tracker.recorded_hp - actor.hp
        if hp_lost > 0:
            return 5.0 + hp_lost
        return 1.0


class Blink(Ability):
    def __init__(self, owner_id: str):
        super().__init__(
            name="Blink",
            text="3/Game, Instant +2: Teleport up to 3.",
            aiming=TargetPoint(in_range=3, empty=True),
            instructions=[
                TeleportInstruction(destination=lambda ctx: ctx.subject_point)
            ],
            action_cost=ActionCost.INSTANT,
            instant_speed=2,
            max_charges=3,
            owner_id=owner_id,
        )

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        target_pt = aiming_result.target_points[0]
        enemies = [e for e in engine.living_entities if e.team != actor.team]
        if not enemies:
            return 1.0
        dist_to_enemies = min([target_pt.get_distance(e.pos) for e in enemies])
        return dist_to_enemies * 0.5


class PulsePistols(Ability):
    def __init__(self, owner_id: EntityId):
        super().__init__(
            name="Pulse Pistols",
            text="Range 1, 4dmg.",
            aiming=TargetEntity(in_range=1),
            instructions=[DamageInstruction(amount=4)],
            is_default=True,
            owner_id=owner_id,
        )


class PulseBombAttached(Modifier):
    def __init__(self, source_id: EntityId):
        self.source_id = source_id


class PulseBombMarker(Marker):
    def __init__(self, engine: "Engine", pos: Point, team: int, source_id: EntityId):
        super().__init__(
            engine=engine, name="Pulse Bomb", pos=pos, team=team, summoner_id=source_id
        )
        self.source_id = source_id


class PulseBombDetonator(Modifier):
    @before(TurnStartEvent)
    def detonate(self, engine: "Engine", event: TurnStartEvent):
        if event.subject_id == self.owner_id:
            owner = engine.get_entity_by_id(self.owner_id)

            detonated = False
            for entity in engine.living_entities:
                mod = entity.get_modifier(PulseBombAttached)
                if mod and mod.source_id == self.owner_id:
                    self._explode(engine, owner, entity.pos)
                    entity.remove_modifier(engine, mod)
                    detonated = True

            for marker in list(engine.markers):
                if (
                    isinstance(marker, PulseBombMarker)
                    and marker.source_id == self.owner_id
                ):
                    self._explode(engine, owner, marker.pos)
                    engine.markers.remove(marker)
                    detonated = True

            if detonated:
                owner.remove_modifier(engine, self)

    def _explode(self, engine: "Engine", owner: "Entity", pos: Point):
        points_in_burst = engine.grid.get_points_in_range(pos, 1)
        for pt in points_in_burst:
            target = engine.entity_at(pt)
            if target:
                if pt == pos:
                    engine.event_queue.enqueue(
                        DamageEvent(source=owner, subject=target, amount=9)
                    )
                else:
                    engine.event_queue.enqueue(
                        DamageEvent(source=owner, subject=target, amount=3)
                    )


@dataclass(kw_only=True)
class PulseBombInstruction(Instruction):
    valence: Valence = Valence.BAD

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        target = engine.entity_at(ctx.subject_point)
        owner = engine.get_entity_by_id(ctx.source_id)

        if not owner.get_modifier(PulseBombDetonator):
            owner.add_modifier(engine, PulseBombDetonator())

        if target and ctx.is_hit:
            target.add_modifier(engine, PulseBombAttached(source_id=ctx.source_id))
        else:
            PulseBombMarker(
                engine=engine,
                pos=ctx.subject_point,
                team=owner.team,
                source_id=ctx.source_id,
            )


class PulseBombDefenseModifier(Modifier):
    @query(QueryDefense)
    def add_defense(self, engine: "Engine", event: QueryDefense):
        if (
            event.ability
            and event.ability.name == "Pulse Bomb"
            and event.attack_source
            and event.attack_source.id == self.owner_id
        ):
            event.result += 2


class PulseBomb(Ability):
    def __init__(self, owner_id: str):
        super().__init__(
            name="Pulse Bomb",
            text="Ultimate 5: Target a space in range 1. If there's a character in the space, attach the pulse bomb to them with +2def. If it doesn't attach to someone, it drops in that space. At the start of your next turn, destroy the pulse bomb. It deals 9dmg to anyone in its space and 3dmg to anyone else in burst 1.",
            aiming=TargetPoint(in_range=1),
            instructions=[PulseBombInstruction()],
            is_ultimate=True,
            ultimate_turn=5,
            owner_id=owner_id,
        )

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        target_pt = aiming_result.target_points[0]
        target = engine.entity_at(target_pt)
        if target and target.team != actor.team:
            return 10.0
        return 2.0


class Tracer(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Tracer", hp=6, speed=4, pos=pos, team=team
        )

        self.add_modifier(engine, RecallTracker())
        self.add_modifier(engine, PulseBombDefenseModifier())

        self.abilities.append(PulsePistols(owner_id=self.id))
        self.abilities.append(Blink(owner_id=self.id))
        self.abilities.append(Recall(owner_id=self.id))
        self.abilities.append(PulseBomb(owner_id=self.id))
