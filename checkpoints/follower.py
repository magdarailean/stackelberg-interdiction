"""Adaptive aggregate flow in one slot."""
from collections.abc import Iterable
from math import isfinite

import networkx as nx

from .network import Edge

def delivered_flow(G: nx.DiGraph, supply: float, demand: float,
                   checkpoints: Iterable[Edge], factor: float = 0.3) -> float:
    """Return maximum S-to-T delivery capped by available supply and demand."""
    if not 0 <= factor <= 1 or any(not isfinite(x) or x < 0 for x in (supply, demand)):
        raise ValueError("Invalid capacity factor, supply or demand")
    graph = G.copy()
    for edge in set(checkpoints):
        graph.edges[edge]["capacity"] *= factor
    return min(supply, demand, nx.maximum_flow_value(graph, "S", "T"))
