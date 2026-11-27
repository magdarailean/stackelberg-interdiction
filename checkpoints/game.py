from itertools import combinations
from math import comb
from random import Random

from ortools.linear_solver import pywraplp

from .defender import Plan, Rules, random_schedule


def schedules(rules: Rules, seeds: int, limit: int, include: list[Plan]) -> tuple[list[Plan], bool]:
    actions = [(t, edge) for t, group in enumerate(rules.allowed) for edge in group
               if all(cap > 0 or edge not in sites for sites, cap in rules.pools)]
    sizes = range(min(rules.budget, len(actions)) + 1)
    complete = sum(comb(len(actions), k) for k in sizes) <= limit
    if complete:
        pool = (frozenset(row) for k in sizes for row in combinations(actions, k))
    else:
        rng = Random(seeds)
        pool = (random_schedule(rules, rng.getrandbits(64)) for _ in range(limit))
    return list(dict.fromkeys([*include, *(p for p in pool if rules.feasible(p))])), complete


def restricted_game(matrix: list[list[float]], rows: list[int], cols: list[int]) -> tuple[list[float], list[float]]:
    solver = pywraplp.Solver.CreateSolver("GLOP")
    p = [solver.NumVar(0, 1, "") for _ in rows]
    value = solver.NumVar(-solver.infinity(), solver.infinity(), "")
    solver.Add(solver.Sum(p) == 1)
    constraints = [solver.Add(solver.Sum(x * matrix[i][j] for x, i in zip(p, rows)) <= value)
                   for j in cols]
    solver.Minimize(value)
    if solver.Solve() != solver.OPTIMAL:
        raise RuntimeError("Restricted matrix game did not solve")
    return [x.solution_value() for x in p], [-c.dual_value() for c in constraints]


def solve_game(matrix: list[list[float]], tolerance: float = 1e-8) -> dict:
    rows, cols = [0], [0]
    rounds = 0
    while True:
        rounds += 1
        p, q = restricted_game(matrix, rows, cols)
        costs = [sum(prob * row[j] for prob, j in zip(q, cols)) for row in matrix]
        responses = [sum(prob * matrix[i][j] for prob, i in zip(p, rows))
                     for j in range(len(matrix[0]))]
        lower, upper = min(costs), max(responses)
        if upper - lower <= tolerance:
            return dict(mass=dict(zip(rows, p)), lower=lower, upper=upper, iterations=rounds)
        row, col = costs.index(lower), responses.index(upper)
        if row in rows and col in cols:
            raise RuntimeError("Best responses stalled outside tolerance")
        if row not in rows:
            rows.append(row)
        if col not in cols:
            cols.append(col)


def generate_responses(train, rules, plans, matrix, seconds, iterations, tolerance=1e-8):
    from .evaluate import Sample
    from .milp import optimize
    from time import perf_counter

    start = perf_counter()
    lower = 0.
    columns = list(range(len(train)))
    days = tuple(day for sample in train for day in sample.days)
    for step in range(1, iterations+1):
        rows = list(range(len(plans)))
        p, q = restricted_game(matrix, rows, columns)
        upper = max(sum(p[i]*matrix[i][j] for i in rows) for j in columns)
        remaining = seconds - (perf_counter()-start)
        stop = "time_limit"
        if remaining > 0:
            weights = tuple(max(0., prob)*w for prob,s in zip(q,train) for w in s.weights)
            sample = Sample(days, train[0].factor, weights)
            result = optimize(sample, rules, remaining)
            if result.lower is not None:
                lower = max(lower, result.lower)
            stop = "no_new_column"
            if upper-lower <= tolerance:
                stop = "gap_tolerance"
            elif result.plan not in plans and step < iterations:
                plans.append(result.plan)
                matrix.append([s.mean(result.plan) for s in train])
                continue
            elif step == iterations:
                stop = "iteration_limit"
        return dict(mass=dict(zip(rows,p)), upper=upper, lower=min(lower,upper),
                    iterations=step, stopping=stop)
