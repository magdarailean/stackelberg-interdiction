from functools import lru_cache
from random import Random
from statistics import mean, quantiles

from .defender import Plan
from .follower import Edge
from .scenarios import Day


class Sample:

    def __init__(self, days: tuple[Day, ...], factor: float = 0.3, weights: tuple[float, ...] | None = None):
        if not days or not 0 < factor <= 1:
            raise ValueError("Expected days and a factor in (0,1]")
        self.days = days
        self.factor = factor
        self.weights = weights or (1/len(days),)*len(days)
        if len(self.weights) != len(days) or min(self.weights) < 0 or abs(sum(self.weights)-1) > 1e-8:
            raise ValueError("Invalid probability weights")

        @lru_cache(maxsize=65536)
        def hourly(i: int, t: int, edges: frozenset[Edge]) -> float:
            return days[i][t].delivered(edges, factor)

        self.hourly = hourly

    def flows(self, plan: Plan) -> list[float]:
        return [sum(self.hourly(i, t, frozenset(e for h, e in plan if h == t))
                    for t in range(len(day))) for i, day in enumerate(self.days)]

    def mean(self, plan: Plan) -> float:
        return sum(w*x for w,x in zip(self.weights, self.flows(plan)))


def interval(values: list[float], seed: int) -> tuple[float, float, float]:
    rng = Random(seed)
    means = [sum(rng.choices(values, k=len(values)))/len(values) for _ in range(2000)]
    cuts = quantiles(means, n=1000, method="inclusive")
    return mean(values), cuts[24], cuts[974]
