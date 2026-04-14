from typing import Tuple, Set, List, Iterator
from grid import Grid

Point = Tuple[int, int]


class Area:
    def get_selections(self, grid: Grid, start: Point) -> Iterator[Set[Point]]:
        """Yields all possible valid area selections from the start point."""
        raise NotImplementedError


class Burst(Area):
    def __init__(self, radius: int, range_limit: int = 0):
        self.radius = radius
        self.range_limit = range_limit

    def get_selections(self, grid: Grid, start: Point) -> Iterator[Set[Point]]:
        # If range_limit is 0, it's centered on the start point
        centers = {start} if self.range_limit == 0 else grid.get_points_in_range(start, self.range_limit)
        
        for center in centers:
            yield grid.get_points_in_range(center, self.radius)


class Square(Area):
    def __init__(self, size: int, range_limit: int = 0):
        self.size = size
        self.range_limit = range_limit

    def get_selections(self, grid: Grid, start: Point) -> Iterator[Set[Point]]:
        centers = {start} if self.range_limit == 0 else grid.get_points_in_range(start, self.range_limit)
        
        offset = self.size // 2
        for cx, cy in centers:
            points = set()
            for dx in range(-offset, self.size - offset):
                for dy in range(-offset, self.size - offset):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < grid.width and 0 <= ny < grid.height:
                        # Check if there's a valid path to the square's points (respecting walls)
                        if (nx, ny) in grid.get_points_in_range((cx, cy), self.size):
                            points.add((nx, ny))
            if points:
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
        nxt = (nx, ny)
        
        if not (0 <= nx < grid.width and 0 <= ny < grid.height):
            break
            
        if grid.is_movement_blocked(curr, nxt):
            break
            
        line.append(nxt)
        curr = nxt

    return line
