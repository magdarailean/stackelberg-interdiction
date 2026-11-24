"""Run and report a reproducible synthetic interdiction experiment."""

import argparse
import json
from functools import cache
from statistics import mean
from time import perf_counter

from interdiction import expected_flow, greedy, optimize, random_schedule, synthetic_network


def run(rows, columns, budget, seed, train_count, test_count, time_limit):
    sites, make = synthetic_network(rows, columns)
    train = [make(seed + i) for i in range(train_count)]
    nominal = [make(seed + train_count + i) for i in range(test_count)]
    shifted = [make(seed + train_count + test_count + i, shift=True) for i in range(test_count)]

    started = perf_counter()
    greedy_schedule = greedy(train, sites, budget)
    greedy_seconds = perf_counter() - started
    result = optimize(train, sites, budget, time_limit, incumbent=greedy_schedule)
    policies = {
        "no_checkpoints": [()],
        "random": [random_schedule(sites, budget, f"{seed}:random:{i}") for i in range(20)],
        "greedy": [greedy_schedule],
        "milp": [result.schedule],
    }

    splits = {}
    for label, scenarios in (("train", train), ("nominal_test", nominal), ("shifted_test", shifted)):
        @cache
        def delivered(index, schedule):
            return scenarios[index].delivered(schedule)

        indices = range(len(scenarios))
        greedy_flows = [delivered(i, frozenset(greedy_schedule)) for i in indices]
        baseline = [delivered(i, frozenset()) for i in indices]
        scores = {}
        for name, schedules in policies.items():
            plans = [frozenset(plan) for plan in schedules]
            flows = [mean(delivered(i, plan) for plan in plans) for i in indices]
            scores[name] = {
                "mean_checkpoint_hours": mean(sum(site.hours for site in plan) for plan in schedules),
                "mean_delivered": mean(flows),
                "mean_delivery_reduction": mean(a - b for a, b in zip(baseline, flows)),
                "mean_improvement_over_greedy": mean(a - b for a, b in zip(greedy_flows, flows)),
            }
        splits[label] = {
            "scenarios": len(scenarios),
            "edge_count_range": [min(s.graph.number_of_edges() for s in scenarios),
                                 max(s.graph.number_of_edges() for s in scenarios)],
            "policies": scores,
        }

    upper = expected_flow(train, result.schedule)
    return {
        "seed": seed,
        "grid": [rows, columns],
        "candidate_count": len(sites),
        "budget_checkpoint_hours": budget,
        "greedy_seconds": greedy_seconds,
        "milp": {
            "status": result.status,
            "build_and_solve_seconds": result.seconds,
            "solve_limit_seconds": time_limit,
            "train_upper_bound": upper,
            "train_lower_bound": result.bound,
            "train_absolute_gap": None if result.bound is None else max(0, upper - result.bound),
        },
        "splits": splits,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=6)
    parser.add_argument("--columns", type=int, default=8)
    parser.add_argument("--budget", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train", type=int, default=4)
    parser.add_argument("--test", type=int, default=8, help="Scenario count per test split")
    parser.add_argument("--time-limit", type=float, default=10, help="SCIP solve limit in seconds")
    args = parser.parse_args()
    if min(args.rows, args.columns) < 2 or min(args.train, args.test) < 1:
        parser.error("The grid needs at least two rows and columns, and each split needs a scenario.")
    if args.budget < 0 or not 0 < args.time_limit < float("inf"):
        parser.error("Budget must be nonnegative and the time limit must be finite and positive.")
    print(json.dumps(run(args.rows, args.columns, args.budget, args.seed,
                         args.train, args.test, args.time_limit), indent=2))


if __name__ == "__main__":
    main()
