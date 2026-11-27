"""Interception-first schedule optimization with separated max-flow cut rows."""

from collections import Counter
from dataclasses import dataclass
from math import isfinite
from time import perf_counter

import networkx as nx
from ortools.linear_solver import pywraplp

from .accounting import account
from .defender import Plan, Rules
from .evaluate import Sample


@dataclass
class InterceptionResult:
    plan: Plan
    status: str
    value: float
    lower_bound: float
    upper_bound: float
    absolute_gap: float
    total_seconds: float
    solve_seconds: float
    build_seconds: float
    iterations: int
    cuts: int


def accounting_totals(sample: Sample, plan: Plan, cfg: dict) -> dict[str, float]:
    """Return probability-weighted ledger totals; foregone flow is not called interception."""
    totals = Counter()
    for day_index, (day, probability) in enumerate(zip(sample.days, sample.weights)):
        for t, scenario in enumerate(day):
            active = frozenset(edge for hour, edge in plan if hour == t)
            supply = scenario.graph.out_degree(scenario.source, weight="capacity")
            demand = scenario.graph.in_degree(scenario.sink, weight="capacity")
            outcome = account(supply, demand, sample.hourly(day_index, t, active), len(active), cfg, t)
            totals.update({key: probability * value for key, value in outcome.items()})
    return dict(totals)


def expected_interception(sample: Sample, plan: Plan, cfg: dict) -> float:
    return accounting_totals(sample, plan, cfg).get("intercepted", 0.0)


def _schedule_model(solver, rules: Rules):
    x = {(t, edge): solver.BoolVar("")
         for t, sites in enumerate(rules.allowed) for edge in sites}
    solver.Add(solver.Sum(x.values()) <= rules.budget)
    if rules.delay_cap is not None:
        solver.Add(solver.Sum(rules.delay_per_slot[t] * var for (t, _), var in x.items())
                   <= rules.delay_cap)
    for t, sites in enumerate(rules.allowed):
        solver.Add(solver.Sum(x[t, edge] for edge in sites) <= rules.crews)
        for group, limit in rules.pools:
            solver.Add(solver.Sum(x[t, edge] for edge in sites if edge in group) <= limit)
        for edge in sites:
            onset = x[t, edge] - x.get((t - 1, edge), 0)
            for offset in range(1, min(rules.shift, len(rules.allowed) + 1)):
                solver.Add(onset <= x.get((t + offset, edge), 0))
            if rules.same_origin and t:
                for previous in rules.allowed[t - 1]:
                    if previous[0] != edge[0]:
                        solver.Add(x[t, edge] + x[t - 1, previous] <= 1)
    return x


def _flow_cut(scenario, active: Plan, factor: float):
    graph = scenario.graph.copy()
    for u, v in active:
        if not graph.has_edge(u, v):
            continue
        if graph.is_multigraph():
            for attrs in graph[u][v].values():
                attrs["capacity"] *= factor
        else:
            graph[u][v]["capacity"] *= factor
    value, partition = nx.minimum_cut(graph, scenario.source, scenario.sink, capacity="capacity")
    return value, frozenset(partition[0])


