"""Seeded toy days with independent hourly conditions."""
from random import Random

from .follower import Scenario
from .network import SITES, toy_graph

Day = tuple[Scenario, ...]


def generate(count: int, seed: int, closure_probability: float, slots: int = 4) -> tuple[Day, ...]:
    """Draw toy supply, demand and independent interior closures."""
    if min(count, slots) < 1 or not 0 <= closure_probability <= 1:
        raise ValueError("Invalid toy scenario parameters")
    rng = Random(seed)

    def hour() -> Scenario:
        graph = toy_graph()
        graph.add_edge("supply", "S", capacity=rng.randint(12, 20))
        graph.add_edge("T", "demand", capacity=rng.randint(13, 21))
        graph.remove_edges_from(e for e in SITES if rng.random() < closure_probability)
        return Scenario(graph, "supply", "demand")

    return tuple(tuple(hour() for _ in range(slots)) for _ in range(count))
