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


def blink_reaction_condition(
    engine: "Engine", event: object, actor: "Entity", ability: "Ability"
) -> bool:
    """React when Tracer is targeted by an enemy attack that deals damage.

    If any of the triggering event's target/included points contain the actor
    (Tracer), she can blink to an empty space within range 3 to avoid the attack.
    Only triggers for abilities that deal damage (have DamageInstruction).
    """
    from events import AbilityUseEvent
    from instruction_library import DamageInstruction
    if not isinstance(event, AbilityUseEvent):
        return False
    subject = engine.get_entity_by_id(event.subject_id)
    if subject.team == actor.team:
        return False

    # Only react to damaging abilities
    has_damage = any(
        isinstance(inst, DamageInstruction) for inst in event.ability.instructions
    )
    if not has_damage:
        return False

    # Check if actor is in the trigger's target/included points
    trigger_targets = []
    if event.aiming_result.sub_aimings:
        for res in event.aiming_result.sub_aimings.values():
            trigger_targets.extend(res.target_points)
            trigger_targets.extend(res.included_points)
    elif event.aiming_result:
        trigger_targets.extend(event.aiming_result.target_points)
        trigger_targets.extend(event.aiming_result.included_points)

    if actor.pos not in trigger_targets:
        return False

    # Verify there's at least one valid empty space to blink to
    reachable = engine.grid.get_movable_spaces(
        engine=engine, actor=actor, max_movement=3
    )
    occupied = {e.pos for e in engine.living_entities if e.pos is not None}
    viable = [p for p in reachable if p != actor.pos and p not in occupied]
    return len(viable) > 0


class Blink(Ability):
    def __init__(self, owner_id: str):
        super().__init__(
            name="Blink",
            text="3/Game, Instant +2: Teleport up to 3.",
            aiming=TargetPoint(in_range=3, empty=True),
            instructions=[
                TeleportInstruction(destination=lambda ctx: ctx.subject_point, teleport_source=True)
            ],
            action_cost=ActionCost.INSTANT,
            instant_speed=2,
            max_charges=3,
            owner_id=owner_id,
            reaction_condition=blink_reaction_condition,
            requires_target=False,
        )

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        from abilities import displacement_value, score_damage
        target_pt = aiming_result.target_points[0]

        # Base priority: displacement value (how much movement this saves)
        base = displacement_value(actor, pos, target_pt, engine)

        # If there's a reaction trigger event, compute dodge value
        trigger = getattr(engine, "_reaction_trigger_event", None)
        if trigger is not None:
            from events import AbilityUseEvent
            if isinstance(trigger, AbilityUseEvent):
                # How much damage would this dodge?
                total_damage = 0
                from instruction_library import DamageInstruction
                for inst in trigger.ability.instructions:
                    if isinstance(inst, DamageInstruction):
                        dmg = inst.amount if isinstance(inst.amount, int) else 0
                        total_damage += dmg

                # Check if blinking leaves the attacker's range
                subject = engine.get_entity_by_id(trigger.subject_id)
                if subject and subject.pos:
                    attack_in_range = getattr(trigger.ability.aiming, "in_range", None)
                    if attack_in_range is not None:
                        new_dist = target_pt.get_distance(subject.pos)
                        if new_dist > attack_in_range:
                            # Dodged! Add value proportionate to damage prevented
                            dodge_bonus = score_damage(total_damage, actor.hp) * 0.8
                            base += dodge_bonus
                        else:
                            # Still in range but displacement has some value
                            # Add small bonus for moving away from attacker
                            old_dist = pos.get_distance(subject.pos)
                            if new_dist > old_dist:
                                base += 0.5 * (new_dist - old_dist)
                    elif total_damage > 0:
                        # No range info but it deals damage — still worth dodging
                        base += score_damage(total_damage, actor.hp) * 0.5

        # Resource conservation: if few charges remain and game is early, reduce priority
        if self.charges is not None and self.max_charges and self.max_charges > 0:
            charges_used = self.max_charges - self.charges
            charges_left = self.charges
            # More penalty for limited charges early in the game
            game_progress = engine.round_num / 7.0  # 7 rounds max
            conservation_penalty = max(0, (1.0 - game_progress) * (1.0 / charges_left) if charges_left > 0 else 0)
            base -= conservation_penalty

        return max(0.1, base)


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
        def no_reaction(*args, **kwargs):
            return False

        recall = Recall(owner_id=self.id)
        recall.reaction_condition = no_reaction
        self.abilities.append(recall)
        self.abilities.append(PulseBomb(owner_id=self.id))
