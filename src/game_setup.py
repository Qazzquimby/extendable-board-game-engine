from dataclasses import dataclass
from typing import List, Type, Dict, Optional, TYPE_CHECKING

from engine import Engine, Agent
from entities import Entity
from grid import Grid
from point import Point

if TYPE_CHECKING:
    pass


@dataclass
class GameSetup:
    team0_classes: List[Type[Entity]]
    team1_classes: List[Type[Entity]]
    grid_size: int = 5

    def get_id(self) -> str:
        team0_names = sorted([cls.__name__ for cls in self.team0_classes])
        team1_names = sorted([cls.__name__ for cls in self.team1_classes])
        return f"g{self.grid_size}_t0_{'_'.join(team0_names)}_vs_t1_{'_'.join(team1_names)}"

    def create_engine(self, agents: Optional[Dict[int, "Agent"]] = None, seed: int = 42) -> Engine:
        engine = Engine(grid=Grid(self.grid_size, self.grid_size), agents=agents, setup=self, seed=seed)

        for i, entity_class in enumerate(self.team0_classes):
            entity_class(engine=engine, pos=Point(0, i), team=0)

        for i, entity_class in enumerate(self.team1_classes):
            entity_class(
                engine=engine,
                pos=Point(self.grid_size - 1, self.grid_size - (i + 1)),
                team=1,
            )
        engine.finalize_setup()
        return engine
