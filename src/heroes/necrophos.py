from dataclasses import dataclass
from typing import Union

from aimings import (
    TargetEntity,
    TargetSelf,
    IncludeArea,
    MultipleAiming,
    is_enemy_aim_condition,
    AimingResult,
    MultipleAimingResults,
)
from areas import Burst
from engine import (
    Engine,
    Hero,
)
from entities import Entity
from modifiers import Modifier, Token, ImmobileToken
from events import (
    after,
    before,
    query,
)
from event_library import (
    ChangeLocationEvent,
    TurnStartEvent,
    TurnEndEvent,
    DamageEvent,
    DeathEvent,
    HealEvent,
    AddTokenEvent,
)
from abilities import (
    Ability,
    ActionCost,
    Instruction,
    ActionContext,
    UseAnAbilityInstruction,
    AddModifierInstruction,
    AddTokenInstruction,
)
from mod_value import ModInt
from point import Point
from queries import QueryLegalAimings, QueryAvoidInclusion
from valence import Valence


class KillCounter(Token):
    valence = Valence.GOOD


@dataclass(kw_only=True)
class NecroStartTurnAura(Modifier):
    text = "Start of turn: Enemies in Burst 3, irreducible 1dmg + 1dmg per 2 Kill counters. Heal 1 per Kill counter"
    valence = Valence.GOOD

    @after(TurnStartEvent)
    def aura(self, engine: "Engine", event: "TurnStartEvent") -> None:
        subject = engine.get_entity_by_id(event.subject_id)
        num_kill_counters = subject.get_token_count(
            engine=engine, token_class=KillCounter
        )
        with self.log_trigger(engine=engine, event=event):
            owner = engine.get_entity_by_id(self.owner_id)
            points_in_range = engine.grid.get_points_in_range(
                start=owner.pos, max_range=3
            )
            enemies_in_range = []
            allies_in_range = []
            for entity in engine.living_entities:
                if entity.pos in points_in_range:
                    if entity.team == subject.team:
                        allies_in_range.append(entity)
                    else:
                        enemies_in_range.append(entity)

            for enemy in enemies_in_range:
                engine.event_queue.enqueue(
                    DamageEvent(
                        source=subject,
                        subject=enemy,
                        amount=ModInt(1 + num_kill_counters // 2, is_irreducible=True),
                    )
                )
            for ally in allies_in_range:
                engine.event_queue.enqueue(
                    HealEvent(subject=ally, amount=ModInt(num_kill_counters))
                )


@dataclass(kw_only=True)
class NecroGetKillCounter(Modifier):
    text = "On killing a unit with 4 or more max health, gain a Kill Counter"
    valence = Valence.GOOD

    @after(DeathEvent, only_self=False)
    def gain_kill_counter(self, engine: "Engine", event: "DeathEvent") -> None:
        if event.killer_id == self.owner_id:
            subject = engine.get_entity_by_id(event.subject_id)
            if subject.max_hp >= 4:
                with self.log_trigger(engine=engine, event=event):
                    owner = engine.get_entity_by_id(self.owner_id)
                    engine.event_queue.enqueue(
                        AddTokenEvent(subject=owner, token_class=KillCounter)
                    )


@dataclass(kw_only=True)
class NecroGhostShroud(Modifier):
    text = """\
    Until the end of your next turn:
     You cannot be affected by default abilities.
     You deal +100% healing.
      You receive +1 damage."""
    valence = Valence.MIXED

    @query(QueryLegalAimings)
    def cannot_target_with_default(self, engine: "Engine", q: "QueryLegalAimings"):
        owner = engine.get_entity_by_id(self.owner_id)
        if q.ability.is_default:
            legal_aimings = [
                aiming for aiming in q.result if owner.pos not in aiming.target_points
            ]
            q.result = legal_aimings

    @query(QueryAvoidInclusion)
    def avoid_inclusion_in_default(self, engine: "Engine", q: "QueryAvoidInclusion"):
        if q.ability.is_default:
            q.result = True

    @before(HealEvent)
    def receive_double_heal(self, engine: "Engine", event: "HealEvent"):
        event.amount.mult(2)

    @before(DamageEvent)
    def take_1_more_damage(self, engine: "Engine", event: "DamageEvent"):
        event.amount.add(1)  # todo should be a query on damage taken


@dataclass
class DeathPulse(Instruction):
    valence = Valence.MIXED

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        point = ctx.subject_point
        entity = engine.entity_at(point)
        if entity:
            source = engine.get_entity_by_id(ctx.source_id)
            if entity.team == source.team:
                engine.event_queue.enqueue(HealEvent(subject=entity, amount=1))
            else:
                engine.event_queue.enqueue(
                    DamageEvent(source=source, subject=entity, amount=1)
                )


@dataclass
class NecroTeleportAdjacentInstruction(Instruction):
    valence = Valence.BAD

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        target = ctx.get_target(engine)
        if target:
            points_adjacent = engine.grid.get_points_in_range(
                start=target.pos, max_range=1
            )
            empty_adjacent = [p for p in points_adjacent if not engine.entity_at(p)]
            if empty_adjacent:
                source = engine.get_entity_by_id(ctx.source_id)
                engine.event_queue.enqueue(
                    ChangeLocationEvent(subject=source, new_pos=empty_adjacent[0])
                )


@dataclass(kw_only=True)
class ReapersScythe(Token):
    source: "Entity"
    text = """\
    At the start of their next turn, the caster deals irreducible damage to you equal to your missing health. On kill, they gain 2 additional Kill counters."""
    valence = Valence.BAD

    @after(TurnStartEvent)
    def trigger(self, engine: "Engine", event: "TurnStartEvent"):
        subject = engine.get_entity_by_id(event.subject_id)
        if subject.id == self.owner_id:
            with self.log_trigger(engine=engine, event=event):
                missing_hp = subject.max_hp - subject.hp
                if missing_hp > 0:
                    damage_event = DamageEvent(
                        source=self.source,
                        subject=subject,
                        amount=ModInt(missing_hp, is_irreducible=True),
                    )
                    engine.event_queue.enqueue(damage_event)
                subject.remove_token(engine, ReapersScythe)

    @after(DeathEvent)
    def on_death(self, engine: "Engine", event: "DeathEvent"):
        if event.subject_id == self.owner_id and event.killer_id == self.source.id:
            engine.event_queue.enqueue(
                AddTokenEvent(subject=self.source, token_class=KillCounter, amount=2)
            )


class DeathPulseAbility(Ability):
    def get_movement(
        self,
        engine: "Engine",
        actor: "Entity",
        reachable_points: set["Point"],
        enemies: list["Entity"],
        allies: list["Entity"],
    ) -> dict["Point", str]:
        proposed_moves = {}
        if not reachable_points:
            return proposed_moves

        def score_pt(pt: Point) -> int:
            score = 0
            for e in enemies:
                if pt.get_distance(e.pos) <= 3:
                    score += 1
            for a in allies:
                if pt.get_distance(a.pos) <= 3 and a.hp < a.max_hp:
                    score += 1
            return score

        best_pt = max(
            reachable_points,
            key=lambda pt: (score_pt(pt), -pt.get_distance(actor.pos)),
        )
        if score_pt(best_pt) > 0:
            proposed_moves[best_pt] = "Maximize Death Pulse targets"
        return proposed_moves

    def _get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        included = aiming_result.included_points
        score = 0
        for pt in included:
            entity = engine.entity_at(pt)
            if entity:
                if entity.team != actor.team:
                    score += 1
                else:
                    if entity.hp < entity.max_hp:
                        score += 1
        return float(score)


class GhostShroudAbility(Ability):
    def _get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        if actor.hp <= actor.max_hp / 2:
            return 3.0
        return 1.0


class DeathSeekerAbility(Ability):
    def _get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        return 2.5


class ReapersScytheAbility(Ability):
    def _get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        target = engine.entity_at(aiming_result.target_points[0])
        if not target:
            return 0.0

        score = 0
        missing_hp = target.max_hp - target.hp
        half_hp = target.max_hp // 2
        if missing_hp >= half_hp:
            score += 2  # likely to get extra kill counters
        expected_damage = min(target.hp, missing_hp)
        return expected_damage + 1  # immobilize


class Necrophos(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Necrophos", hp=8, speed=3, pos=pos, team=team
        )

        self.add_modifier(engine, NecroStartTurnAura())
        self.add_modifier(engine, NecroGetKillCounter())

        self.abilities.append(
            DeathPulseAbility(
                name="Death Pulse",
                text="Enemies in burst 3, 1dmg. You and allies in burst 3, heal 1.",
                aiming=IncludeArea(area=Burst(radius=3)),
                instructions=[DeathPulse()],
                is_default=True,
                owner_id=self.id,
            )
        )

        self.abilities.append(
            GhostShroudAbility(
                name="Ghost Shroud",
                text="""\
        1/Game, Instant +3
Until the end of your next turn:
  You cannot be affected by default abilities.
  You deal +100% healing.
  You receive +1 damage..""",
                aiming=TargetSelf(),
                instructions=[
                    AddModifierInstruction(modifier_class=NecroGhostShroud),
                ],
                owner_id=self.id,
                action_cost=ActionCost.INSTANT,
                instant_speed=3,
                max_charges=1,
            )
        )

        self.abilities.append(
            DeathSeekerAbility(
                name="Death Seeker",
                text="""\
               1/Game
Teleport to a space adjacent to an enemy in range 3.
Use a default ability.
                """,
                aiming=MultipleAiming(
                    {
                        "enemy": TargetEntity(
                            in_range=3, condition=is_enemy_aim_condition
                        ),
                        "self": TargetSelf(),
                    }
                ),
                instructions=[
                    NecroTeleportAdjacentInstruction(aiming_name="enemy"),
                    UseAnAbilityInstruction(aiming_name="self", default_only=True),
                ],
                max_charges=1,
                owner_id=self.id,
            )
        )

        self.abilities.append(
            ReapersScytheAbility(
                name="Reaper's Scythe",
                text="""\
                1/Game
Range 3, immobilize.
At the start of your next turn, deal irreducible damage the target equal to their missing health.
On kill, gain 2 additional Kill counters.
                """,
                aiming=TargetEntity(in_range=3),
                instructions=[
                    AddTokenInstruction(
                        token_class=ImmobileToken,
                    ),
                    AddTokenInstruction(
                        token_class=ReapersScythe, token_kwargs={"source": self}
                    ),
                ],
                max_charges=1,
                owner_id=self.id,
            )
        )
