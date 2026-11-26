from math import ceil
from statistics import mean
from time import perf_counter

import networkx as nx

from .defender import Rules, centrality, greedy, random_schedule
from .evaluate import Sample, interval
from .milp import Result, optimize


def diagnostics(result: Result, sample: Sample) -> dict:
    upper = sample.mean(result.plan)
    gap = None if result.lower is None else max(0., upper-result.lower)
    return dict(status=result.status, upper=upper, lower=result.lower, absolute_gap=gap,
                relative_gap=None if gap is None else gap / upper if upper else 0.,
                solve_seconds=result.solve_seconds, build_seconds=result.build_seconds,
                variables=result.variables, constraints=result.constraints)


def experiment(train: Sample, tests: dict[str, Sample], rules: Rules,
               topology: nx.DiGraph, seed: int, seconds: float,
               detailed: dict[str, Sample] | None = None) -> dict:
    start = perf_counter()
    heuristic = greedy(rules, train.mean)
    elapsed = perf_counter()-start
    fitted = optimize(train, rules, seconds, heuristic)
    policies = {"no_checkpoints": [frozenset()], "greedy": [heuristic], "milp": [fitted.plan],
                "centrality": [centrality(rules, topology, seed)],
                "random": [random_schedule(rules, seed+i) for i in range(20)]}
    report = dict(milp=diagnostics(fitted, train), greedy_seconds=elapsed, splits={})
    if detailed:
        report["fixture_schedule"] = sorted(fitted.plan)
    for name, sample in {"train": train, **tests}.items():
        plans = policies.copy()
        split = {}
        if name not in ("train", "tune"):
            incumbent = min((p for group in plans.values() for p in group), key=sample.mean)
            oracle = optimize(sample, rules, seconds, incumbent)
            plans["hindsight_oracle_unattainable"] = [oracle.plan]
            split["oracle_solver"] = diagnostics(oracle, sample)
        scores = {}
        if detailed:
            sample = detailed[name]
        baseline = sample.flows(frozenset())
        reference = sample.flows(heuristic)
        for policy, group in plans.items():
            flows = [mean(row) for row in zip(*(sample.flows(p) for p in group))]
            gains = [g-v for g, v in zip(reference, flows)]
            scores[policy] = dict(mean_delivered=mean(flows),
                mean_checkpoint_hours=mean(map(len, group)),
                mean_delivery_reduction=mean(baseline)-mean(flows),
                mean_improvement_over_greedy=mean(gains),
                delivered_ci95=interval(flows, seed)[1:], gain_ci95=interval(gains, seed)[1:],
                worst_tail=mean(sorted(flows, reverse=True)[:ceil(len(flows)/10)]))
        report["splits"][name] = dict(**split, policies=scores, scenarios=len(sample.days))
    return report
