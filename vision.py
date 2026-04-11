import math


# todo typing
# todo visualizer

def calculate_full_field_of_view(start_x, start_y, grid_width, grid_height, walls):
    """
    Calculates all visible cells from a start position using recursive shadowcasting
    adapted for corner-to-corner geometry.
    """
    visible_cells = {(start_x, start_y)}
    grazing_cells = set()

    # Scan each of the 8 octants
    for octant in range(8):
        scan_octant(
            start_x, start_y, 1, 1.0, 0.0,
            grid_width, grid_height, walls,
            octant, visible_cells, grazing_cells
        )

    return visible_cells, grazing_cells


def scan_octant(start_x, start_y, row, start_slope, end_slope,
                grid_width, grid_height, walls, octant,
                visible_set, grazing_set):
    if start_slope < end_slope:
        return

    for distance in range(row, max(grid_width, grid_height)):
        blocked = False
        next_start_slope = start_slope

        # Calculate the range of cells in this row/column
        for column in range(distance + 1):
            # Transform relative coordinates to global grid coordinates based on octant
            relative_x, relative_y = transform_octant(column, distance, octant)
            target_x = start_x + relative_x
            target_y = start_y + relative_y

            if not (0 <= target_x < grid_width and 0 <= target_y < grid_height):
                continue

            # Calculate slopes of the current cell's corners relative to start
            # For visibility, we check the 'inner' and 'outer' slopes of the tile
            left_slope = (column + 0.5) / (distance - 0.5)
            right_slope = (column - 0.5) / (distance + 0.5)

            if start_slope < right_slope:
                continue
            if end_slope > left_slope:
                break

            # If it's within the current view arc, it's visible
            visible_set.add((target_x, target_y))

            # Check for Grazing
            if is_grazing(start_x, start_y, target_x, target_y, walls):
                grazing_set.add((target_x, target_y))

            # Handle wall transitions to cast shadows
            is_wall = (target_x, target_y) in walls
            if blocked:
                if is_wall:
                    next_start_slope = right_slope
                else:
                    blocked = False
                    start_slope = next_start_slope
            else:
                if is_wall and distance > 0:
                    blocked = True
                    scan_octant(start_x, start_y, distance + 1, start_slope, left_slope,
                                grid_width, grid_height, walls, octant,
                                visible_set, grazing_set)
                    next_start_slope = right_slope

        if blocked:
            break


def is_grazing(start_x, start_y, target_x, target_y, walls):
    """
    Checks if a visible target has an orthogonally adjacent wall
    situated between the start and the target.
    """
    neighbors = [
        (target_x - 1, target_y), (target_x + 1, target_y),
        (target_x, target_y - 1), (target_x, target_y + 1)
    ]
    target_distance_sq = (target_x - start_x) ** 2 + (target_y - start_y) ** 2

    for neighbor_x, neighbor_y in neighbors:
        if (neighbor_x, neighbor_y) in walls:
            wall_distance_sq = (neighbor_x - start_x) ** 2 + (neighbor_y - start_y) ** 2
            if wall_distance_sq < target_distance_sq:
                return True
    return False


def transform_octant(row, col, octant):
    """Maps local octant coordinates to global relative coordinates."""
    if octant == 0: return (col, -row)
    if octant == 1: return (row, -col)
    if octant == 2: return (row, col)
    if octant == 3: return (col, row)
    if octant == 4: return (-col, row)
    if octant == 5: return (-row, col)
    if octant == 6: return (-row, -col)
    if octant == 7: return (-col, -row)