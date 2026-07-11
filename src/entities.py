from typing import Optional, List, Type, TYPE_CHECKING

from abilities import Ability
from aimings import TargetSelf
from events import EventPhase
from event_library import SummonEvent, RemoveTokenEvent, AddTokenEvent
from point import Point
from queries import (
    QueryHasArmor,
    QueryCanMove,
    QueryDefense,
    QueryCrit,
    GetTokenCountQuery,
)
from schemas import EntityState
from util import DO_NOTHING

if TYPE_CHECKING:
    from engine import Engine
    from modifiers import Modifier, Token


EntityId = int


class Entity:
    def __init__(
        self, engine: "Engine", name: str, hp: int, speed: int, pos: Point, team: int
    ):
        self.id = engine.generate_id()
        self.set = "development"
        self.name = name

        self.max_hp = hp  # todo prevent healing over max
        self.hp = hp
        self.speed = speed

        self._pos: Optional[Point] = None
        self.team = team
        self.activator: Optional["Entity"] = None

        self.modifiers: List["Modifier"] = []
        self.abilities: List["Ability"] = []

        self.move_actions: int = 0
        self.standard_actions: int = 0
        self.free_actions: int = 0
        engine.add_entity(self)
        self.pos = pos  # runs setter

    def __str__(self):
        return f"{self.name}({self.id})"

    @property
    def pos(self) -> Optional[Point]:
        return self._pos

    @pos.setter
    def pos(self, value: Optional[Point]) -> None:
        assert isinstance(value, Point) or value is None
        self._pos = value

    def start_turn(self) -> None:
        self.move_actions = 1
        self.standard_actions = 1
        self.free_actions = 99  # Arbitrary large number

    def gain_ability(self, engine: "Engine", ability: Ability):
        ability.owner = self
        self.abilities.append(ability)
        for mod in ability.modifiers:
            self.add_modifier(engine=engine, modifier=mod)

    def lose_ability(self, engine: "Engine", ability: Ability):
        if ability in self.abilities:
            self.abilities.remove(ability)
            ability.owner = None
            for mod in ability.modifiers:
                self.remove_modifier(engine=engine, modifier=mod)

    def get_modifier(self, modifier_class):
        # Utility to find a specific modifier on this entity
        for mod in self.modifiers:
            if isinstance(mod, modifier_class):
                return mod
        return None

    def to_model(self) -> EntityState:
        return EntityState(
            id=self.id,
            name=self.name,
            hp=self.hp,
            pos=self.pos,
            team=self.team,
            move_actions=self.move_actions,
            standard_actions=self.standard_actions,
            free_actions=self.free_actions,
            modifiers=[str(modifier) for modifier in self.modifiers],
        )

    # --- Engine Query Helpers ---
    def has_armor(self, engine: "Engine") -> bool:
        return QueryHasArmor(subject=self).resolve(engine)

    def can_move(self, engine: "Engine" = None) -> bool:
        q = QueryCanMove(self)
        engine.router.publish(q, EventPhase.QUERY)
        return q.result

    # todo Seems not used now but should be?
    # def get_legal_actions(self) -> List[Ability]:
    #     # Returns all abilities the entity has. Modifiers can alter this list.
    #     # A "basic move" is not an ability in this list, but a capability checked via `can_move()`.
    #     legal = []
    #     for ability in self.abilities:
    #         if ability.is_tapped:
    #             continue
    #         if ability.charges is not None and ability.charges <= 0:
    #             continue
    #         if (
    #             ability.is_ultimate
    #             and ability.ultimate_turn is not None
    #             and engine.round_num < ability.ultimate_turn
    #         ):
    #             continue
    #         legal.append(ability)
    #
    #     q = QueryLegalActions(self, base_result=legal)
    #     engine.router.publish(q, EventPhase.QUERY)
    #     return q.result

    def get_defense(
        self,
        engine: "Engine",
        attack_source: Optional["Entity"] = None,
        ability: Optional["Ability"] = None,
    ) -> int:
        q = QueryDefense(
            subject=self, attack_source=attack_source, ability=ability, result=0
        )
        engine.router.publish(q, EventPhase.QUERY)
        return int(q.result)

    def get_crit(
        self,
        engine: "Engine",
        subject: "Entity",
        ability: Optional["Ability"] = None,
    ) -> int:
        q = QueryCrit(
            subject=subject,
            attack_source=self,
            ability=ability,
            result=ability.crit_chance,
        )
        engine.router.publish(q, EventPhase.QUERY)
        return int(q.result)

    def distance_to(self, other: "Entity") -> int:
        return abs(self.pos[0] - other.pos[0]) + abs(self.pos[1] - other.pos[1])

    def add_modifier(
        self,
        engine: "Engine",
        modifier: "Modifier",
    ) -> None:
        modifier.owner = self
        self.modifiers.append(modifier)
        engine.router.subscribe(modifier)

    def remove_modifier(
        self,
        engine: "Engine",
        modifier: "Modifier",
    ) -> None:
        if modifier in self.modifiers:
            self.modifiers.remove(modifier)
            engine.router.unsubscribe(modifier)

    def add_token(
        self, engine: "Engine", token_class: Type["Token"], amount: int = 1
    ) -> None:
        event = AddTokenEvent(
            engine=engine,
            subject=self,
            token_class=token_class,
            amount=amount,
        )
        engine.event_queue.enqueue(event)

    def remove_token(
        self, engine: "Engine", token_class: Type["Token"], amount: int = 1
    ) -> None:
        event = RemoveTokenEvent(
            engine=engine, subject=self, token_class=token_class, amount=amount
        )
        engine.event_queue.enqueue(event)

    def get_token_count(self, token_class: Type["Token"], engine: "Engine") -> int:
        return GetTokenCountQuery(subject=self, token_class=token_class).resolve(engine)


class Hero(Entity):
    def __init__(
        self, engine: "Engine", name: str, hp: int, speed: int, pos: Point, team: int
    ):
        super().__init__(
            engine=engine, name=name, hp=hp, speed=speed, pos=pos, team=team
        )
        self.activator = self
        self.abilities.append(
            Ability(name=DO_NOTHING, aiming=TargetSelf(), instructions=[], owner=self)
        )


class Summon(Entity):
    def __init__(
        self,
        engine: "Engine",
        name: str,
        hp: int,
        speed: int,
        pos: Point,
        team: int,
        summoner: Entity,
    ):
        super().__init__(
            engine=engine, name=name, hp=hp, speed=speed, pos=pos, team=team
        )
        self.summoner = summoner
        self.activator = summoner.activator
        event = SummonEvent(engine=engine, summoner=self.summoner, subject=self)
        engine.event_queue.enqueue(event)


class Object(Summon):
    def __init__(
        self,
        engine: "Engine",
        name: str,
        hp: int,
        pos: Point,
        team: int,
        summoner: Entity,
    ):
        super().__init__(
            engine=engine,
            name=name,
            hp=hp,
            speed=0,
            pos=pos,
            team=team,
            summoner=summoner,
        )


class Marker:
    def __init__(self, engine: "Engine", name: str, pos: Point, team: int):
        engine = engine
        self.id = engine.generate_id()
        self.name = name
        self._pos: Optional[Point] = None
        self.team = team
        self.modifiers: List["Modifier"] = []
        engine.markers.append(self)
        self.pos = pos  # runs setter

    @property
    def pos(self) -> Optional[Point]:
        return self._pos

    @pos.setter
    def pos(self, value: Optional[Point]) -> None:
        self._pos = value
