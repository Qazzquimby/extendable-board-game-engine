from dataclasses import dataclass

from typing import Union

from aimings import (
    TargetEntity,
    MultipleAiming,
    IncludeArea,
    is_enemy_aim_condition,
    AimingResult,
    MultipleAimingResults,
)
from areas import Burst
from engine import (
    Engine,
    Hero,
    query,
)
from entities import Entity
from logger import log
from modifiers import Modifier
from queries import QueryDefense
from events import after
from event_library import PullEvent, DeployEvent, TurnStartEvent, DeathEvent, HealEvent
from abilities import (
    Ability,
    Instruction,
    ActionContext,
    best_move_for_score,
    displacement_value,
)
from instruction_library import DamageInstruction
from point import Point
from valence import Valence

VIKTORIA_NAME = "Viktoria"


class OnFirstTurnSpawnOtherViktoria(Modifier):
    text = "Deploy: Create a copy of this in your deploy zone, without this ability."

    @after(DeployEvent)
    def spawn_viktoria(self, engine: "Engine", event: DeployEvent):
        subject = engine.get_entity_by_id(event.subject_id)
        if hasattr(subject, "is_original") and subject.is_original:
            with self.log_trigger(engine=engine, event=event):
                legal_spaces = engine.grid.get_points_in_range(
                    start=subject.pos, max_range=1
                )
                open_spaces = [
                    space for space in legal_spaces if not engine.entity_at(space)
                ]
                if open_spaces:
                    target_space = open_spaces[0]
                    v = Viktoria(
                        engine=engine,
                        pos=target_space,
                        team=subject.team,
                        is_original=False,
                    )
                    v.activator = subject.activator
                    log(f"New Viktoria spawned at {target_space}")


class OnStartOfTurnMayTeleportAnotherViktoriaHereThenTeleport1(Modifier):
    text = "Start of turn: Another Viktoria in range 4 may teleport adjacent to this. Teleport 1."

    @after(TurnStartEvent)
    def start_of_turn(self, engine: "Engine", event: TurnStartEvent):
        with self.log_trigger(engine, event):
            subject = engine.get_entity_by_id(event.subject_id)
            spaces_in_range = engine.grid.get_points_in_range(
                start=subject.pos, max_range=4
            )
            for space in spaces_in_range:
                entity = engine.entity_at(space)
                if entity and entity.name == VIKTORIA_NAME:
                    # todo they can choose to teleport to any space in burst1. Then you can choose to teleport burst 1.
                    #  only do plausible movements to avoid explosive action space.
                    pass


class OnKillAllViktoriasHeal(Modifier):
    @after(DeathEvent, only_self=False)
    def on_kill(self, engine: "Engine", event: DeathEvent):
        if event.killer_id == self.owner_id:
            owner = engine.get_entity_by_id(self.owner_id)
            for entity in engine.living_entities:
                if entity.name == VIKTORIA_NAME:
                    with self.log_trigger(engine=engine, event=event):
                        engine.event_queue.enqueue(HealEvent(subject=entity, amount=2))


@dataclass(kw_only=True)
class DefenseModifier(Modifier):
    amount: int
    text = "You can only be hit on a d6 roll higher than your defense"
    valence = Valence.GOOD

    @query(QueryDefense)
    def modify_defense(self, engine: "Engine", q: QueryDefense):
        q.result += self.amount


class OnDeathOtherViktoriasHealAndGainDef(Modifier):
    @after(DeathEvent)
    def on_death(self, engine: "Engine", event: DeathEvent):
        owner = engine.get_entity_by_id(self.owner_id)
        for entity in engine.living_entities:
            if entity.name == VIKTORIA_NAME and entity != owner:
                with self.log_trigger(engine=engine, event=event):
                    engine.event_queue.enqueue(HealEvent(subject=entity, amount=2))
                    owner.add_modifier(engine, DefenseModifier(amount=2))


