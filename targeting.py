import math
from typing import Tuple, Set, List

Point = Tuple[int, int]

def get_burst(center: Point, radius: int) -> Set[Point]:
    """
    Returns all points within a Chebyshev distance (grid range) of the center.
    """
    cx, cy = center
    points = set()
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            if max(abs(dx), abs(dy)) <= radius:
                points.add((cx + dx, cy + dy))
    return points

def get_line(start: Point, target: Point, length: int) -> List[Point]:
    """
    Returns a line of points originating from start, passing through target, 
    up to the specified length.
    """
    if start == target or length <= 0:
        return []
    
    x0, y0 = start
    x1, y1 = target
    
    dx = x1 - x0
    dy = y1 - y0
    
    # Normalize for grid steps using Chebyshev distance
    steps = max(abs(dx), abs(dy))
    if steps == 0:
        return []
        
    step_x = dx / steps
    step_y = dy / steps
    
    line = []
    for i in range(1, length + 1):
        nx = round(x0 + step_x * i)
        ny = round(y0 + step_y * i)
        line.append((nx, ny))
        
    return line
