from typing import Set, List, Iterator, Callable, Optional

from grid import Grid
from point import Point


class Area:
    def __init__(self, in_range: int):
        self.in_range = in_range

    def get_selections(self, grid: Grid, start: Point) -> Iterator[Set[Point]]:
        """Yields all possible valid area selections from the start point."""
        raise NotImplementedError


class Burst(Area):
    def __init__(
        self,
        radius: int,
        in_range: int = 0,
        condition: Optional[Callable[[Set[Point]], bool]] = None,
    ):
        super().__init__(in_range=in_range)
        self.radius = radius
        self.range_limit = in_range
        self.condition = condition

    def get_selections(self, grid: Grid, start: Point) -> Iterator[Set[Point]]:
        # If range_limit is 0, it's centered on the start point
        centers = (
            {start}
            if self.range_limit == 0
            else grid.get_points_in_range(start, self.range_limit)
        )

        for center in centers:
            selection = grid.get_points_in_range(center, self.radius)
            if self.condition is None or self.condition(selection):
                yield selection


class Line(Area):
    def __init__(
        self,
        length: int,
        in_range: int = 0,
        condition: Optional[Callable[[Set[Point]], bool]] = None,
    ):
        super().__init__(in_range=in_range)
        self.length = length
        self.condition = condition

    def get_selections(self, grid: Grid, start: Point) -> Iterator[Set[Point]]:
        valid_starts = (
            {start}
            if self.in_range == 0
            else grid.get_points_in_range(start, self.in_range)
        )
        seen_lines = set()
        for s in valid_starts:
            for aim in grid.get_points_in_range(s, self.length):
                if aim == s:
                    continue
                line = tuple(get_line(grid, s, aim, self.length))
                if line and line not in seen_lines:
                    seen_lines.add(line)
                    points = set(line)
                    if self.condition is None or self.condition(points):
                        yield points


class Square(Area):
    def __init__(
        self,
        side_length: int,
        in_range: int = 0,
        condition: Optional[Callable[[Set[Point]], bool]] = None,
    ):
        super().__init__(in_range=in_range)
        self.side_length = side_length
        self.in_range = in_range
        self.condition = condition

    def get_selections(self, grid: Grid, start: Point) -> Iterator[Set[Point]]:
        valid_starts = (
            {start}
            if self.in_range == 0
            else grid.get_points_in_range(start, self.in_range)
        )

        seen_squares = set()

        for start in valid_starts:
            for leftmost in range(start.x - self.side_length + 1, start.x + 1):
                for topmost in range(start.y - self.side_length + 1, start.y + 1):
                    points = set()
                    for offset_x in range(self.side_length):
                        for offset_y in range(self.side_length):
                            cell = Point(leftmost + offset_x, topmost + offset_y)
                            if 0 <= cell.x < grid.width and 0 <= cell.y < grid.height:
                                # Check if there's a valid path to the square's points (respecting walls)
                                if cell in grid.get_points_in_range(
                                    start, self.side_length
                                ):
                                    points.add(cell)

                    if points:
                        frozen_points = frozenset(points)
                        if frozen_points not in seen_squares:
                            seen_squares.add(frozen_points)
                            if self.condition is None or self.condition(points):
                                yield points


def get_line(grid: Grid, start: Point, target: Point, length: int) -> List[Point]:
    """
    Returns a line of points originating from start, passing through target,
    up to the specified length, stopping at walls.
    """
    if start == target or length <= 0:
        return []

    x0, y0 = start
    x1, y1 = target

    dx = x1 - x0
    dy = y1 - y0

    steps = max(abs(dx), abs(dy))
    if steps == 0:
        return []

    step_x = dx / steps
    step_y = dy / steps

    line = []
    curr = start
    for i in range(1, length + 1):
        nx = round(x0 + step_x * i)
        ny = round(y0 + step_y * i)
        next_point = Point(nx, ny)

        if not (0 <= nx < grid.width and 0 <= ny < grid.height):
            break

        if grid.is_movement_blocked(curr, next_point):
            break

        line.append(next_point)
        curr = next_point

    return line
