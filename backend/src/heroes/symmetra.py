from dataclasses import dataclass, field
from typing import Union

from abilities import (
    Ability,
    ActionCost,
    ActionContext,
    Instruction,
)
from instruction_library import DamageInstruction, TeleportInstruction
from aimings import (
    TargetEntity,
    MultipleAiming,
    TargetPoint,
    TargetSelf,
    AimingResult,
    MultipleAimingResults,
)
from engine import Engine
from entities import (
    Entity,
    Object,
    Hero,
    Marker,
)
from modifiers import (
    Modifier,
    SummonModifier,
    Token,
    SlowToken,
)
from events import after
from event_library import (
    TurnStartEvent,
    TurnEndEvent,
    DamageEvent,
    SummonEvent,
    ChangeLocationEvent,
    DeathEvent,
    HealEvent,
)
from point import Point
from valence import Valence


# region Photon Orb
class PhotonOrb(Ability):
    def __init__(self, owner_id: str):
        super().__init__(
            name="Photon Orb",
            text="Range 4: +2 miss, 4dmg.",
            aiming=TargetEntity(in_range=4),
            instructions=[DamageInstruction(amount=4)],
            is_default=True,
            defense=2,
            owner_id=owner_id,
        )

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        return 2.0


# endregion


# region Photon Beam


class PhotonBeamToken(Token):
    valence = Valence.BAD


@dataclass(kw_only=True)
class PhotonBeamManager(Modifier):
    valence = Valence.GOOD
    entities_hit_this_turn: set = field(default_factory=set, init=False)

    @after(TurnStartEvent)
    def clear_tracker_on_turn_start(self, engine: "Engine", event: TurnStartEvent):
        self.entities_hit_this_turn.clear()

    @after(TurnEndEvent)
    def fade_tokens_on_turn_end(self, engine: "Engine", event: TurnEndEvent):
        for entity in engine.living_entities:
            if (
                entity.get_token_count(engine, PhotonBeamToken) > 0
                and entity not in self.entities_hit_this_turn
            ):
                entity.remove_token(engine, PhotonBeamToken, amount=1)


@dataclass(kw_only=True)
class PhotonBeamDamageInstruction(Instruction):
    valence: Valence = Valence.BAD

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        subject = engine.entity_at(ctx.subject_point)
        if subject:
            token_count = subject.get_token_count(engine, PhotonBeamToken)
            amount = 2 + 2 * token_count
            if ctx.is_crit:
                amount *= 2
            source = engine.get_entity_by_id(ctx.source_id)
            engine.event_queue.enqueue(
                DamageEvent(
                    source=source,
                    subject=subject,
                    amount=amount,
                    ability=ctx.ability,
                )
            )


@dataclass(kw_only=True)
class GivePhotonBeamTokenAndTrack(Instruction):
    tracker: PhotonBeamManager
    valence: Valence = Valence.BAD

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        subject = engine.entity_at(ctx.subject_point)
        if subject:
            subject.add_token(engine, PhotonBeamToken)
            self.tracker.entities_hit_this_turn.add(subject)


class PhotonBeam(Ability):
    def __init__(self, owner_id: str, tracker: PhotonBeamManager):
        super().__init__(
            name="Photon Beam",
            aiming=TargetEntity(in_range=2),
            instructions=[
                PhotonBeamDamageInstruction(),
                GivePhotonBeamTokenAndTrack(tracker=tracker),
            ],
            is_default=True,
            owner_id=owner_id,
        )

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        target = engine.entity_at(aiming_result.target_points[0])
        if not target:
            return 0.0
        token_count = target.get_token_count(engine, PhotonBeamToken)
        return 2.0 + token_count * 2.0


# endregion


# region Sentry Turret
@dataclass(kw_only=True)
class SentryTurretManager(Modifier):
    valence = Valence.GOOD
    targets_hit_this_activation: set = field(default_factory=set, init=False)

    # todo should separate turn and activation. Hero and their summons activate on same turn.
    @after(TurnStartEvent)
    def clear_on_turn_start(self, engine: "Engine", event: TurnStartEvent):
        self.targets_hit_this_activation.clear()


