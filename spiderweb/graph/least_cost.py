from __future__ import annotations

import heapq
import numpy as np


def least_cost_path(cost_surface, start, goal):
    """Compute a least-cost path across a raster grid.

    start and goal are (row, col) tuples.
    Returns a list of cells representing the path.
    """

    rows, cols = cost_surface.shape
    visited = set()
    queue = [(0, start, [])]

    while queue:
        cost, node, path = heapq.heappop(queue)

        if node in visited:
            continue

        visited.add(node)
        path = path + [node]

        if node == goal:
            return path, cost

        r, c = node

        for dr, dc in [
            (-1, 0),
            (1, 0),
            (0, -1),
            (0, 1),
        ]:
            nr, nc = r + dr, c + dc

            if 0 <= nr < rows and 0 <= nc < cols:
                if (nr, nc) not in visited:
                    next_cost = cost + float(cost_surface[nr, nc])
                    heapq.heappush(queue, (next_cost, (nr, nc), path))

    return [], np.inf
