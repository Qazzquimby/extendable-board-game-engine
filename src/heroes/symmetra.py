from dataclasses import dataclass

from abilities import (
    Ability,
    DamageInstruction,
    GiveTokenInstruction,
    TeleportInstruction,
)
from aimings import TargetEntity, MultipleAiming, TargetPoint
from engine import (
    Entity,
    after,
    Object,
    Engine,
    SlowToken,
    Hero,
    GiveTokenEvent,
    ActionContext,
    Instruction,
)
from modifiers import Modifier, SummonModifier, Token
from events import TurnStartEvent, TurnEndEvent, DamageEvent, SummonEvent
from point import Point

# region Photon Beam


class PhotonBeamToken(Token):
    pass


class PhotonBeamManager(Modifier):
    def __init__(self):
        self.entities_hit_this_turn = set()
        super().__init__()

    @after(TurnStartEvent)
    def clear_tracker_on_turn_start(self, event: TurnStartEvent):
        self.entities_hit_this_turn.clear()

    @after(TurnEndEvent)
    def fade_tokens_on_turn_end(self, event: TurnEndEvent):
        for entity in self.owner.engine.living_entities:
            if (
                entity.get_token_count(PhotonBeamToken) > 0
                and entity not in self.entities_hit_this_turn
            ):
                entity.remove_token(PhotonBeamToken, amount=1)


@dataclass
class GivePhotonBeamTokenAndTrack(Instruction):
    # We pass the manager instance in, creating a direct link.
    tracker: PhotonBeamManager

    def execute(self, ctx: ActionContext) -> None:
        subject = ctx.engine.entity_at(ctx.subject_point)
        if subject:
            subject.add_token(PhotonBeamToken)
        self.tracker.entities_hit_this_turn.add(subject)


# endregion


# region Sentry Turret
class SentryTurretManager(Modifier):
    def __init__(self):
        self.target_hit_this_activation = set()
        super().__init__()

    @after(
        TurnStartEvent
    )  # todo should separate turn and activation. Hero and their summons activate on same turn.
    def clear_on_turn_start(self, event: TurnStartEvent):
        self.target_hit_this_activation.clear()


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

        class TurretAttack(SummonModifier):
            # At start of creator's activation: ⌖Nearest enemy in range 2: *Undefendable*, 1dmg.
            # If another **Sentry Turret** already hit the target this activation, the target gets **slow** -1.
            @after(TurnStartEvent)
            def fire_at_nearest(self, event: TurnStartEvent):
                manager = self.owner.summoner.get_modifier(SentryTurretManager)  # todo

                # Find nearest enemy in range 2
                enemies = [
                    e
                    for e in self.owner.engine.living_entities
                    if e.team != self.owner.team and self.owner.distance_to(e) <= 2
                ]
                if enemies:
                    nearest = min(enemies, key=lambda e: self.owner.distance_to(e))
                    if nearest in manager.targets_hit_this_activation:
                        GiveTokenEvent(
                            engine=engine,
                            subject=nearest,
                            token_class=SlowToken,
                            amount=1,
                        ).resolve()
                    manager.targets_hit_this_activation.add(nearest)
                    DamageEvent(
                        engine=self.owner.engine,
                        source=self.owner,
                        subject=nearest,
                        amount=1,
                    ).resolve()

        self.add_modifier(TurretAttack())


def grant_sentry_turret_ability(owner_entity: Entity):
    if not owner_entity.has_modifier(SentryTurretManager):
        owner_entity.add_modifier(SentryTurretManager())

    create_turret_ability = Ability(
        name="Create Sentry Turret",
        aiming=MultipleAiming(
            [TargetPoint(in_range=None, empty=True) for _i in range(3)]
        ),
        instructions=[CreateSentryTurretInstruction()],
        max_charges=1,
        owner=owner_entity,
    )
    owner_entity.abilities.append(create_turret_ability)


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
        # todo, teleporter behavior. Everyone has action while in teleporter's space to teleport to other space.

    @after(SummonEvent)
    def give_teleport_ability(self):
        for entity in self.engine.living_entities:
            entity.abilities.append(
                Ability(
                    name="Use Teleporter",
                    aiming=TargetEntity(),  # todo target teleporter, todo ignoring line of sight
                    instructions=[
                        TeleportInstruction(
                            destination=lambda ctx: ctx.subject.pos,
                        )
                    ],
                    owner=self,
                )
            )
            # todo no duplicate abilities
            # todo entities can sometimes share spaces? non-blocking tag? Things targeting the space hit the top entity, and all are included in aoe


@dataclass
class CreateSentryTurretInstruction(Instruction):
    def execute(self, ctx: ActionContext) -> None:
        for point in ctx.target_points:
            if not ctx.engine.entity_at(point):
                SentryTurret(
                    engine=ctx.engine,
                    pos=point,
                    team=ctx.source.team,
                    summoner=ctx.source,
                )


@dataclass
class CreateTeleporterInstruction(Instruction):
    def execute(self, ctx: ActionContext) -> None:
        for point in ctx.target_points:
            if not ctx.engine.entity_at(point):
                Teleporter(
                    engine=ctx.engine,
                    pos=point,
                    team=ctx.source.team,
                    summoner=ctx.source,
                )


class Symmetra(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Symmetra", hp=8, speed=3, pos=pos, team=team
        )
        self.grant_ability(
            Ability(
                name="Photon Beam",
                aiming=TargetEntity(in_range=2),
                instructions=[
                    DamageInstruction(
                        amount=lambda ctx: 2
                        + (2 * ctx.subject.get_token_count(PhotonBeamToken)),
                        undefendable=True,
                    ),
                    GivePhotonBeamTokenAndTrack(),
                ],
                # The passive tracking logic is bundled directly into the ability
                modifiers=[PhotonBeamManager()],
                is_default=True,
            )
        )

        self.abilities.append(
            # todo  Choose one --
            #           - ⌖Range 4: +2 *miss*, 2dmg.
            #           - At the beginning of your next activation: ⌖Range 4: +2 *miss*, 4dmg.
            Ability(
                name="Photon Orb",
                aiming=TargetEntity(in_range=4),
                instructions=[DamageInstruction(amount=2)],
                is_default=True,
                owner=self,
            )
        )

        grant_sentry_turret_ability(self)

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
                owner=self,
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