@dataclass(kw_only=True)
class TurretAttack(SummonModifier):
    valence = Valence.GOOD

    @after(TurnStartEvent)
    def fire_at_nearest(self, engine: "Engine", event: TurnStartEvent):
        owner = engine.get_entity_by_id(self.owner_id)
        if not owner or owner.pos is None:
            return
        # Only fire if it's the summoner's turn start
        try:
            summoner = summoner = engine.get_entity_by_id(owner.summoner_id)
        except AttributeError:
            print("Turret attack not on a summon")
            return
        if event.subject_id != summoner.id:
            return

        manager = summoner.get_modifier(SentryTurretManager)
        if not manager:
            return

        # Find nearest enemy in range 2
        enemies = [
            e
            for e in engine.living_entities
            if e.team != owner.team and e.pos is not None and owner.distance_to(e) <= 2
        ]
        if enemies:
            nearest = min(enemies, key=lambda e: owner.distance_to(e))
            if nearest in manager.targets_hit_this_activation:
                nearest.add_token(engine, SlowToken, amount=1)
            manager.targets_hit_this_activation.add(nearest)
            engine.event_queue.enqueue(
                DamageEvent(
                    source=owner,
                    subject=nearest,
                    amount=1,
                )
            )


class SentryTurret(Object):
    def __init__(self, engine: Engine, pos: Point, team: int, summoner: Entity):
        super().__init__(
            engine=engine,
            name="Sentry Turret",
            hp=1,
            pos=pos,
            team=team,
            summoner=summoner,
        )
        self.add_modifier(engine, TurretAttack())
        from entities import DoNothingAbility
        self.abilities.append(DoNothingAbility(name="Do Nothing", aiming=TargetSelf(), instructions=[], owner_id=self.id))


@dataclass(kw_only=True)
class CreateSentryTurretInstruction(Instruction):
    valence: Valence = Valence.GOOD

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        source = engine.get_entity_by_id(ctx.source_id)
        for point in ctx.target_points:
            if not engine.entity_at(point):
                SentryTurret(
                    engine=engine,
                    pos=point,
                    team=source.team,
                    summoner=source,
                )


class CreateSentryTurret(Ability):
    def __init__(self, owner_id: str):
        super().__init__(
            name="Create Sentry Turret",
            aiming=MultipleAiming(
                [TargetPoint(in_range=None, empty=True) for _i in range(3)]
            ),
            instructions=[CreateSentryTurretInstruction()],
            max_charges=1,
            requires_target=False,
            owner_id=owner_id,
        )

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        return 5.0


# endregion


# region Teleporter
@dataclass(kw_only=True)
class TeleporterModifier(Modifier):
    valence = Valence.GOOD

    @after(ChangeLocationEvent)
    def on_location_change(self, engine: "Engine", event: ChangeLocationEvent):
        owner = engine.get_entity_by_id(self.owner_id)
        if not owner or owner.pos is None:
            return

        # Find the other teleporter of the same team/summoner
        other_teleporter = None
        for entity in engine.living_entities:
            if (
                isinstance(entity, Teleporter)
                and entity != owner
                and entity.team == owner.team
            ):
                other_teleporter = entity
                break

        for entity in engine.living_entities:
            on_teleporter = (
                (entity.pos == owner.pos) if (entity.pos is not None) else False
            )
            existing_ability = next(
                (a for a in entity.abilities if a.name == "Use Teleporter"), None
            )

            if on_teleporter and other_teleporter and other_teleporter.pos is not None:
                if not existing_ability:
                    teleport_ability = Ability(
                        name="Use Teleporter",
                        aiming=TargetSelf(),
                        instructions=[
                            TeleportInstruction(destination=other_teleporter.pos)
                        ],
                        action_cost=ActionCost.FREE,
                        owner_id=entity.id,
                    )
                    entity.abilities.append(teleport_ability)
            else:
                on_other = (
                    (entity.pos == other_teleporter.pos)
                    if (
                        other_teleporter
                        and other_teleporter.pos is not None
                        and entity.pos is not None
                    )
                    else False
                )
                if not on_teleporter and not on_other and existing_ability:
                    entity.abilities.remove(existing_ability)


class Teleporter(Object):
    def __init__(self, engine: Engine, pos: Point, team: int, summoner: Entity):
        super().__init__(
            engine=engine,
            name="Teleporter",
            hp=8,
            pos=pos,
            team=team,
            summoner=summoner,
        )
        self.add_modifier(engine, TeleporterModifier())
        from entities import DoNothingAbility
        from aimings import TargetSelf
        self.abilities.append(DoNothingAbility(name="Do Nothing", aiming=TargetSelf(), instructions=[], owner_id=self.id))


@dataclass(kw_only=True)
class CreateTeleporterInstruction(Instruction):
    valence: Valence = Valence.GOOD

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        source = engine.get_entity_by_id(ctx.source_id)
        for point in ctx.target_points:
            if not engine.entity_at(point):
                Teleporter(
                    engine=engine,
                    pos=point,
                    team=source.team,
                    summoner=source,
                )


