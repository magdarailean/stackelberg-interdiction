"""Paired evaluation on held-out synthetic days."""
from random import Random
from statistics import mean, quantiles

import networkx as nx

from .defender import Plan
from .follower import delivered_flow
from .scenarios import Day

def daily_flow(graph: nx.DiGraph, day: Day, plan: Plan) -> float:
    """Sum the two independent hourly follower responses."""
    total = 0.0
    for t, slot in enumerate(day):
        available = graph.copy()
        for edge in slot.closed:
            available.edges[edge]["capacity"] = 0
        total += delivered_flow(available, slot.supply, slot.demand,
                                (e for hour, e in plan if hour == t))
    return total

def interval(values: list[float], seed: int) -> tuple[float, float, float]:
    """Approximate 95% percentile bootstrap interval over independent days."""
    rng = Random(seed)
    means = [mean(rng.choices(values, k=len(values))) for _ in range(2000)]
    cuts = quantiles(means, n=1000, method="inclusive")
    return mean(values), cuts[24], cuts[974]
