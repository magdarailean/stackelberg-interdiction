from math import isclose, isfinite
from ortools.linear_solver import pywraplp


def upper_tail(values: list[float], weights: list[float], alpha: float) -> float:
    if not values or len(weights) != len(values) or not 0 <= alpha < 1:
        raise ValueError("Invalid tail inputs")
    if any(not isfinite(w) or w < 0 for w in weights) or not isclose(sum(weights), 1):
        raise ValueError("Expected probability weights summing to one")
    remaining = 1 - alpha
    total = 0.
    for value, weight in sorted(zip(values, weights), reverse=True):
        mass = min(remaining, weight)
        total += mass * value
        remaining -= mass
        if remaining <= 0:
            break
    return total / (1-alpha)


def risk_mixture(regimes: list[list[list[float]]], alpha: float, contamination: float | None = None) -> dict:
    if not regimes or not 0 <= alpha < 1 or contamination is not None and not 0 <= contamination <= 1:
        raise ValueError("Invalid risk parameters")
    solver = pywraplp.Solver.CreateSolver("GLOP")
    mass = [solver.NumVar(0, 1, "") for _ in regimes[0]]
    solver.Add(solver.Sum(mass) == 1)
    bound = solver.NumVar(0, solver.infinity(), "")
    for regime in regimes:
        losses = [solver.Sum(x*v for x,v in zip(mass, day, strict=True)) for day in zip(*regime, strict=True)]
        if contamination is not None:
            average = solver.Sum(losses)/len(losses)
            for loss in losses:
                solver.Add(bound >= (1-contamination)*average + contamination*loss)
        else:
            threshold = solver.NumVar(0, solver.infinity(), "")
            excess = [solver.NumVar(0,solver.infinity(),"") for _ in losses]
            for slack,loss in zip(excess,losses):
                solver.Add(slack >= loss-threshold)
            solver.Add(bound >= threshold+solver.Sum(excess)/(len(losses)*(1-alpha)))
    solver.Minimize(bound)
    if solver.Solve() != solver.OPTIMAL:
        raise RuntimeError("Risk optimization failed")
    return {i:x.solution_value() for i,x in enumerate(mass) if x.solution_value()>0}
