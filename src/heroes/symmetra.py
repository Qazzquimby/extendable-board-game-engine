from dataclasses import dataclass, field

from abilities import (
    Ability,
    DamageInstruction,
    TeleportInstruction,
    ActionCost,
    ActionContext,
    Instruction,
)
from aimings import TargetEntity, MultipleAiming, TargetPoint, TargetSelf
from engine import Engine
from entities import (
    Entity,
    Object,
    Hero,
)
from modifiers import (
    Modifier,
    SummonModifier,
    Token,
    SlowToken,
    ClearAtStartOfTurnMixin,
)
from events import after, before
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
from queries import QueryDefense
from valence import Valence


# region Photon Orb
@dataclass(kw_only=True)
class PhotonOrbMissChance(Modifier, ClearAtStartOfTurnMixin):
    valence = Valence.BAD

    @before(QueryDefense)
    def add_miss_chance(self, engine: "Engine", event: QueryDefense):
        if (
                event.ability
                and event.ability.name == "Photon Orb"
                and event.ability.owner_id == self.owner_id
        ):
            event.result += 2


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


@dataclass
class PhotonBeamDamageInstruction(Instruction):
    valence = Valence.BAD

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


@dataclass
class GivePhotonBeamTokenAndTrack(Instruction):
    tracker: PhotonBeamManager
    valence = Valence.BAD

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        subject = engine.entity_at(ctx.subject_point)
        if subject:
            subject.add_token(engine, PhotonBeamToken)
            self.tracker.entities_hit_this_turn.add(subject)


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


def grant_sentry_turret_ability(engine: "Engine", owner_entity: Entity):
    if not owner_entity.get_modifier(SentryTurretManager):
        owner_entity.add_modifier(engine, SentryTurretManager())

    create_turret_ability = Ability(
        name="Create Sentry Turret",
        aiming=MultipleAiming(
            [TargetPoint(in_range=None, empty=True) for _i in range(3)]
        ),
        instructions=[CreateSentryTurretInstruction()],
        max_charges=1,
        owner_id=owner_entity.id,
    )
    owner_entity.abilities.append(create_turret_ability)


@dataclass
class CreateSentryTurretInstruction(Instruction):
    valence = Valence.GOOD

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


@dataclass
class CreateTeleporterInstruction(Instruction):
    valence = Valence.GOOD

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


@dataclass
class CreateShieldGeneratorInstruction(Instruction):
    valence = Valence.GOOD

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


# endregion


class Symmetra(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Symmetra", hp=8, speed=3, pos=pos, team=team
        )
        photon_beam_manager = PhotonBeamManager()
        self.gain_ability(
            engine,
            Ability(
                name="Photon Beam",
                aiming=TargetEntity(in_range=2),
                instructions=[
                    PhotonBeamDamageInstruction(),
                    GivePhotonBeamTokenAndTrack(tracker=photon_beam_manager),
                ],
                modifiers=[photon_beam_manager],
                is_default=True,
            ),
        )

        # todo, dumb, many attacks need to have a miss chance and sometimes only in some situations.
        # Reimplement
        self.add_modifier(engine, PhotonOrbMissChance())
        self.abilities.append(
            Ability(
                name="Photon Orb",
                aiming=TargetEntity(in_range=4),
                instructions=[DamageInstruction(amount=2)],
                is_default=True,
                owner_id=self.id,
            )
        )

        # todo At the beginning of your next activation, pick target in ⌖Range 4: +2 *miss*, 4dmg.
        # self.abilities.append(
        #     Ability(
        #         name="Charge Photon Orb",
        #         is_default=True,
        #         owner_id=self.id,
        #     )
        # )

        grant_sentry_turret_ability(engine, self)

        self.abilities.append(
            Ability(
                name="Create Teleporter",
                aiming=MultipleAiming(
                    [
                        TargetPoint(in_range=1, empty=True),
                        TargetPoint(in_range=None, empty=True),
                    ]
                ),
                instructions=[CreateTeleporterInstruction()],
                max_charges=1,
                owner_id=self.id,
            )
        )

        self.abilities.append(
            Ability(
                name="Create Shield Generator",
                aiming=TargetPoint(in_range=1, empty=True),
                instructions=[CreateShieldGeneratorInstruction()],
                is_ultimate=True,
                ultimate_turn=3,
                owner_id=self.id,
            )
        )

#  todo     - name: Create Floating Barrier
#         art: floating_barrier.webp
#         text: |-
#           1/game:
#           Create a **Floating Barrier** marker in an edge in range 1, facing away from you.
#           It has:
#             This blocks line of sight for the creator's enemies.
#             At start of creator's activation: This moves forward 2 spaces.

# todo      - name: Create Shield Generator
#         art: shield_generator.webp
#         text: |-
#           *Ultimate* 3:
#           Create a **Shield Generator** object in an empty space in range 1.
#           Heal all allies 4.
#           It has:
#             4hp.
#             Allies of the creator have +4 maximum health.
#             When this is destroyed, allies of the creator lose 4 health.

# todo       - name: Create Photon Barrier
#         art: photon_barrier.jpg
#         text: |-
#           *Ultimate* 4:
#           Choose any edge across the map.
#           Create a **Photon Barrier** object along that edge.
#           It has:
#             12hp.
#             This blocks line of sight for the creator's enemies.
