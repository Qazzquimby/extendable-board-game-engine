import math
from typing import Tuple, Set, List, Optional, Callable, TYPE_CHECKING
from collections import deque
from enum import Enum
from point import Point

if TYPE_CHECKING:
    from engine import Engine
    from entities import Entity


Edge = Tuple[Point, Point]


class Direction(Enum):
    NORTH = Point(0, -1)
    SOUTH = Point(0, 1)
    EAST = Point(1, 0)
    WEST = Point(-1, 0)


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
    ) -> Set[Point]:
        """Finds all points within max_range, respecting walls. First step can be diagonal. Must have line of sight."""
        if max_range < 0 or start is None:
            return set()

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

        visible_points = set()
        for point in visited.keys():
            is_visible, _has_cover = self.get_line_of_sight(
                start_pos=start, target_pos=point, blocked_points=blocking_los_points
            )
            if is_visible:
                visible_points.add(point)
        return visible_points

    def get_movable_spaces(
        self,
        actor: "Entity",
        max_movement: int,
    ) -> Set[Point]:
        """Finds all points reachable within max_movement using orthogonal steps. Path is blocked by enemies. Cannot end on any occupied space."""
        start = actor.pos
        if max_movement < 0:
            return set()

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
                    if not self.is_movement_blocked(
                        curr, n
                    ) and n not in enemy_points:
                        if n not in visited or visited[n] > cost + 1:
                            visited[n] = cost + 1
                            queue.append((n, cost + 1))

        # Cannot end on occupied spaces
        reachable_points = {p for p in visited.keys() if p not in occupied_points}
        reachable_points.add(start)  # Can always stay where we are
        return reachable_points

    def is_movement_blocked(
        self,
        current: Point,
        next_pos: Point,
    ) -> bool:
        """Checks if movement between two adjacent spaces is blocked by walls."""
        if next_pos in self.walls:
            return True
        edge = tuple(sorted([current, next_pos]))
        if edge in self.edge_walls:
            return True
        return False

    def get_path(
        self,
        start: Point,
        target: Point,
        actor: "Entity",
        visualize_file: Optional[str] = None,
        valid_step: Optional[Callable[[Point, Point], bool]] = None,
    ) -> Optional[List[Point]]:
        """Finds the shortest path using BFS, respecting walls and edge walls."""
        if start == target:
            if visualize_file:
                with open(visualize_file, "w") as f:
                    f.write(self.visualize(start=start, target=target, path=[start]))
            return [start]

        enemy_points = {
            e.pos
            for e in self.engine.entities
            if e.team != actor.team and e.hp > 0 and e.pos is not None
        }

        queue: deque[List[Point]] = deque([[start]])
        visited: Set[Point] = {start}

        while queue:
            path = queue.popleft()
            curr = path[-1]

            if curr == target:
                if visualize_file:
                    with open(visualize_file, "w") as f:
                        f.write(self.visualize(start=start, target=target, path=path))
                return path

            x, y = curr
            for nx, ny in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]:
                n = Point(nx, ny)
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    if (
                        n not in visited
                        and not self.is_movement_blocked(curr, n)
                        and n not in enemy_points
                    ):
                        if valid_step is None or valid_step(curr, n):
                            visited.add(n)
                            queue.append(path + [n])

        if visualize_file:
            with open(visualize_file, "w") as f:
                f.write(self.visualize(start=start, target=target, path=None))
        return None

    def get_push_path(
        self, subject: "Entity", direction: Direction, distance: int
    ) -> List[Point]:
        """
        Finds a path of valid positions for a push in a specific direction.
        The path does not include the start point.
        """
        occupied_points = {
            e.pos
            for e in self.engine.entities
            if e.hp > 0 and e.pos is not None and e is not subject
        }

        path = []
        current = subject.pos
        for _ in range(distance):
            next_pos = current + direction.value

            if not (0 <= next_pos.x < self.width and 0 <= next_pos.y < self.height):
                break  # Out of bounds

            if self.is_movement_blocked(current, next_pos) or next_pos in occupied_points:
                break  # Movement blocked

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
        occupied_points = {
            e.pos
            for e in self.engine.entities
            if e.hp > 0 and e.pos is not None and e is not subject
        }

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
                    if not self.is_movement_blocked(current, n) and n not in occupied_points:
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
        start_pos: Point,
        target_pos: Point,
        visualize_file: Optional[str] = None,
        blocked_points: Optional[Set[Point]] = None,
    ) -> Tuple[bool, bool]:
        """
        Calculates visibility based strictly on corner-to-corner math.
        Returns (isVisible, hasCover).
        """
        if blocked_points:
            blocked_points = blocked_points.copy()
            blocked_points.update(self.walls)
        else:
            blocked_points = self.walls.copy()

        if start_pos == target_pos:
            if visualize_file:
                with open(visualize_file, "w") as f:
                    f.write(
                        self.visualize(
                            start=start_pos,
                            target=target_pos,
                            visible=True,
                            has_cover=False,
                        )
                    )
            return True, False

        # 1. Corner Selection based on proximity
        corner_x = 1.0 if target_pos.x >= start_pos.x else 0.0
        corner_y = 1.0 if target_pos.y >= start_pos.y else 0.0

        # Mathematical float coordinates of the chosen corners
        x0, y0 = float(start_pos.x + corner_x), float(start_pos.y + corner_y)
        x1, y1 = float(target_pos.x + corner_x), float(target_pos.y + corner_y)

        # 2. Geometry Check: Does the segment intersect any wall interior?
        visible = True

        # Handle the simple diagonal cases first (common rule: squeezing points is blocked)
        dx = target_pos.x - start_pos.x
        dy = target_pos.y - start_pos.y
        if dx == 0:
            step = 1 if dy > 0 else -1
            for y in range(start_pos.y + step, target_pos.y, step):
                if (start_pos.x, y) in blocked_points:
                    visible = False
                    break
        elif dy == 0:
            step = 1 if dx > 0 else -1
            for x in range(start_pos.x + step, target_pos.x, step):
                if (x, start_pos.y) in blocked_points:
                    visible = False
                    break
        elif abs(dx) == abs(dy):
            gap_w1 = (start_pos.x + (1 if dx > 0 else -1), start_pos.y)
            gap_w2 = (start_pos.x, start_pos.y + (1 if dy > 0 else -1))
            if gap_w1 in blocked_points and gap_w2 in blocked_points:
                visible = False

        # Perform ray tracing (DDA-style) if not already blocked
        if visible:
            distance = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
            if distance > 0:
                steps = distance * 2
                for i in range(1, int(steps)):
                    t = i / steps
                    curr_x = x0 + t * (x1 - x0)
                    curr_y = y0 + t * (y1 - y0)

                    grid_x, grid_y = math.floor(curr_x), math.floor(curr_y)
                    local_x, local_y = curr_x % 1.0, curr_y % 1.0

                    if Point(grid_x, grid_y) in blocked_points:
                        if (grid_x, grid_y) == (start_pos.x, start_pos.y) or (
                            grid_x,
                            grid_y,
                        ) == (target_pos.x, target_pos.y):
                            continue

                        EPSILON = 0.000001
                        if (EPSILON < local_x < (1.0 - EPSILON)) and (
                            EPSILON < local_y < (1.0 - EPSILON)
                        ):
                            visible = False
                            break

        # 3. Covered Check (Must be visible)
        has_cover = False
        if visible:
            neighbors = [
                (target_pos.x - 1, target_pos.y),
                (target_pos.x + 1, target_pos.y),
                (target_pos.x, target_pos.y - 1),
                (target_pos.x, target_pos.y + 1),
            ]
            target_dist = (target_pos.x - start_pos.x) ** 2 + (
                target_pos.y - start_pos.y
            ) ** 2
            for nx, ny in neighbors:
                if (nx, ny) in self.walls:
                    wall_dist = (nx - start_pos.x) ** 2 + (ny - start_pos.y) ** 2
                    if wall_dist < target_dist:
                        has_cover = True
                        break

        if visualize_file:
            with open(visualize_file, "w") as f:
                f.write(
                    self.visualize(
                        start=start_pos,
                        target=target_pos,
                        visible=visible,
                        has_cover=has_cover,
                    )
                )

        return visible, has_cover

    def _render_html(self, color_func, legend_html: str) -> str:
        html = ['<table style="border-collapse: collapse;">']
        for y in range(self.height):
            html.append("  <tr>")
            for x in range(self.width):
                color = color_func(Point(x, y))
                html.append(
                    f'    <td style="width: 20px; height: 20px; background-color: {color}; border: 1px solid #ccc;"></td>'
                )
            html.append("  </tr>")
        html.append("</table>")

        html.append('<div style="margin-top: 10px; font-family: sans-serif;">')
        html.append(legend_html)
        html.append("</div>")

        return "\n".join(html)

    def visualize(
        self,
        start: Optional[Point] = None,
        target: Optional[Point] = None,
        path: Optional[List[Point]] = None,
        visible: Optional[bool] = None,
        has_cover: Optional[bool] = None,
    ) -> str:
        path_set = set(path) if path else set()

        def get_color(p: Point) -> str:
            if p == start:
                return "green"
            if p == target:
                return "red"
            if p in self.walls:
                return "black"
            if p in path_set:
                return "blue"
            return "white"

        legend = [
            "<strong>Legend:</strong><br>",
            '<span style="display:inline-block; width:15px; height:15px; background-color:green; border:1px solid #ccc;"></span> Start<br>',
            '<span style="display:inline-block; width:15px; height:15px; background-color:red; border:1px solid #ccc;"></span> Target<br>',
            '<span style="display:inline-block; width:15px; height:15px; background-color:black; border:1px solid #ccc;"></span> Wall<br>',
            '<span style="display:inline-block; width:15px; height:15px; background-color:blue; border:1px solid #ccc;"></span> Path<br>',
        ]
        if visible is not None:
            legend.append(
                f'<br><strong>Line of Sight:</strong> {"Visible" if visible else "Blocked"}'
            )
            if has_cover:
                legend.append(" (Covered)")

        return self._render_html(get_color, "\n".join(legend))

    def visualize_visibility(self, start: Point) -> str:
        def get_color(p: Point) -> str:
            if p == start:
                return "green"
            if p in self.walls:
                return "black"
            visible, covered = self.get_line_of_sight(start, p)
            if not visible:
                return "darkgray"
            if covered:
                return "yellow"
            return "lightblue"

        legend = [
            "<strong>Visibility Legend:</strong><br>",
            '<span style="display:inline-block; width:15px; height:15px; background-color:green; border:1px solid #ccc;"></span> Start<br>',
            '<span style="display:inline-block; width:15px; height:15px; background-color:black; border:1px solid #ccc;"></span> Wall<br>',
            '<span style="display:inline-block; width:15px; height:15px; background-color:lightblue; border:1px solid #ccc;"></span> Visible<br>',
            '<span style="display:inline-block; width:15px; height:15px; background-color:yellow; border:1px solid #ccc;"></span> Covered<br>',
            '<span style="display:inline-block; width:15px; height:15px; background-color:darkgray; border:1px solid #ccc;"></span> Hidden<br>',
        ]
        return self._render_html(get_color, "\n".join(legend))
