import math
from typing import Tuple, Set, List, Optional
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

    def is_movement_blocked(self, current: Point, next_pos: Point) -> bool:
        """Checks if movement between two adjacent spaces is blocked."""
        if next_pos in self.walls:
            return True
        edge = tuple(sorted([current, next_pos]))
        if edge in self.edge_walls:
            return True
        return False

    def get_path(self, start: Point, target: Point, visualize_file: Optional[str] = None) -> Optional[List[Point]]:
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
                        visited.add(n)
                        queue.append(path + [n])
        
        if visualize_file:
            with open(visualize_file, 'w') as f:
                f.write(self.visualize(start=start, target=target, path=None))
        return None

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
        if abs(dx) == abs(dy):
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

        # 3. Grazing Check (Must be visible)
        grazing = False
        if visible:
            neighbors = [(target_x - 1, target_y), (target_x + 1, target_y),
                         (target_x, target_y - 1), (target_x, target_y + 1)]
            target_dist = (target_x - start_x) ** 2 + (target_y - start_y) ** 2
            for nx, ny in neighbors:
                if (nx, ny) in self.walls:
                    wall_dist = (nx - start_x) ** 2 + (ny - start_y) ** 2
                    if wall_dist < target_dist:
                        grazing = True
                        break

        if visualize_file:
            with open(visualize_file, 'w') as f:
                f.write(self.visualize(start=start_pos, target=target_pos, visible=visible, grazing=grazing))

        return visible, grazing

    def visualize(self, start: Optional[Point] = None, target: Optional[Point] = None, path: Optional[List[Point]] = None, visible: Optional[bool] = None, grazing: Optional[bool] = None) -> str:
        path_set = set(path) if path else set()
        html = ['<table style="border-collapse: collapse;">']
        for y in range(self.height):
            html.append('  <tr>')
            for x in range(self.width):
                p = (x, y)
                color = "white"
                if p == start:
                    color = "green"
                elif p == target:
                    color = "red"
                elif p in self.walls:
                    color = "black"
                elif p in path_set:
                    color = "blue"
                html.append(f'    <td style="width: 20px; height: 20px; background-color: {color}; border: 1px solid #ccc;"></td>')
            html.append('  </tr>')
        html.append('</table>')
        
        html.append('<div style="margin-top: 10px; font-family: sans-serif;">')
        html.append('<strong>Legend:</strong><br>')
        html.append('<span style="display:inline-block; width:15px; height:15px; background-color:green; border:1px solid #ccc;"></span> Start<br>')
        html.append('<span style="display:inline-block; width:15px; height:15px; background-color:red; border:1px solid #ccc;"></span> Target<br>')
        html.append('<span style="display:inline-block; width:15px; height:15px; background-color:black; border:1px solid #ccc;"></span> Wall<br>')
        html.append('<span style="display:inline-block; width:15px; height:15px; background-color:blue; border:1px solid #ccc;"></span> Path<br>')
        
        if visible is not None:
            html.append(f'<br><strong>Line of Sight:</strong> {"Visible" if visible else "Blocked"}')
            if grazing:
                html.append(' (Grazing)')
        
        html.append('</div>')
        
        return "\n".join(html)

    def visualize_visibility(self, start: Point) -> str:
        html = ['<table style="border-collapse: collapse;">']
        for y in range(self.height):
            html.append('  <tr>')
            for x in range(self.width):
                p = (x, y)
                color = "white"
                if p == start:
                    color = "green"
                elif p in self.walls:
                    color = "black"
                else:
                    visible, grazing = self.get_line_of_sight(start, p)
                    if not visible:
                        color = "darkgray"
                    elif grazing:
                        color = "yellow"
                    else:
                        color = "lightblue"
                html.append(f'    <td style="width: 20px; height: 20px; background-color: {color}; border: 1px solid #ccc;"></td>')
            html.append('  </tr>')
        html.append('</table>')
        
        html.append('<div style="margin-top: 10px; font-family: sans-serif;">')
        html.append('<strong>Visibility Legend:</strong><br>')
        html.append('<span style="display:inline-block; width:15px; height:15px; background-color:green; border:1px solid #ccc;"></span> Start<br>')
        html.append('<span style="display:inline-block; width:15px; height:15px; background-color:black; border:1px solid #ccc;"></span> Wall<br>')
        html.append('<span style="display:inline-block; width:15px; height:15px; background-color:lightblue; border:1px solid #ccc;"></span> Visible<br>')
        html.append('<span style="display:inline-block; width:15px; height:15px; background-color:yellow; border:1px solid #ccc;"></span> Grazing<br>')
        html.append('<span style="display:inline-block; width:15px; height:15px; background-color:darkgray; border:1px solid #ccc;"></span> Hidden<br>')
        html.append('</div>')
        
        return "\n".join(html)

