"""Deterministic editor positions; geometry never changes workflow behavior."""

from collections import deque
from copy import deepcopy
from math import ceil, sqrt


def arrange(workflow: dict, positions: dict | None = None) -> dict:
    result = deepcopy(workflow)
    nodes = result["nodes"]
    if positions is None:
        start = result["initial_node"]
        seen, order, queue = set(), [], deque([start])
        while queue:
            key = queue.popleft()
            if key in seen or key not in nodes:
                continue
            seen.add(key)
            order.append(key)
            queue.extend(sorted(t.get("target_node") for t in nodes[key].get("transitions", [])
                                if isinstance(t.get("target_node"), str)))
        order.extend(sorted(set(nodes) - seen))
        columns = min(5, max(1, ceil(sqrt(len(order)))))
        positions = {key: {"x": (i % columns) * 560, "y": (i // columns) * 440}
                     for i, key in enumerate(order)}
    if set(positions) != set(nodes):
        raise ValueError("Positions must cover every node exactly once")
    points = [(value["x"], value["y"]) for value in positions.values()]
    if len(set(points)) != len(points):
        raise ValueError("Node positions overlap")
    for key, node in nodes.items():
        node["position"] = {"x": positions[key]["x"], "y": positions[key]["y"]}
    return result
