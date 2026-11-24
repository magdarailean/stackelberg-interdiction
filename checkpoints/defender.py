"""Feasible two-hour policies for the toy network."""
from collections.abc import Callable
from itertools import product
from random import Random

from .network import Edge, SITES

Action = tuple[int, Edge]
Plan = frozenset[Action]

def feasible_plans(budget: int = 2) -> tuple[Plan, ...]:
    """One crew may idle or staff one authorized site per hour."""
    if budget < 0:
        raise ValueError("Budget must be nonnegative")
    plans = []
    for first, second in product((None, *SITES[:3]), (None, *SITES[1:])):
        if first and second and first[0] != second[0]:
            continue
        plan = frozenset((t, e) for t, e in enumerate((first, second)) if e)
        if len(plan) <= budget:
            plans.append(plan)
    return tuple(plans)

def random_feasible(plans: tuple[Plan, ...], seed: int) -> Plan:
    """Draw uniformly among feasible schedules with maximum feasible hours."""
    hours = max(map(len, plans))
    return Random(seed).choice([p for p in plans if len(p) == hours])

def greedy(plans: tuple[Plan, ...], score: Callable[[Plan], float]) -> Plan:
    """Add the feasible action with greatest positive training flow reduction."""
    current: Plan = frozenset()
    value = score(current)
    while True:
        additions = [p for p in plans if current < p and len(p) == len(current) + 1]
        if not additions:
            return current
        best = min(additions, key=score)
        updated = score(best)
        if updated >= value:
            return current
        current, value = best, updated
