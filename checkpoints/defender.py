"""Shared schedule constraints and placement baselines."""
from collections.abc import Callable
from dataclasses import dataclass
from random import Random

import networkx as nx

from .follower import Edge

Action = tuple[int, Edge]
Plan = frozenset[Action]


@dataclass(frozen=True)
class Rules:
    """Hourly authorization, total hours, crew cap and minimum shift."""
    allowed: tuple[tuple[Edge, ...], ...]
    budget: int = 4
    crews: int = 1
    shift: int = 1
    same_origin: bool = False

    def __post_init__(self) -> None:
        if not self.allowed or min(self.budget, self.crews) < 0 or self.shift < 1:
            raise ValueError("Invalid schedule limits")
        if self.same_origin and self.crews != 1:
            raise ValueError("Toy travel rule requires one crew")

    def feasible(self, plan: Plan) -> bool:
        """Check every active run including both horizon boundaries."""
        if len(plan) > self.budget:
            return False
        for t, e in plan:
            if not 0 <= t < len(self.allowed) or e not in self.allowed[t]:
                return False
            if sum(h == t for h, _ in plan) > self.crews:
                return False
            if (t-1, e) not in plan and any((t+i, e) not in plan for i in range(self.shift)):
                return False
            if self.same_origin and any(h == t-1 and f[0] != e[0] for h, f in plan):
                return False
        return True

    def blocks(self) -> list[Plan]:
        """Minimum shifts can overlap an existing run to extend it."""
        return [frozenset((t+i, e) for i in range(self.shift))
                for t, sites in enumerate(self.allowed) for e in sites
                if t + self.shift <= len(self.allowed)
                and all(e in self.allowed[t+i] for i in range(self.shift))]


def greedy(rules: Rules, score: Callable[[Plan], float]) -> Plan:
    """Recompute marginal daily delivery reduction per added hour."""
    plan: Plan = frozenset()
    blocks = rules.blocks()
    while True:
        value = score(plan)
        options = [plan | b for b in blocks if b - plan and rules.feasible(plan | b)]
        if not options:
            return plan
        best = max(options, key=lambda p: (value - score(p)) / len(p - plan))
        if score(best) >= value - 1e-10:
            return plan
        plan = best


def fill(rules: Rules, blocks: list[Plan]) -> Plan:
    """Accept feasible shifts in priority order."""
    plan: Plan = frozenset()
    for block in blocks:
        if rules.feasible(plan | block):
            plan |= block
    return plan


def random_schedule(rules: Rules, seed: int) -> Plan:
    """Shuffle candidate shifts with a local generator."""
    blocks = rules.blocks()
    Random(seed).shuffle(blocks)
    return fill(rules, blocks)


def centrality(rules: Rules, graph: nx.DiGraph, seed: int) -> Plan:
    """Rank sites by static unweighted directed edge betweenness."""
    ranks = nx.edge_betweenness_centrality(graph, k=min(32, len(graph)), seed=seed)
    return fill(rules, sorted(rules.blocks(), key=lambda b: -ranks.get(next(iter(b))[1], 0)))
