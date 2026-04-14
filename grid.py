import math
from typing import Tuple, Set, List, Optional, Callable
from collections import deque

Point = Tuple[int, int]
Edge = Tuple[Point, Point]


class Grid:
    def __init__(self, width: int = 10, height: int = 10) -> None:
        self.width = width
        self.height = height
        self.walls: Set[Point] = set()
        self.edge_walls: Set[Edge] = set()

    def add_wall(self, p: Point) -> None:
        self.walls.add(p)

    def add_edge_wall(self, p1: Point, p2: Point) -> None:
        """Adds a wall on the edge between two adjacent spaces."""
        # Normalize the edge so order doesn't matter
        edge: Edge = tuple(sorted([p1, p2])) # type: ignore
        self.edge_walls.add(edge)

    def get_range(self, p1: Point, p2: Point) -> int:
        """Calculates range where first step can be diagonal, subsequent must be orthogonal."""
        dx = abs(p1[0] - p2[0])
        dy = abs(p1[1] - p2[1])
        if dx > 0 and dy > 0:
            return dx + dy - 1
        return dx + dy

    def is_movement_blocked(self, current: Point, next_pos: Point) -> bool:
        """Checks if movement between two adjacent spaces is blocked."""
        if next_pos in self.walls:
            return True
        edge = tuple(sorted([current, next_pos]))
        if edge in self.edge_walls:
            return True
        return False

    def get_path(self, start: Point, target: Point, visualize_file: Optional[str] = None, valid_step: Optional[Callable[[Point, Point], bool]] = None) -> Optional[List[Point]]:
        """Finds the shortest path using BFS, respecting walls and edge walls."""
        if start == target:
            if visualize_file:
                with open(visualize_file, 'w') as f:
                    f.write(self.visualize(start=start, target=target, path=[start]))
            return [start]

        queue: deque[List[Point]] = deque([[start]])
        visited: Set[Point] = {start}

        while queue:
            path = queue.popleft()
            curr = path[-1]

            if curr == target:
                if visualize_file:
                    with open(visualize_file, 'w') as f:
                        f.write(self.visualize(start=start, target=target, path=path))
                return path

            x, y = curr
            for nx, ny in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]:
                n = (nx, ny)
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    if n not in visited and not self.is_movement_blocked(curr, n):
                        if valid_step is None or valid_step(curr, n):
                            visited.add(n)
                            queue.append(path + [n])

        if visualize_file:
            with open(visualize_file, 'w') as f:
                f.write(self.visualize(start=start, target=target, path=None))
        return None

    def get_push_path(self, start: Point, target: Point, push_from: Point) -> Optional[List[Point]]:
        """Finds a path where every step moves further away from the push_from point."""
        def is_away(curr: Point, nxt: Point) -> bool:
            return self.get_range(nxt, push_from) > self.get_range(curr, push_from)
        return self.get_path(start, target, valid_step=is_away)

    def get_pull_path(self, start: Point, target: Point, pull_to: Point) -> Optional[List[Point]]:
        """Finds a path where every step moves closer to the pull_to point."""
        def is_toward(curr: Point, nxt: Point) -> bool:
            return self.get_range(nxt, pull_to) < self.get_range(curr, pull_to)
        return self.get_path(start, target, valid_step=is_toward)

    def get_line_of_sight(self, start_pos: Point, target_pos: Point, visualize_file: Optional[str] = None) -> \
    Tuple[bool, bool]:
        """
        Calculates visibility based strictly on corner-to-corner math.
        Returns (isVisible, isGrazing).
        """
        start_x, start_y = start_pos
        target_x, target_y = target_pos

        if start_pos == target_pos:
            if visualize_file:
                with open(visualize_file, 'w') as f:
                    f.write(self.visualize(start=start_pos, target=target_pos, visible=True, grazing=False))
            return True, False

        # 1. Corner Selection based on proximity
        corner_x = 1.0 if target_x >= start_x else 0.0
        corner_y = 1.0 if target_y >= start_y else 0.0

        # Mathematical float coordinates of the chosen corners
        x0, y0 = float(start_x + corner_x), float(start_y + corner_y)
        x1, y1 = float(target_x + corner_x), float(target_y + corner_y)

        # 2. Geometry Check: Does the segment intersect any wall interior?
        visible = True

        # Handle the simple diagonal cases first (common rule: squeezing points is blocked)
        dx = target_x - start_x
        dy = target_y - start_y
        if dx == 0:
            step = 1 if dy > 0 else -1
            for y in range(start_y + step, target_y, step):
                if (start_x, y) in self.walls:
                    visible = False
                    break
        elif dy == 0:
            step = 1 if dx > 0 else -1
            for x in range(start_x + step, target_x, step):
                if (x, start_y) in self.walls:
                    visible = False
                    break
        elif abs(dx) == abs(dy):
            gap_w1 = (start_x + (1 if dx > 0 else -1), start_y)
            gap_w2 = (start_x, start_y + (1 if dy > 0 else -1))
            if gap_w1 in self.walls and gap_w2 in self.walls:
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

                    if (grid_x, grid_y) in self.walls:
                        if (grid_x, grid_y) == (start_x, start_y) or (
                        grid_x, grid_y) == (target_x, target_y):
                            continue

                        EPSILON = 0.000001
                        if (EPSILON < local_x < (1.0 - EPSILON)) and (
                                EPSILON < local_y < (1.0 - EPSILON)):
                            visible = False
                            break

        # 3. Covered Check (Must be visible)
        covered = False
        if visible:
            neighbors = [(target_x - 1, target_y), (target_x + 1, target_y),
                         (target_x, target_y - 1), (target_x, target_y + 1)]
            target_dist = (target_x - start_x) ** 2 + (target_y - start_y) ** 2
            for nx, ny in neighbors:
                if (nx, ny) in self.walls:
                    wall_dist = (nx - start_x) ** 2 + (ny - start_y) ** 2
                    if wall_dist < target_dist:
                        covered = True
                        break

        if visualize_file:
            with open(visualize_file, 'w') as f:
                f.write(self.visualize(start=start_pos, target=target_pos, visible=visible, grazing=covered))

        return visible, covered

    def _render_html(self, color_func, legend_html: str) -> str:
        html = ['<table style="border-collapse: collapse;">']
        for y in range(self.height):
            html.append('  <tr>')
            for x in range(self.width):
                color = color_func((x, y))
                html.append(f'    <td style="width: 20px; height: 20px; background-color: {color}; border: 1px solid #ccc;"></td>')
            html.append('  </tr>')
        html.append('</table>')

        html.append('<div style="margin-top: 10px; font-family: sans-serif;">')
        html.append(legend_html)
        html.append('</div>')

        return "\n".join(html)

    def visualize(self, start: Optional[Point] = None, target: Optional[Point] = None, path: Optional[List[Point]] = None, visible: Optional[bool] = None, grazing: Optional[bool] = None) -> str:
        path_set = set(path) if path else set()

        def get_color(p: Point) -> str:
            if p == start: return "green"
            if p == target: return "red"
            if p in self.walls: return "black"
            if p in path_set: return "blue"
            return "white"

        legend = [
            '<strong>Legend:</strong><br>',
            '<span style="display:inline-block; width:15px; height:15px; background-color:green; border:1px solid #ccc;"></span> Start<br>',
            '<span style="display:inline-block; width:15px; height:15px; background-color:red; border:1px solid #ccc;"></span> Target<br>',
            '<span style="display:inline-block; width:15px; height:15px; background-color:black; border:1px solid #ccc;"></span> Wall<br>',
            '<span style="display:inline-block; width:15px; height:15px; background-color:blue; border:1px solid #ccc;"></span> Path<br>'
        ]
        if visible is not None:
            legend.append(f'<br><strong>Line of Sight:</strong> {"Visible" if visible else "Blocked"}')
            if grazing:
                legend.append(' (Grazing)')

        return self._render_html(get_color, "\n".join(legend))

    def visualize_visibility(self, start: Point) -> str:
        def get_color(p: Point) -> str:
            if p == start: return "green"
            if p in self.walls: return "black"
            visible, covered = self.get_line_of_sight(start, p)
            if not visible: return "darkgray"
            if covered: return "yellow"
            return "lightblue"

        legend = [
            '<strong>Visibility Legend:</strong><br>',
            '<span style="display:inline-block; width:15px; height:15px; background-color:green; border:1px solid #ccc;"></span> Start<br>',
            '<span style="display:inline-block; width:15px; height:15px; background-color:black; border:1px solid #ccc;"></span> Wall<br>',
            '<span style="display:inline-block; width:15px; height:15px; background-color:lightblue; border:1px solid #ccc;"></span> Visible<br>',
            '<span style="display:inline-block; width:15px; height:15px; background-color:yellow; border:1px solid #ccc;"></span> Grazing<br>',
            '<span style="display:inline-block; width:15px; height:15px; background-color:darkgray; border:1px solid #ccc;"></span> Hidden<br>'
        ]
        return self._render_html(get_color, "\n".join(legend))
