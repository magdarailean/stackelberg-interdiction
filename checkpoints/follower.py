from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from math import isfinite

import networkx as nx

Edge = tuple[Hashable, Hashable]


@dataclass(frozen=True)
class Scenario:
    graph: nx.DiGraph
    source: Hashable
    sink: Hashable

    def delivered(self, edges: Iterable[Edge] = (), factor: float = 0.3) -> float:
        if not 0 < factor <= 1:
            raise ValueError("factor must be in (0, 1]")
        active = set(edges)
        graph = self.graph.copy() if active else self.graph
        for edge in active:
            if graph.has_edge(*edge):
                graph.edges[edge]["capacity"] *= factor
        return nx.maximum_flow_value(graph, self.source, self.sink,
                                     flow_func=nx.algorithms.flow.shortest_augmenting_path)


def delivered_flow(G: nx.DiGraph, supply: float, demand: float,
                   checkpoints: Iterable[Edge], factor: float = 0.3) -> float:
    if any(not isfinite(x) or x < 0 for x in (supply, demand)):
        raise ValueError("Invalid supply or demand")
    return min(supply, demand, Scenario(G, "S", "T").delivered(checkpoints, factor))