@dataclass(kw_only=True)
class DragonsBreathPull(Instruction):
    valence: Valence = Valence.MIXED

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        target = ctx.get_target(engine)
        if not target:
            return
        burst_4_area = engine.grid.get_points_in_range(
            start=ctx.target_point, max_range=6
        )
        viktorias_in_range = []
        for point in burst_4_area:
            entity = engine.entity_at(point)
            if entity and entity.name == VIKTORIA_NAME:
                viktorias_in_range.append(entity)
        for viktoria in viktorias_in_range:
            with log("Dragon's Breath Pull"):
                engine.event_queue.enqueue(
                    PullEvent(viktoria, distance=4, toward_point=ctx.target_point)
                )


class EnchantedKatana(Ability):
    def __init__(self, owner_id: str):
        super().__init__(
            name="Enchanted Katana",
            text="Range 1, 2dmg +2Crit. Other enemies in burst 1, 1dmg",
            aiming=MultipleAiming(
                {
                    "target": TargetEntity(
                        in_range=1, condition=is_enemy_aim_condition
                    ),
                    "burst": IncludeArea(
                        area=Burst(radius=1), condition=is_enemy_aim_condition
                    ),
                },
                exclusions={"burst": "target"},
            ),
            instructions=[
                DamageInstruction(aiming_name="target", amount=2),
                DamageInstruction(aiming_name="burst", amount=1),
            ],
            crit_chance=2,
            is_default=True,
            owner_id=owner_id,
        )

    def get_movement(
        self,
        engine: "Engine",
        actor: "Entity",
        reachable_points: set["Point"],
        enemies: list["Entity"],
        allies: list["Entity"],
    ) -> dict["Point", str]:
        if not reachable_points or not enemies:
            return {}
        return best_move_for_score(
            reachable_points,
            actor.pos,
            score_fn=lambda pt: sum(2 for e in enemies if pt.get_distance(e.pos) == 1),
            reason="Maximize Enchanted Katana targets",
        )

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        target_points = aiming_result.sub_aimings["target"].target_points
        if not target_points:
            return 0.0
        target = engine.entity_at(target_points[0])
        score = 2.0

        included = aiming_result.sub_aimings["burst"].included_points
        for pt in included:
            e = engine.entity_at(pt)
            if e and e.team != actor.team and e != target:
                score += 1.0
                if e.hp <= 1:
                    score += 1
        return score


class DragonsBreath(Ability):
    def __init__(self, owner_id: str):
        super().__init__(
            name="Dragon's Breath",
            text="Target enemy in range 4. All Viktorias in range 6 of the target pull 4 towards it.",
            aiming=TargetEntity(in_range=4),
            instructions=[DragonsBreathPull()],
            owner_id=owner_id,
        )

    def get_movement(
        self,
        engine: "Engine",
        actor: "Entity",
        reachable_points: set["Point"],
        enemies: list["Entity"],
        allies: list["Entity"],
    ) -> dict["Point", str]:
        if not reachable_points or not enemies:
            return {}
        return best_move_for_score(
            reachable_points,
            actor.pos,
            score_fn=lambda pt: sum(1 for e in enemies if pt.get_distance(e.pos) <= 4),
            reason="In range for Dragon's Breath",
        )

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        target_points = aiming_result.target_points
        if not target_points:
            return 0.0
        target_pt = target_points[0]

        score = 0.0
        for e in engine.living_entities:
            if e.name == VIKTORIA_NAME and e.pos and e.pos.get_distance(target_pt) <= 5:
                pull_path = engine.grid.get_pull_path(
                    subject=e, pull_to=target_pt, distance=4
                )
                if not pull_path:
                    continue
                dest_point = pull_path[-1]
                value = displacement_value(e, e.pos, dest_point, engine)
                if value > 0:
                    score += value

        return score


class Viktoria(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int, is_original=True):
        self.is_original = is_original
        super().__init__(
            engine=engine, name=VIKTORIA_NAME, hp=6, speed=3, pos=pos, team=team
        )
        self.add_modifier(engine, OnFirstTurnSpawnOtherViktoria())
        self.add_modifier(engine, OnKillAllViktoriasHeal())
        self.add_modifier(engine, OnDeathOtherViktoriasHealAndGainDef())

        self.abilities.append(EnchantedKatana(owner_id=self.id))
        self.abilities.append(DragonsBreath(owner_id=self.id))
