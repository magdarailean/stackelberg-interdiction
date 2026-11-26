"""DOBSS for a finite Bayesian Stackelberg game with general-sum payoffs.

Let D be leader schedules, T follower types, and A_t the actions available to
type t. Priors are pi_t; L[t][a][d] and F[t][a][d] are the leader and follower
payoffs. The leader commits to x in the simplex. Each type observes x and selects
a pure best response q[t,a]. DOBSS uses strong Stackelberg tie-breaking: among
follower best responses, it selects the one maximizing leader payoff.

The MILP has x_d >= 0, sum_d x_d = 1, binary q[t,a], sum_a q[t,a] = 1,
and v_t equal to the chosen best-response payoff. For every t,a:

    sum_d F[t,a,d] x_d <= v_t
    v_t - sum_d F[t,a,d] x_d <= M_t (1 - q[t,a])

Thus a selected action is a best response. The product z[t,a,d]=q[t,a]x_d is
linearized by z<=x, z<=q, z>=x+q-1. The objective is
sum_t pi_t sum_a,d L[t,a,d] z[t,a,d]. M_t is the range of follower payoffs,
which is valid because each type's best-response value lies in that range.

This is the compact DOBSS MILP (Paruchuri et al., AAMAS 2008), not a zero-sum
Stackelberg LP. `multiple_lp` independently enumerates one pure follower action
per type and solves the corresponding leader LPs, which is the Harsanyi/Conitzer-
Sandholm reference method for these finite games.
"""

from itertools import product
from math import isfinite
from time import perf_counter

from ortools.linear_solver import pywraplp


def _validate(priors, leader, follower):
    if not priors or len(leader) != len(priors) or len(follower) != len(priors):
        raise ValueError("Expected matching nonempty type payoffs and priors")
    if min(priors) < 0 or abs(sum(priors) - 1.0) > 1e-8:
        raise ValueError("Follower-type priors must be a probability distribution")
    schedules = None
    actions = []
    for t, (l_actions, f_actions) in enumerate(zip(leader, follower)):
        if not l_actions or len(l_actions) != len(f_actions):
            raise ValueError("Each follower type needs matching nonempty action sets")
        if schedules is None:
            schedules = len(l_actions[0])
        for row in (*l_actions, *f_actions):
            if len(row) != schedules or any(not isfinite(float(v)) for v in row):
                raise ValueError("Payoff matrices must be finite and share a schedule count")
        actions.append(len(l_actions))
    return schedules, actions


def solve_dobss(priors, leader, follower, seconds: float | None = None) -> dict:
    """Solve the finite Bayesian general-sum Stackelberg game using SCIP DOBSS."""
    schedules, action_counts = _validate(priors, leader, follower)
    if seconds is not None and (not isfinite(seconds) or seconds <= 0):
        raise ValueError("Time limit must be positive")
    started = perf_counter()
    solver = pywraplp.Solver.CreateSolver("SCIP")
    if solver is None:
        raise RuntimeError("SCIP unavailable")
    solver.SetNumThreads(1)
    x = [solver.NumVar(0.0, 1.0, "") for _ in range(schedules)]
    solver.Add(solver.Sum(x) == 1.0)

    q, value, z = {}, {}, {}
    objective = solver.Objective()
    objective.SetMaximization()
    for t, count in enumerate(action_counts):
        q[t] = [solver.BoolVar("") for _ in range(count)]
        solver.Add(solver.Sum(q[t]) == 1.0)
        all_payoffs = [float(v) for row in follower[t] for v in row]
        lower, upper = min(all_payoffs), max(all_payoffs)
        value[t] = solver.NumVar(lower, upper, "")
        big_m = upper - lower
        for a in range(count):
            expected_follower = solver.Sum(float(follower[t][a][d]) * x[d]
                                           for d in range(schedules))
            solver.Add(expected_follower <= value[t])
            solver.Add(value[t] - expected_follower <= big_m * (1.0 - q[t][a]))
            for d in range(schedules):
                z[t, a, d] = solver.NumVar(0.0, 1.0, "")
                solver.Add(z[t, a, d] <= x[d])
                solver.Add(z[t, a, d] <= q[t][a])
                solver.Add(z[t, a, d] >= x[d] + q[t][a] - 1.0)
                objective.SetCoefficient(z[t, a, d],
                                         float(priors[t]) * float(leader[t][a][d]))

    if seconds is not None:
        solver.SetTimeLimit(max(1, int(seconds * 1000)))
    status = solver.Solve()
    elapsed = perf_counter() - started
    if status not in (solver.OPTIMAL, solver.FEASIBLE):
        return {"status": "no_solution", "solve_seconds": elapsed,
                "upper_bound": objective.BestBound(), "lower_bound": None,
                "absolute_gap": None}

    mass = {d: x[d].solution_value() for d in range(schedules) if x[d].solution_value() > 1e-9}
    responses = {t: max(range(action_counts[t]), key=lambda a: q[t][a].solution_value())
                 for t in range(len(priors))}
    lower_bound = objective.Value()
    upper_bound = max(lower_bound, objective.BestBound())
    return {
        "status": "optimal" if status == solver.OPTIMAL else "feasible",
        "mass": mass,
        "responses": responses,
        "value": lower_bound,
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "absolute_gap": max(0.0, upper_bound - lower_bound),
        "solve_seconds": elapsed,
    }


def multiple_lp(priors, leader, follower, tolerance: float = 1e-8) -> dict:
    """Exact multiple-LP reference via enumeration of one response per type."""
    schedules, action_counts = _validate(priors, leader, follower)
    best = None
    solved = 0
    for responses in product(*(range(count) for count in action_counts)):
        solver = pywraplp.Solver.CreateSolver("GLOP")
        if solver is None:
            raise RuntimeError("GLOP unavailable")
        x = [solver.NumVar(0.0, 1.0, "") for _ in range(schedules)]
        solver.Add(solver.Sum(x) == 1.0)
        for t, chosen in enumerate(responses):
            chosen_value = solver.Sum(float(follower[t][chosen][d]) * x[d]
                                      for d in range(schedules))
            for action in range(action_counts[t]):
                other_value = solver.Sum(float(follower[t][action][d]) * x[d]
                                         for d in range(schedules))
                solver.Add(chosen_value + tolerance >= other_value)
        objective = solver.Objective()
        objective.SetMaximization()
        for d in range(schedules):
            coefficient = sum(float(priors[t]) * float(leader[t][responses[t]][d])
                              for t in range(len(priors)))
            objective.SetCoefficient(x[d], coefficient)
        status = solver.Solve()
        solved += 1
        if status != solver.OPTIMAL:
            continue
        value = objective.Value()
        if best is None or value > best["value"] + tolerance:
            best = {"value": value,
                    "mass": {d: x[d].solution_value() for d in range(schedules)
                             if x[d].solution_value() > 1e-9},
                    "responses": dict(enumerate(responses))}
    if best is None:
        raise RuntimeError("No follower response profile was feasible")
    return {**best, "status": "optimal", "lp_count": solved}


def best_pure_value(priors, leader, follower) -> float:
    """Evaluate every pure leader schedule with leader-favorable follower ties."""
    schedules, action_counts = _validate(priors, leader, follower)
    best = float("-inf")
    for d in range(schedules):
        value = 0.0
        for t, count in enumerate(action_counts):
            max_follower = max(float(follower[t][a][d]) for a in range(count))
            leader_payoff = max(float(leader[t][a][d]) for a in range(count)
                                if float(follower[t][a][d]) >= max_follower - 1e-9)
            value += float(priors[t]) * leader_payoff
        best = max(best, value)
    return best