class CreateTeleporter(Ability):
    def __init__(self, owner_id: str):
        super().__init__(
            name="Create Teleporter",
            aiming=MultipleAiming(
                [
                    TargetPoint(in_range=1, empty=True),
                    TargetPoint(in_range=None, empty=True),
                ]
            ),
            instructions=[CreateTeleporterInstruction()],
            max_charges=1,
            requires_target=False,
            owner_id=owner_id,
        )

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        return 3.0


# endregion


# region Shield Generator
@dataclass(kw_only=True)
class ShieldGeneratorModifier(Modifier):
    valence = Valence.GOOD

    @after(SummonEvent, only_self=False)
    def on_summon(self, engine: "Engine", event: SummonEvent):
        owner = engine.get_entity_by_id(self.owner_id)
        spawned_entity = engine.get_entity_by_id(event.subject_id)
        if spawned_entity.team == owner.team and isinstance(spawned_entity, Hero):
            spawned_entity.max_hp += 4
            engine.event_queue.enqueue(HealEvent(subject=spawned_entity, amount=4))

    @after(DeathEvent)
    def on_death(self, engine: "Engine", event: DeathEvent):
        subject = engine.get_entity_by_id(event.subject_id)
        for entity in engine.living_entities:
            if entity.team == subject.team and isinstance(entity, Hero):
                entity.max_hp -= 4
                entity.hp -= 4
                if entity.hp <= 0:
                    engine.event_queue.enqueue(DeathEvent(subject=entity))


class ShieldGenerator(Object):
    def __init__(self, engine: Engine, pos: Point, team: int, summoner: Entity):
        super().__init__(
            engine=engine,
            name="Shield Generator",
            hp=4,
            pos=pos,
            team=team,
            summoner=summoner,
        )
        self.add_modifier(engine, ShieldGeneratorModifier())
        from entities import DoNothingAbility
        from aimings import TargetSelf
        self.abilities.append(DoNothingAbility(name="Do Nothing", aiming=TargetSelf(), instructions=[], owner_id=self.id))


@dataclass(kw_only=True)
class CreateShieldGeneratorInstruction(Instruction):
    valence: Valence = Valence.GOOD

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        source = engine.get_entity_by_id(ctx.source_id)
        for point in ctx.target_points:
            if not engine.entity_at(point):
                ShieldGenerator(
                    engine=engine,
                    pos=point,
                    team=source.team,
                    summoner=source,
                )
                for entity in engine.living_entities:
                    if entity.team == source.team and entity.name != "Shield Generator":
                        entity.max_hp += 4
                        engine.event_queue.enqueue(HealEvent(subject=entity, amount=4))


class CreateShieldGenerator(Ability):
    def __init__(self, owner_id: str):
        super().__init__(
            name="Create Shield Generator",
            aiming=TargetPoint(in_range=1, empty=True),
            instructions=[CreateShieldGeneratorInstruction()],
            is_ultimate=True,
            ultimate_turn=3,
            requires_target=False,
            owner_id=owner_id,
        )

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        return 10.0


# endregion


# region Floating Barrier
class FloatingBarrierModifier(Modifier):
    valence = Valence.GOOD

    def __init__(self, direction: Point):
        self.direction = direction

    def blocks_los_for(self, engine: "Engine", viewer: "Entity") -> bool:
        owner = next(
            (m for m in getattr(engine, "markers", []) if m.id == self.owner_id), None
        )
        if not owner:
            return False
        creator = (
            engine.get_entity_by_id(owner.summoner_id)
            if hasattr(owner, "summoner_id")
            else None
        )
        if creator and viewer.team != creator.team:
            return True
        return False

    @after(TurnStartEvent)
    def move_forward(self, engine: "Engine", event: TurnStartEvent):
        owner = next(
            (m for m in getattr(engine, "markers", []) if m.id == self.owner_id), None
        )
        if not owner or not owner.pos:
            return
        creator = (
            engine.get_entity_by_id(owner.summoner_id)
            if hasattr(owner, "summoner_id")
            else None
        )
        if creator and event.subject_id == creator.id:
            for _ in range(2):
                next_pos = owner.pos + self.direction
                if (
                    0 <= next_pos.x < engine.grid.width
                    and 0 <= next_pos.y < engine.grid.height
                ):
                    if not engine.grid.is_movement_blocked(owner.pos, next_pos):
                        owner.pos = next_pos


