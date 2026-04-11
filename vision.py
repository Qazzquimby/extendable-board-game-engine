import math

# todo typing
# this is inefficient, want to quickly get full set of spaces in los.
# has edge cases particularly around corners.
def get_line_of_sight(start_pos, target_pos, walls):
    """
    Calculates visibility based strictly on corner-to-corner math.
    Returns (isVisible, isGrazing).
    """
    start_x, start_y = start_pos
    target_x, target_y = target_pos

    if start_pos == target_pos:
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
    # If looking NW through a gap between a North and West wall, block it.
    dx = target_x - start_x
    dy = target_y - start_y
    if abs(dx) == abs(dy):
        # Check standard diagonal gap blockage
        gap_w1 = (start_x + (1 if dx > 0 else -1), start_y)
        gap_w2 = (start_x, start_y + (1 if dy > 0 else -1))
        if gap_w1 in walls and gap_w2 in walls:
            visible = False

    # Perform ray tracing (DDA-style) if not already blocked
    if visible:
        distance = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
        if distance > 0:
            # Step size for intersection checks
            steps = distance * 2
            for i in range(1, int(steps)):
                t = i / steps
                # Sample point on the line segment
                curr_x = x0 + t * (x1 - x0)
                curr_y = y0 + t * (y1 - y0)

                # Check if this point lies strictly INSIDE a wall
                # We use floor() to get grid coord, and then add epsilon
                # to check if the point is within the (epsilon, 1-epsilon) range of the tile.
                grid_x, grid_y = math.floor(curr_x), math.floor(curr_y)
                local_x, local_y = curr_x % 1.0, curr_y % 1.0

                # If point is inside a wall tile and not in the "scraping" zone (near boundary)
                if (grid_x, grid_y) in walls:
                    # Ignore the start and end cells
                    if (grid_x, grid_y) == (start_x, start_y) or (grid_x, grid_y) == (target_x, target_y):
                        continue

                    # Rule: Only passing through the tile *interior* blocks.
                    # We define interior as being more than EPSILON away from 0.0 or 1.0
                    EPSILON = 0.000001
                    if (EPSILON < local_x < (1.0 - EPSILON)) and (
                            EPSILON < local_y < (1.0 - EPSILON)):
                        visible = False
                        break

    # 3. Grazing Check (Must be visible)
    grazing = False
    if visible:
        neighbors = [(target_x - 1, target_y), (target_x + 1, target_y), (target_x, target_y - 1), (target_x, target_y + 1)]
        target_dist = (target_x - start_x) ** 2 + (target_y - start_y) ** 2
        for nx, ny in neighbors:
            if (nx, ny) in walls:
                # If wall is orthogonally adjacent and closer to start
                wall_dist = (nx - start_x) ** 2 + (ny - start_y) ** 2
                if wall_dist < target_dist:
                    grazing = True
                    break

    return visible, grazing