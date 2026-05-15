from typing import Optional

from abilities import Ability
from engine import Event, Engine, Entity, Summon
from mod_value import ModInt


class PushEvent(Event):
    def __init__(
        self,
        engine: "Engine",
        subject: "Entity",
        distance: int,
        source: Optional["Entity"] = None,
    ):
        super().__init__(engine=engine, subject=subject)
        self.distance = ModInt(distance)
        self.source = source

    def _resolve(self) -> None:
        # Pushing is calculated based on pathing away from the source
        if (
            getattr(self.subject, "pos", None) is not None
            and self.source
            and getattr(self.source, "pos", None) is not None
        ):
            dist = max(0, self.distance.value)
            if dist > 0:
                path = self.engine.grid.get_push_path(  # todo
                    start=self.subject.pos, target=None, push_from=self.source.pos
                )
                if path and len(path) >= dist:
                    self.subject.pos = path[dist - 1]


class PullEvent(Event):
    def __init__(
        self,
        engine: "Engine",
        subject: "Entity",
        distance: int,
        source: Optional["Entity"] = None,
    ):
        super().__init__(engine=engine, subject=subject)
        self.distance = ModInt(distance)
        self.source = source

    def _resolve(self) -> None:
        if (
            getattr(self.subject, "pos", None) is not None
            and self.source
            and getattr(self.source, "pos", None) is not None
        ):
            dist = max(0, self.distance.value)
            if dist > 0:
                path = self.engine.grid.get_pull_path(
                    self.subject.pos, self.source.pos, self.source.pos
                )
                if path and len(path) >= dist:
                    self.subject.pos = path[dist - 1]


class TurnStartEvent(Event):
    def __init__(self, engine: "Engine", subject: "Entity"):
        super().__init__(engine=engine, subject=subject)

    def _resolve(self) -> None:
        self.engine.active_entity.start_turn()


class TurnEndEvent(Event):
    def __init__(self, engine: "Engine", subject: "Entity"):
        super().__init__(engine=engine, subject=subject)

    def _resolve(self) -> None:
        for ability in self.subject.abilities:
            if ability.taps:
                if not ability.tapped_this_turn:
                    ability.is_tapped = False
                ability.tapped_this_turn = False


class DamageEvent(Event):
    def __init__(
        self,
        engine: Engine,
        source: Optional[Entity],
        subject: Entity,
        amount: int,
        ability: Optional["Ability"] = None,
    ):
        super().__init__(engine=engine, subject=subject)
        self.source = source
        self.amount = ModInt(amount)
        self.ability = ability

    def _resolve(self) -> None:
        if self.subject.has_armor():
            self.amount.add(-1)

        final_damage = max(0, self.amount.value)
        new_hp = max(0, self.subject.hp - final_damage)
        self.subject.hp = new_hp

        if self.subject.hp <= 0:
            DeathEvent(self.engine, subject=self.subject, killer=self.source).resolve()


class DeathEvent(Event):
    # For on-kill use on-death and filter by killer
    def __init__(
        self, engine: Engine, subject: Entity, killer: Optional[Entity] = None
    ):
        super().__init__(engine=engine, subject=subject)
        self.killer = killer

    def _resolve(self) -> None:
        self.subject.pos = None


class SummonEvent(Event):
    def __init__(self, engine: Engine, summoner: Entity, subject: "Summon"):
        super().__init__(engine=engine, subject=subject)
        self.summoner = summoner

    def _resolve(self) -> None:
        pass  # should maybe set the summon's pos here?
        # If this is doing nothing it means the summoning couldn't be modified or cancelled by the before stage


class HealEvent(Event):
    def __init__(self, engine: Engine, subject: Entity, amount: int):
        super().__init__(engine=engine, subject=subject)
        self.amount = ModInt(amount)

    def _resolve(self) -> None:
        final_heal = max(0, self.amount.value)
        self.subject.hp += final_heal


class GiveTokenEvent(Event):
    def __init__(
        self, engine: Engine, subject: Entity, token_class: Type[Token], amount: int
    ):
        super().__init__(engine=engine, subject=subject)
        self.token_class = token_class
        self.amount = amount

    def _resolve(self):
        self.subject.add_token(self.token_class, amount=self.amount)
