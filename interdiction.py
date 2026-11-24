"""Fixed-deployment interdiction on synthetic directed networks."""

from dataclasses import dataclass
from random import Random
from time import perf_counter

import networkx as nx


@dataclass(frozen=True)
class Site:
    edge: tuple[int, int]
    hours: int
    reduction: int


@dataclass(frozen=True)
class Scenario:
    graph: nx.DiGraph
    source: int
    sink: int
    weight: float = 1.0

    def delivered(self, sites=()):
        graph = self.graph.copy() if sites else self.graph
        for site in sites:
            if graph.has_edge(*site.edge):
                arc = graph.edges[site.edge]
                arc["capacity"] = max(0, arc["capacity"] - site.reduction)
        return nx.maximum_flow_value(graph, self.source, self.sink)


def expected_flow(scenarios, schedule=()):
    return sum(s.weight * s.delivered(schedule) for s in scenarios) / sum(
        s.weight for s in scenarios
    )


def greedy(scenarios, sites, budget):
    schedule = ()
    while affordable := [s for s in sites if s not in schedule and s.hours <= budget]:
        previous = expected_flow(scenarios, schedule)
        gains = {
            s: (previous - expected_flow(scenarios, (*schedule, s))) / s.hours
            for s in affordable
        }
        site = max(affordable, key=gains.__getitem__)
        if gains[site] <= 0:
            break
        schedule += (site,)
        budget -= site.hours
    return schedule


def random_schedule(sites, budget, seed):
    order = list(sites)
    Random(seed).shuffle(order)
    schedule = []
    for site in order:
        if site.hours <= budget:
            schedule.append(site)
            budget -= site.hours
    return tuple(schedule)


@dataclass(frozen=True)
class SolveResult:
    schedule: tuple[Site, ...]
    status: str
    bound: float | None
    seconds: float


def optimize(scenarios, sites, budget, seconds, incumbent=()):
    from ortools.linear_solver import pywraplp

    started = perf_counter()
    solver = pywraplp.Solver.CreateSolver("SCIP")
    if solver is None:
        raise RuntimeError("OR-Tools must include the SCIP solver.")
    solver.SetNumThreads(1)
    solver.SetTimeLimit(max(1, int(seconds * 1000)))
    active = {s.edge: solver.BoolVar("") for s in sites}
    solver.Add(solver.Sum(s.hours * active[s.edge] for s in sites) <= budget)
    reductions = {s.edge: s.reduction for s in sites}
    objective = solver.Objective()
    objective.SetMinimization()
    total_weight = sum(s.weight for s in scenarios)

    # One independent min cut per scenario and one shared deployment. For an
    # arc from the source side to the sink side, pay its residual capacity.
    for scenario in scenarios:
        weight = scenario.weight / total_weight
        side = {node: solver.BoolVar("") for node in scenario.graph}
        solver.Add(side[scenario.source] == 1)
        solver.Add(side[scenario.sink] == 0)
        for u, v, capacity in scenario.graph.edges.data("capacity"):
            if capacity == 0:
                continue
            crossing = side[u] - side[v]
            reduction = min(capacity, reductions.get((u, v), 0))
            residual = capacity - reduction
            if residual:
                cut = solver.NumVar(0, 1, "")
                solver.Add(cut >= crossing)
                objective.SetCoefficient(cut, weight * residual)
            if reduction:
                uncovered = solver.NumVar(0, 1, "")
                solver.Add(uncovered >= crossing - active[u, v])
                objective.SetCoefficient(uncovered, weight * reduction)

    solver.SetHint(list(active.values()), [float(s in incumbent) for s in sites])
    status = solver.Solve()
    elapsed = perf_counter() - started
    if status == solver.NOT_SOLVED:
        return SolveResult(incumbent, "fallback", None, elapsed)
    if status not in (solver.OPTIMAL, solver.FEASIBLE):
        raise RuntimeError(f"Unexpected SCIP status {status} for a feasible model")
    schedule = tuple(s for s in sites if active[s.edge].solution_value() > 0.5)
    # A feasible deployment can be better than the cut the solver paired with
    # it. Compare policies with independently recomputed follower responses.
    if expected_flow(scenarios, incumbent) < expected_flow(scenarios, schedule):
        schedule = incumbent
    return SolveResult(
        schedule, "optimal" if status == solver.OPTIMAL else "feasible",
        objective.BestBound(), elapsed,
    )


def synthetic_network(rows, columns):
    """Return fixed candidate sites and a seeded factory for fictional scenarios."""
    barrier = columns // 2 - 1
    source = rows * columns
    sink = source + 1

    def node(row, column):
        return row * columns + column

    candidate_rows = sorted({i * rows // min(rows, 8) for i in range(min(rows, 8))})
    sites = tuple(
        Site((node(row, barrier), node(row, barrier + 1)), 1 + index % 3, 6)
        for index, row in enumerate(candidate_rows)
    )

    def make(seed, shift=False):
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
