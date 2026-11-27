from collections.abc import Callable
from dataclasses import dataclass
from random import Random
from functools import cache
from itertools import combinations

import networkx as nx

from .follower import Edge

Action = tuple[int, Edge]
Plan = frozenset[Action]


@dataclass(frozen=True)
class Rules:
    allowed: tuple[tuple[Edge, ...], ...]
    budget: int = 4
    crews: int = 1
    shift: int = 1
    same_origin: bool = False
    pools: tuple[tuple[frozenset[Edge], int], ...] = ()
    delay_per_slot: tuple[float, ...] = ()
    delay_cap: float | None = None

    def __post_init__(self) -> None:
        if not self.allowed or min(self.budget, self.crews) < 0 or self.shift < 1:
            raise ValueError("Invalid schedule limits")
        if self.same_origin and self.crews != 1:
            raise ValueError("Toy travel rule requires one crew")

    def feasible(self, plan: Plan) -> bool:
        if len(plan) > self.budget:
            return False
        if self.delay_cap is not None:
            if any(not 0 <= t < len(self.delay_per_slot) for t,_ in plan):
                return False
            if sum(self.delay_per_slot[t] for t,_ in plan) > self.delay_cap:
                return False
        for sites, limit in self.pools:
            for hour in range(len(self.allowed)):
                if sum(t == hour and e in sites for t, e in plan) > limit:
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
        return [frozenset((t+i, e) for i in range(self.shift))
                for t, sites in enumerate(self.allowed) for e in sites
                if t + self.shift <= len(self.allowed)
                and all(e in self.allowed[t+i] for i in range(self.shift))]


def greedy(rules: Rules, score: Callable[[Plan], float], lookahead: int = 1) -> Plan:
    plan: Plan = frozenset()
    blocks = [b for b in rules.blocks() if rules.feasible(b)]
    score = cache(score)
    while True:
        value = score(plan)
        remaining = [b for b in blocks if b - plan and rules.feasible(plan | b)]
        options = dict.fromkeys(p for size in range(1, min(lookahead,rules.budget-len(plan))+1)
                                for batch in combinations(remaining,size)
                                if rules.feasible(p := plan.union(*batch)))
        if not options:
            return plan
        best = min(options,key=lambda p:(score(p),-len(p)))
        if lookahead == 1 and score(best) >= value - 1e-10:
            return plan
        plan = best


def fill(rules: Rules, blocks: list[Plan]) -> Plan:
    plan: Plan = frozenset()
    for block in blocks:
        if rules.feasible(plan | block):
            plan |= block
    return plan


def random_schedule(rules: Rules, seed: int) -> Plan:
    blocks = rules.blocks()
    Random(seed).shuffle(blocks)
    return fill(rules, blocks)


def centrality(rules: Rules, graph: nx.DiGraph, seed: int) -> Plan:
    ranks = nx.edge_betweenness_centrality(graph, k=min(32, len(graph)), seed=seed)
    return fill(rules, sorted(rules.blocks(), key=lambda b: -ranks.get(next(iter(b))[1], 0)))
