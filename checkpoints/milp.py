"""Shared time-indexed min-cut model."""
from dataclasses import dataclass
from math import isfinite
from time import perf_counter

from ortools.linear_solver import pywraplp

from .defender import Plan, Rules
from .evaluate import Sample


@dataclass
class Result:
    """Feasible policy, dual bound and model diagnostics."""
    plan: Plan
    status: str
    lower: float | None
    solve_seconds: float
    build_seconds: float
    variables: int
    constraints: int


def optimize(sample: Sample, rules: Rules, seconds: float, incumbent: Plan = frozenset()) -> Result:
    """Minimize mean daily delivery using one cut per hour and day."""
    if not isfinite(seconds) or seconds <= 0 or not rules.feasible(incumbent):
        raise ValueError("Invalid time limit or incumbent")
    start = perf_counter()
    s = pywraplp.Solver.CreateSolver("SCIP")
    if s is None:
        raise RuntimeError("SCIP unavailable")
    s.SetNumThreads(1)
    x = {(t, e): s.BoolVar("") for t, sites in enumerate(rules.allowed) for e in sites}
    s.Add(s.Sum(x.values()) <= rules.budget)
    for t, sites in enumerate(rules.allowed):
        s.Add(s.Sum(x[t, e] for e in sites) <= rules.crews)
        for e in sites:
            onset = x[t, e] - x.get((t-1, e), 0)
            for i in range(1, min(rules.shift, len(rules.allowed) + 1)):
                s.Add(onset <= x.get((t+i, e), 0))
            if rules.same_origin and t:
                for prev in rules.allowed[t-1]:
                    if prev[0] != e[0]:
                        s.Add(x[t, e] + x[t-1, prev] <= 1)
    objective = s.Objective()
    objective.SetMinimization()
    for day in sample.days:
        if len(day) != len(rules.allowed):
            raise ValueError("Day length differs from planning horizon")
        for t, slot in enumerate(day):
            side = {v: s.BoolVar("") for v in slot.graph}
            s.Add(side[slot.source] == 1)
            s.Add(side[slot.sink] == 0)
            for u, v, cap in slot.graph.edges.data("capacity"):
                if cap == 0:
                    continue
                crossing = side[u] - side[v]
                d = s.NumVar(0, 1, "")
                s.Add(d >= crossing)
                weight = cap / len(sample.days)
                action = x.get((t, (u, v)))
                if action is not None and sample.factor < 1:
                    z = s.NumVar(0, 1, "")
                    s.Add(z >= d - action)
                    objective.SetCoefficient(z, weight * (1 - sample.factor))
                    weight *= sample.factor
                objective.SetCoefficient(d, weight)

    built = perf_counter()
    s.SetHint(list(x.values()), [int(a in incumbent) for a in x])
    s.SetTimeLimit(max(1, int(seconds * 1000)))
    status = s.Solve()
    elapsed = perf_counter() - built
    plan, bound, label = incumbent, None, "fallback"
    if status in (s.OPTIMAL, s.FEASIBLE):
        candidate = frozenset(a for a, var in x.items() if var.solution_value() > 0.5)
        if not rules.feasible(candidate):
            raise RuntimeError("Solver returned an infeasible schedule")
        plan = min((candidate, incumbent), key=sample.mean)
        label = "optimal" if status == s.OPTIMAL else "feasible"
        bound = objective.BestBound()
    elif status != s.NOT_SOLVED:
        raise RuntimeError(f"Unexpected SCIP status {status}")
    return Result(plan, label, bound, elapsed, built-start, s.NumVariables(), s.NumConstraints())
