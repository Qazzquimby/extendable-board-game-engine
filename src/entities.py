import copy
from typing import Optional, List, Type, TYPE_CHECKING

from abilities import Ability
from aimings import TargetSelf

from events import (
    EventPhase,
    SummonEvent,
    AddTokenEvent,
    RemoveTokenEvent,
    DeployEvent,
)
from point import Point
from queries import (
    QueryHasArmor,
    QueryCanMove,
    QueryLegalActions,
    QueryDefense,
    QueryCrit,
    GetTokenCountQuery,
)
from schemas import EntityState

if TYPE_CHECKING:
    from engine import Engine
    from modifiers import Modifier, Token


class Entity:
    def __init__(
        self, engine: "Engine", name: str, hp: int, speed: int, pos: Point, team: int
    ):
        self.engine = engine
        self.id = self.engine.generate_id()
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
        self.engine.add_entity(self)
        self.pos = pos  # runs setter

    def __deepcopy__(self, memo):
        if id(self) in memo:
            return memo[id(self)]
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result

        result.engine = memo[id(self.engine)]

        result.id = self.id
        result.set = self.set
        result.name = self.name

        result.max_hp = self.max_hp
        result.hp = self.hp
        result.speed = self.speed

        result._pos = self._pos
        if result._pos:
            result.engine._entity_by_pos[result._pos] = result
        result.team = self.team
        result.activator = copy.deepcopy(self.activator, memo)

        result.modifiers = copy.deepcopy(self.modifiers, memo)
        result.abilities = copy.deepcopy(self.abilities, memo)

        result.move_actions = self.move_actions
        result.standard_actions = self.standard_actions
        result.free_actions = self.free_actions
        return result

    @property
    def pos(self) -> Optional[Point]:
        return self._pos

    @pos.setter
    def pos(self, value: Optional[Point]) -> None:
        assert isinstance(value, Point) or value is None
        if self._pos is not None:
            if self.engine.entity_at(self._pos) == self:
                del self.engine._entity_by_pos[self._pos]
        self._pos = value
        if value is not None:
            self.engine._entity_by_pos[value] = self

    def start_turn(self) -> None:
        self.move_actions = 1
        self.standard_actions = 1
        self.free_actions = 99  # Arbitrary large number

    def gain_ability(self, ability: Ability):
        ability.owner = self
        self.abilities.append(ability)
        for mod in ability.modifiers:
            self.add_modifier(mod)

    def lose_ability(self, ability: Ability):
        if ability in self.abilities:
            self.abilities.remove(ability)
            ability.owner = None
            for mod in ability.modifiers:
                self.remove_modifier(mod)

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

    def get_hash(self) -> float:
        import hashlib

        key = f"{self.set}__{self.name}"
        hash_int = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
        return float(hash_int % 10000) / 100.0

    # --- Engine Query Helpers ---
    def has_armor(self) -> bool:
        return QueryHasArmor(subject=self).resolve()

    def can_move(self) -> bool:
        q = QueryCanMove(self)
        self.engine.router.publish(q, EventPhase.QUERY)
        return q.result

    def get_legal_actions(self) -> List[Ability]:
        # Returns all abilities the entity has. Modifiers can alter this list.
        # A "basic move" is not an ability in this list, but a capability checked via `can_move()`.
        legal = []
        for ability in self.abilities:
            if ability.is_tapped:
                continue
            if ability.charges is not None and ability.charges <= 0:
                continue
            if (
                ability.is_ultimate
                and ability.ultimate_turn is not None
                and self.engine.round_num < ability.ultimate_turn
            ):
                continue
            legal.append(ability)

        q = QueryLegalActions(self, base_result=legal)
        self.engine.router.publish(q, EventPhase.QUERY)
        return q.result

    def get_defense(
        self,
        attack_source: Optional["Entity"] = None,
        ability: Optional["Ability"] = None,
    ) -> int:
        q = QueryDefense(
            subject=self, attack_source=attack_source, ability=ability, result=0
        )
        self.engine.router.publish(q, EventPhase.QUERY)
        return int(q.result)

    def get_crit(self, subject: "Entity", ability: Optional["Ability"] = None) -> int:
        q = QueryCrit(
            subject=subject,
            attack_source=self,
            ability=ability,
            result=ability.crit_chance,
        )
        self.engine.router.publish(q, EventPhase.QUERY)
        return int(q.result)

    def distance_to(self, other: "Entity") -> int:
        return abs(self.pos[0] - other.pos[0]) + abs(self.pos[1] - other.pos[1])

    def add_modifier(self, modifier: "Modifier") -> None:
        modifier.owner = self
        self.modifiers.append(modifier)
        self.engine.router.subscribe(modifier)

    def remove_modifier(self, modifier: "Modifier") -> None:
        if modifier in self.modifiers:
            self.modifiers.remove(modifier)
            self.engine.router.unsubscribe(modifier)

    def add_token(self, token_class: Type["Token"], amount: int = 1) -> None:
        AddTokenEvent(
            subject=self,
            token_class=token_class,
            amount=amount,
        ).resolve()

    def remove_token(self, token_class: Type["Token"], amount: int = 1) -> None:
        RemoveTokenEvent(subject=self, token_class=token_class, amount=amount).resolve()

    def get_token_count(self, token_class: Type["Token"]) -> int:
        return GetTokenCountQuery(subject=self, token_class=token_class).resolve()