@dataclass(kw_only=True)
class CreateFloatingBarrierInstruction(Instruction):
    valence: Valence = Valence.GOOD

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        source = engine.get_entity_by_id(ctx.source_id)
        target_point = ctx.target_points[0]
        raw_dir = Point(target_point.x - source.pos.x, target_point.y - source.pos.y)
        dx = 1 if raw_dir.x > 0 else (-1 if raw_dir.x < 0 else 0)
        dy = 1 if raw_dir.y > 0 else (-1 if raw_dir.y < 0 else 0)
        direction = Point(dx, dy)

        marker = Marker(
            engine=engine, name="Floating Barrier", pos=target_point, team=source.team, summoner_id=source.id
        )
        mod = FloatingBarrierModifier(direction=direction)
        mod.owner_id = marker.id
        marker.modifiers.append(mod)
        engine.router.subscribe(mod)


class CreateFloatingBarrier(Ability):
    def __init__(self, owner_id: str):
        super().__init__(
            name="Create Floating Barrier",
            text="""1/game:
Create a **Floating Barrier** marker in an edge in range 1, facing away from you.
It has:
  This blocks line of sight for the creator's enemies.
  At start of creator's activation: This moves forward 2 spaces.""",
            aiming=TargetPoint(in_range=1, empty=True),
            instructions=[CreateFloatingBarrierInstruction()],
            max_charges=1,
            requires_target=False,
            owner_id=owner_id,
        )

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        return 4.0


# endregion


# region Photon Barrier
class BlocksLOSModifier(Modifier):
    valence = Valence.GOOD

    def blocks_los_for(self, engine: "Engine", viewer: "Entity") -> bool:
        owner = engine.get_entity_by_id(self.owner_id)
        if not owner:
            return False
        creator = (
            engine.get_entity_by_id(owner.summoner_id)
            if hasattr(owner, "summoner_id")
            else None
        )
        if creator and viewer.team != creator.team:
            return True
        return False


class PhotonBarrier(Object):
    def __init__(self, engine: Engine, pos: Point, team: int, summoner: Entity):
        super().__init__(
            engine=engine,
            name="Photon Barrier",
            hp=12,
            pos=pos,
            team=team,
            summoner=summoner,
        )
        self.add_modifier(engine, BlocksLOSModifier())


@dataclass(kw_only=True)
class CreatePhotonBarrierInstruction(Instruction):
    valence: Valence = Valence.GOOD

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        source = engine.get_entity_by_id(ctx.source_id)
        center = ctx.target_points[0]
        dir_pt = ctx.target_points[1]

        dx = dir_pt.x - center.x
        dy = dir_pt.y - center.y

        if abs(dx) > abs(dy):
            points = [Point(x, center.y) for x in range(engine.grid.width)]
        else:
            points = [Point(center.x, y) for y in range(engine.grid.height)]

        for pt in points:
            if not engine.entity_at(pt):
                PhotonBarrier(engine=engine, pos=pt, team=source.team, summoner=source)


class CreatePhotonBarrier(Ability):
    def __init__(self, owner_id: str):
        super().__init__(
            name="Create Photon Barrier",
            text="""*Ultimate* 4:
Choose any edge across the map.
Create a **Photon Barrier** object along that edge.
It has:
  12hp.
  This blocks line of sight for the creator's enemies.""",
            aiming=MultipleAiming(
                [
                    TargetPoint(in_range=None, empty=True),
                    TargetPoint(in_range=None, empty=False),
                ]
            ),
            instructions=[CreatePhotonBarrierInstruction()],
            is_ultimate=True,
            ultimate_turn=4,
            requires_target=False,
            owner_id=owner_id,
        )

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        return 8.0


# endregion


class Symmetra(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Symmetra", hp=8, speed=3, pos=pos, team=team
        )
        photon_beam_manager = PhotonBeamManager()
        self.add_modifier(engine, photon_beam_manager)
        self.abilities.append(PhotonBeam(owner_id=self.id, tracker=photon_beam_manager))

        self.abilities.append(PhotonOrb(owner_id=self.id))

        self.add_modifier(engine, SentryTurretManager())
        self.abilities.append(CreateSentryTurret(owner_id=self.id))

        self.abilities.append(CreateTeleporter(owner_id=self.id))
        self.abilities.append(CreateShieldGenerator(owner_id=self.id))
        self.abilities.append(CreateFloatingBarrier(owner_id=self.id))
        self.abilities.append(CreatePhotonBarrier(owner_id=self.id))
