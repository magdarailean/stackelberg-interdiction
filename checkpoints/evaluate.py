"""Paired policy evaluation on independent synthetic days."""
from functools import lru_cache
from random import Random
from statistics import mean, quantiles

from .defender import Plan
from .follower import Edge
from .scenarios import Day


class Sample:
    """Cache slot responses shared by different schedules on this split."""

    def __init__(self, days: tuple[Day, ...], factor: float = 0.3):
        if not days or not 0 < factor <= 1:
            raise ValueError("Expected days and a factor in (0,1]")
        self.days = days
        self.factor = factor

        @lru_cache(maxsize=65536)
        def hourly(i: int, t: int, edges: frozenset[Edge]) -> float:
            return days[i][t].delivered(edges, factor)

        self.hourly = hourly

    def flows(self, plan: Plan) -> list[float]:
        """Compute each day's total delivery."""
        return [sum(self.hourly(i, t, frozenset(e for h, e in plan if h == t))
                    for t in range(len(day))) for i, day in enumerate(self.days)]

    def mean(self, plan: Plan) -> float:
        """Return equally weighted mean daily delivery."""
        return mean(self.flows(plan))


def interval(values: list[float], seed: int) -> tuple[float, float, float]:
    """Approximate 95% percentile bootstrap interval over independent days."""
    rng = Random(seed)
    means = [mean(rng.choices(values, k=len(values))) for _ in range(2000)]
    cuts = quantiles(means, n=1000, method="inclusive")
    return mean(values), cuts[24], cuts[974]