class Hero(Entity):
    def __init__(
        self, engine: "Engine", name: str, hp: int, speed: int, pos: Point, team: int
    ):
        super().__init__(
            engine=engine, name=name, hp=hp, speed=speed, pos=pos, team=team
        )
        self.activator = self
        self.abilities.append(
            Ability(name="Do Nothing", aiming=TargetSelf(), instructions=[], owner=self)
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
        SummonEvent(summoner=self.summoner, subject=self).resolve()

    def __deepcopy__(self, memo):
        if id(self) in memo:
            return memo[id(self)]
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result

        result.engine = memo[id(self.engine)]

        result.id = self.id
        result.set = self.set
        result.name = self.name

        result.max_hp = self.max_hp
        result.hp = self.hp
        result.speed = self.speed

        result._pos = self._pos
        if result._pos:
            result.engine._entity_by_pos[result._pos] = result
        result.team = self.team
        result.activator = copy.deepcopy(self.activator, memo)

        result.modifiers = copy.deepcopy(self.modifiers, memo)
        result.abilities = copy.deepcopy(self.abilities, memo)

        result.move_actions = self.move_actions
        result.standard_actions = self.standard_actions
        result.free_actions = self.free_actions

        result.summoner = copy.deepcopy(self.summoner, memo)
        return result


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
        self.engine = engine
        self.id = self.engine.generate_id()
        self.name = name
        self._pos: Optional[Point] = None
        self.team = team
        self.modifiers: List["Modifier"] = []
        self.engine.markers.append(self)
        self.pos = pos  # runs setter

    def __deepcopy__(self, memo):
        if id(self) in memo:
            return memo[id(self)]
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result

        result.engine = memo[id(self.engine)]

        result.id = self.id
        result.name = self.name
        result._pos = self._pos
        if result._pos:
            result.engine._markers_by_pos.setdefault(result._pos, []).append(result)

        result.team = self.team
        result.modifiers = copy.deepcopy(self.modifiers, memo)
        return result

    @property
    def pos(self) -> Optional[Point]:
        return self._pos

    @pos.setter
    def pos(self, value: Optional[Point]) -> None:
        if self._pos is not None:
            if self in self.engine._markers_by_pos.get(self._pos, []):
                self.engine._markers_by_pos[self._pos].remove(self)
                if not self.engine._markers_by_pos[self._pos]:
                    del self.engine._markers_by_pos[self._pos]
        self._pos = value
        if value is not None:
            self.engine._markers_by_pos.setdefault(value, []).append(self)