def optimize_interception(
    sample: Sample,
    rules: Rules,
    cfg: dict,
    seconds: float,
    incumbent: Plan = frozenset(),
    target_hours: int | None = None,
    max_iterations: int = 100,
) -> InterceptionResult:
    """Maximize expected modeled interceptions, using NetworkX cuts as lazy rows.

    The follower's adaptive max-flow equals the minimum directed cut value. For each
    sampled day/hour, variable q is bounded by every discovered cut and by the
    inspection processing capacity (rate times active checkpoint-hours). Maximizing
    detection_probability * E[q] therefore exactly matches the ledger's interception
    rule. Violated cuts from each incumbent are added until SCIP proves the relaxed
    MILP optimum feasible or the time limit is reached. For maximization, SCIP's
    best bound on the cut relaxation is a valid global upper bound; an evaluated
    schedule is the lower bound. Deferral is accounted separately and is never
    credited as interception.
    """
    if not isfinite(seconds) or seconds <= 0 or max_iterations < 1:
        raise ValueError("Invalid time limit or iteration limit")
    if target_hours is not None and not 0 <= target_hours <= rules.budget:
        raise ValueError("Target checkpoint-hours must be within the schedule budget")
    if not rules.feasible(incumbent) or (target_hours is not None and len(incumbent) != target_hours):
        raise ValueError("Incumbent does not satisfy schedule constraints")
    rate = float(cfg["processing_per_crew_hour"])
    detection = float(cfg["detection_probability"])
    if rate < 0 or not 0 <= detection <= 1:
        raise ValueError("Invalid inspection capacity or detection probability")

    started = perf_counter()
    solver = pywraplp.Solver.CreateSolver("SCIP")
    if solver is None:
        raise RuntimeError("SCIP unavailable")
    solver.SetNumThreads(1)
    x = _schedule_model(solver, rules)
    if target_hours is not None:
        solver.Add(solver.Sum(x.values()) == target_hours)

    q = {}
    objective = solver.Objective()
    objective.SetMaximization()
    theoretical_upper = 0.0
    for d, (day, probability) in enumerate(zip(sample.days, sample.weights)):
        for t, scenario in enumerate(day):
            upper = min(
                scenario.graph.out_degree(scenario.source, weight="capacity"),
                scenario.graph.in_degree(scenario.sink, weight="capacity"),
                rate * rules.crews,
            )
            q[d, t] = solver.NumVar(0.0, max(0.0, upper), "")
            solver.Add(q[d, t] <= rate * solver.Sum(x[t, edge] for edge in rules.allowed[t]))
            objective.SetCoefficient(q[d, t], detection * probability)
            no_checkpoint_flow = scenario.delivered((), sample.factor)
            theoretical_upper += probability * detection * min(no_checkpoint_flow, rate * rules.crews)
    built = perf_counter()

    best_plan = incumbent
    best_value = expected_interception(sample, incumbent, cfg)
    last_upper = theoretical_upper
    seen_cuts: set[tuple[int, int, frozenset]] = set()
    cut_count = 0
    iterations = 0
    status_label = "time_limit"

    for iterations in range(1, max_iterations + 1):
        remaining = seconds - (perf_counter() - started)
        if remaining <= 0:
            break
        solver.SetTimeLimit(max(1, int(remaining * 1000)))
        status = solver.Solve()
        if status not in (solver.OPTIMAL, solver.FEASIBLE):
            status_label = "time_limit" if status == solver.NOT_SOLVED else "fallback"
            break

        candidate = frozenset(action for action, var in x.items() if var.solution_value() > 0.5)
        if not rules.feasible(candidate) or (target_hours is not None and len(candidate) != target_hours):
            raise RuntimeError("Solver returned an infeasible schedule")
        value = expected_interception(sample, candidate, cfg)
        if value > best_value + 1e-9:
            best_plan, best_value = candidate, value
        solver_bound = objective.BestBound()
        last_upper = min(theoretical_upper, max(best_value, solver_bound))

        q_values = {key: variable.solution_value() for key, variable in q.items()}
        new_cuts = 0
        for d, day in enumerate(sample.days):
            for t, scenario in enumerate(day):
                active = frozenset(edge for hour, edge in candidate if hour == t)
                flow, source_side = _flow_cut(scenario, active, sample.factor)
                if q_values[d, t] <= flow + 1e-7:
                    continue
                key = (d, t, source_side)
                if key in seen_cuts:
                    continue
                seen_cuts.add(key)
                crossing_capacity = 0.0
                row = q[d, t]
                for u, v, capacity in scenario.graph.edges.data("capacity"):
                    if u in source_side and v not in source_side:
                        crossing_capacity += capacity
                        action = x.get((t, (u, v)))
                        if action is not None and sample.factor < 1:
                            row += (1 - sample.factor) * capacity * action
                solver.Add(row <= crossing_capacity)
                new_cuts += 1
                cut_count += 1

        if not new_cuts and status == solver.OPTIMAL:
            status_label = "optimal"
            last_upper = best_value
            break
        if status == solver.FEASIBLE:
            status_label = "feasible"
        elif new_cuts:
            status_label = "separating_cuts"
    else:
        status_label = "iteration_limit"

    gap = max(0.0, last_upper - best_value)
    return InterceptionResult(
        plan=best_plan,
        status=status_label,
        value=best_value,
        lower_bound=best_value,
        upper_bound=max(best_value, last_upper),
        absolute_gap=gap,
        total_seconds=perf_counter() - started,
        solve_seconds=max(0.0, perf_counter() - built),
        build_seconds=built - started,
        iterations=iterations,
        cuts=cut_count,
    )
