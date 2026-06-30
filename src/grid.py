import math
from heapq import heappush, heappop
from itertools import count
from typing import Tuple, Set, List, Optional, TYPE_CHECKING
from collections import deque
from enum import Enum
from point import Point
from util import UniqueTuple

if TYPE_CHECKING:
    from engine import Engine
    from entities import Entity


Edge = Tuple[Point, Point]


class Direction(Enum):
    NORTH = Point(0, -1)
    SOUTH = Point(0, 1)
    EAST = Point(1, 0)
    WEST = Point(-1, 0)


_NEIGHBORS = (
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
)


class Grid:
    def __init__(self, width: int = 10, height: int = 10) -> None:
        self.width = width
        self.height = height
        self.walls: Set[Point] = set()
        self.edge_walls: Set[Edge] = set()
        self.engine: Optional["Engine"] = None

    def add_wall(self, p: Point) -> None:
        self.walls.add(p)

    def add_edge_wall(self, p1: Point, p2: Point) -> None:
        """Adds a wall on the edge between two adjacent spaces."""
        # Normalize the edge so order doesn't matter
        edge: Edge = tuple(sorted([p1, p2]))  # type: ignore
        self.edge_walls.add(edge)

    def get_range(self, p1: Point, p2: Point) -> int:
        """Calculates range where first step can be diagonal, subsequent must be orthogonal."""
        dx = abs(p1[0] - p2[0])
        dy = abs(p1[1] - p2[1])
        if dx > 0 and dy > 0:
            return dx + dy - 1
        return dx + dy

    def get_points_in_range(
        self,
        start: Point,
        max_range: int,
        blocking_los_points: Optional[Set[Point]] = None,
    ) -> UniqueTuple[Point]:
        """Finds all points within max_range, respecting walls. First step can be diagonal. Must have line of sight."""
        if max_range < 0 or start is None:
            return UniqueTuple()

        blocking_los_points = blocking_los_points or set()

        visited: dict[Point, int] = {}  # point to cost
        queue = deque([(start, 0)])

        while queue:
            curr, cost = queue.popleft()
            curr: Point

            if curr in visited and visited[curr] <= cost:
                continue
            visited[curr] = cost

            if cost >= max_range:
                continue

            x = curr.x
            y = curr.y

            # Diagonal moves possible as first step
            if cost == 0:
                for nx, ny in [
                    (x + 1, y + 1),
                    (x + 1, y - 1),
                    (x - 1, y + 1),
                    (x - 1, y - 1),
                ]:
                    point = Point(nx, ny)
                    if 0 <= nx < self.width and 0 <= ny < self.height:
                        # Check if diagonal movement is blocked by walls (corner cutting)
                        if point not in self.walls:
                            queue.append((point, cost + 1))
            # Orthogonal moves
            for nx, ny in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]:
                point = Point(nx, ny)
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    queue.append((point, cost + 1))

        visible_points = []
        for point in visited.keys():
            is_visible, _has_cover = self.get_line_of_sight(
                start_pos=start, target_pos=point, blocked_points=blocking_los_points
            )
            if is_visible:
                visible_points.append(point)
        return UniqueTuple(visible_points)

    def get_movable_spaces(
        self,
        actor: "Entity",
        max_movement: int,
    ) -> UniqueTuple[Point]:
        """Finds all points reachable within max_movement using orthogonal steps. Path is blocked by enemies. Cannot end on any occupied space."""
        start = actor.pos
        if max_movement < 0:
            return UniqueTuple()

        enemy_points = {
            e.pos
            for e in self.engine.entities
            if e.team != actor.team and e.hp > 0 and e.pos is not None
        }
        occupied_points = {
            e.pos
            for e in self.engine.entities
            if e.hp > 0 and e.pos is not None and e is not actor
        }

        visited = {start: 0}
        queue = deque([(start, 0)])

        while queue:
            curr, cost = queue.popleft()

            if cost >= max_movement:
                continue

            x, y = curr
            for nx, ny in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]:
                n = Point(nx, ny)
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    if not self.is_movement_blocked(curr, n) and n not in enemy_points:
                        if n not in visited or visited[n] > cost + 1:
                            visited[n] = cost + 1
                            queue.append((n, cost + 1))

        # Cannot end on occupied spaces
        reachable_points = [p for p in visited.keys() if p not in occupied_points]
        reachable_points.append(start)  # Can always stay where we are
        return UniqueTuple(reachable_points)

    def is_movement_blocked(
        self,
        current: Point,
        next_pos: Point,
    ) -> bool:
        """Checks if movement between two adjacent spaces is blocked by walls."""
        if next_pos in self.walls:
            return True
        if self.edge_walls:
            edge = tuple(sorted([current, next_pos]))
            if edge in self.edge_walls:
                return True
        return False

    def get_path(
        self,
        start: Point,
        target: Point,
        actor: "Entity",
        valid_step=None,
    ) -> Optional[tuple[Point]]:
        if start == target:
            return tuple(start)

        enemy_points = {
            e.pos
            for e in self.engine.entities
            if e.team != actor.team and e.hp > 0 and e.pos is not None
        }

        width = self.width
        height = self.height
        is_blocked = self.is_movement_blocked

        tx = target.x
        ty = target.y

        def heuristic(x: int, y: int) -> int:
            return abs(x - tx) + abs(y - ty)

        open_heap = []
        tie_breaker = count()

        g_score = {start: 0}
        parent = {start: None}

        heappush(
            open_heap,
            (
                heuristic(start.x, start.y),
                next(tie_breaker),
                start,
            ),
        )

        closed = set()

        while open_heap:
            _, _, curr = heappop(open_heap)

            if curr in closed:
                continue

            if curr == target:
                path = []
                while curr is not None:
                    path.append(curr)
                    curr = parent[curr]
                path.reverse()
                return tuple(path)

            closed.add(curr)

            x = curr.x
            y = curr.y
            curr_g = g_score[curr]

            for dx, dy in _NEIGHBORS:
                nx = x + dx
                ny = y + dy

                if nx < 0 or nx >= width or ny < 0 or ny >= height:
                    continue
                n = Point(nx, ny)
                if n in closed or n in enemy_points or is_blocked(curr, n):
                    continue
                if valid_step is not None and not valid_step(curr, n):
                    continue

                tentative_g = curr_g + 1

                if tentative_g < g_score.get(n, float("inf")):
                    g_score[n] = tentative_g
                    parent[n] = curr
                    heappush(
                        open_heap,
                        (
                            tentative_g + heuristic(nx, ny),
                            next(tie_breaker),
                            n,
                        ),
                    )

        return None

    def get_push_path(
        self, subject: "Entity", direction: Direction, distance: int
    ) -> List[Point]:
        """
        Finds a path of valid positions for a push in a specific direction.
        The path does not include the start point.
        """
        path = []
        current = subject.pos
        for _ in range(distance):
            next_pos = current + direction.value

            if not (0 <= next_pos.x < self.width and 0 <= next_pos.y < self.height):
                break  # Out of bounds

            if self.is_movement_blocked(current, next_pos):
                break  # Movement blocked by wall

            path.append(next_pos)
            current = next_pos

        return path

    def get_pull_path(
        self, subject: "Entity", pull_to: Point, distance: int
    ) -> List[Point]:
        """
        Finds a path of valid positions towards a pull point.
        The path does not include the start point.
        """
        path = []
        current = subject.pos
        for _ in range(distance):
            if current == pull_to:
                break

            neighbors = []
            x, y = current
            # Check orthogonal neighbors
            for nx, ny in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]:
                n = Point(nx, ny)
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    if not self.is_movement_blocked(current, n):
                        neighbors.append(n)

            if not neighbors:
                break

            # Move to neighbor closest to pull_to
            neighbors.sort(key=lambda p: self.get_range(p, pull_to))
            next_pos = neighbors[0]

            # Only move if it's actually closer
            if self.get_range(next_pos, pull_to) < self.get_range(current, pull_to):
                path.append(next_pos)
                current = next_pos
            else:
                break  # Can't get closer

        return path

    def get_line_of_sight(
        self,
        start_pos: "Point",
        target_pos: "Point",
        visualize_file: Optional[str] = None,
        blocked_points: Optional[Set["Point"]] = None,
    ) -> Tuple[bool, bool]:
        """
        Calculates visibility based strictly on corner-to-corner math.
        Returns (isVisible, hasCover).
        """
        if start_pos == target_pos:
            return True, False

        sx, sy = start_pos.x, start_pos.y
        tx, ty = target_pos.x, target_pos.y
        dx = tx - sx
        dy = ty - sy

        # Avoid O(N) set copying overhead; use a fast lookup helper instead
        walls = self.walls

        def is_blocked(p: Tuple[int, int]) -> bool:
            return (p in walls) or (blocked_points is not None and p in blocked_points)

        visible = True

        # 1. Handle simple horizontal/vertical/diagonal cases
        if dx == 0:
            step = 1 if dy > 0 else -1
            for y in range(sy + step, ty, step):
                if is_blocked((sx, y)):
                    visible = False
                    break
        elif dy == 0:
            step = 1 if dx > 0 else -1
            for x in range(sx + step, tx, step):
                if is_blocked((x, sy)):
                    visible = False
                    break
        elif abs(dx) == abs(dy):
            gap_w1 = (sx + (1 if dx > 0 else -1), sy)
            gap_w2 = (sx, sy + (1 if dy > 0 else -1))
            if is_blocked(gap_w1) and is_blocked(gap_w2):
                visible = False

        # 2. Perform ray tracing (DDA-style) if not already blocked
        if visible and dx != 0 and dy != 0:
            corner_x = 1.0 if dx >= 0 else 0.0
            corner_y = 1.0 if dy >= 0 else 0.0

            x0, y0 = float(sx + corner_x), float(sy + corner_y)
            x1, y1 = float(tx + corner_x), float(ty + corner_y)

            # Use multiplication instead of exponentiation (** 2 is slower in Python)
            distance = math.sqrt((x1 - x0) * (x1 - x0) + (y1 - y0) * (y1 - y0))

            if distance > 0:
                steps = int(distance * 2)
                if steps > 1:
                    # Pre-calculate step sizes instead of computing `t` every iteration
                    step_x = (x1 - x0) / steps
                    step_y = (y1 - y0) / steps

                    curr_x, curr_y = x0, y0
                    start_tup, target_tup = (sx, sy), (tx, ty)

                    EPSILON = 0.000001
                    UPPER_BOUND = 1.0 - EPSILON

                    for _ in range(1, steps):
                        curr_x += step_x
                        curr_y += step_y
                        grid_x = int(curr_x // 1)
                        grid_y = int(curr_y // 1)
                        grid_tup = (grid_x, grid_y)

                        if grid_tup != start_tup and grid_tup != target_tup:
                            if is_blocked(grid_tup):
                                local_x = curr_x % 1.0
                                local_y = curr_y % 1.0

                                if (EPSILON < local_x < UPPER_BOUND) and (
                                    EPSILON < local_y < UPPER_BOUND
                                ):
                                    visible = False
                                    break

        # 3. Covered Check (Must be visible)
        has_cover = False
        if visible:
            target_dist_sq = dx * dx + dy * dy
            neighbors = (
                (tx - 1, ty),
                (tx + 1, ty),
                (tx, ty - 1),
                (tx, ty + 1),
            )

            for nx, ny in neighbors:
                if (nx, ny) in walls:
                    wall_dist_sq = (nx - sx) * (nx - sx) + (ny - sy) * (ny - sy)
                    if wall_dist_sq < target_dist_sq:
                        has_cover = True
                        break

        return visible, has_cover
