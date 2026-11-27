import networkx as nx

from collections.abc import Callable
from random import Random

from .follower import Edge, Scenario

SITES = (("A", "C"), ("A", "D"), ("B", "C"), ("B", "D"))

def toy_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_weighted_edges_from([
        ("S", "A", 10), ("S", "B", 8), ("A", "C", 7), ("A", "D", 4),
        ("B", "C", 4), ("B", "D", 7), ("C", "T", 8), ("D", "T", 9)
    ], weight="capacity")
    return graph


def synthetic_network(rows: int, columns: int) -> tuple[tuple[Edge, ...], Callable[[int, bool], Scenario]]:
    barrier = columns // 2 - 1
    source = rows * columns
    sink = source + 1

    def node(row: int, column: int) -> int:
        return row * columns + column

    candidate_rows = sorted({i * rows // min(rows, 8) for i in range(min(rows, 8))})
    sites = tuple(
        (node(row, barrier), node(row, barrier + 1))
        for row in candidate_rows
    )

    def make(seed: int, shift: bool = False) -> Scenario:
        rng = Random(seed)
        graph = nx.DiGraph()
        graph.add_nodes_from(range(sink + 1))
        for row in range(rows):
            supply = rng.randint(3, 9) if shift else rng.randint(4, 8)
            graph.add_edge(source, node(row, 0), capacity=supply)
            graph.add_edge(node(row, columns - 1), sink, capacity=rng.randint(5, 9))
            for column in range(columns):
                here = node(row, column)
                if column + 1 < columns:
                    capacity = rng.randint(12, 24)
                    if column == barrier:
                        capacity = rng.randint(3, 9) if row in candidate_rows else rng.randint(0, 2)
                        if rng.random() < 0.12:
                            capacity = 0
                    if capacity:
                        graph.add_edge(here, node(row, column + 1), capacity=capacity)
                if row + 1 < rows:
                    below = node(row + 1, column)
                    graph.add_edge(here, below, capacity=rng.randint(8, 16))
                    graph.add_edge(below, here, capacity=rng.randint(8, 16))
        if shift:
            for row in rng.sample(range(rows - 1), k=max(1, rows // 8)):
                graph.add_edge(node(row, barrier), node(row + 1, barrier + 1), capacity=rng.randint(2, 6))
        return Scenario(graph, source, sink)

    return sites, make
