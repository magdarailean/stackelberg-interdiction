import json
from random import Random
from statistics import mean

import networkx as nx

from .defender import Rules
from .evaluate import Sample, interval
from .follower import Scenario
from .geo import DATA
from .interception import expected_interception, optimize_interception


def random_layout(seed: int) -> tuple:
    rng = Random(f"{seed}:layout")
    graph = nx.DiGraph()
    for branch in range(rng.randint(3, 6)):
        chain = ["s", *(f"{branch}:{i}" for i in range(rng.randint(2, 5))), "t"]
        for u, v in zip(chain, chain[1:]):
            graph.add_edge(u, v, capacity=rng.randint(8, 24))
    return graph, tuple(rng.sample(list(graph.edges), 6))


def draws(layout: nx.DiGraph, seed: str, count: int) -> Sample:
    rng = Random(seed)
    days = []
    for _ in range(count):
        graph = layout.copy()
        for _, _, attrs in graph.edges(data=True):
            attrs["capacity"] += rng.randint(-3, 3)
        days.append((Scenario(graph, "s", "t"),))
    return Sample(tuple(days))


def compare(seed: int, cfg: dict) -> dict:
    layout, sites = random_layout(seed)
    train = draws(layout, f"{seed}:train", 4)
    test = draws(layout, f"{seed}:test", 6)
    rules = Rules((sites,), budget=2, crews=2)
    greedy = frozenset()
    for _ in range(2):
        greedy = max((greedy | {(0, site)} for site in sites if (0, site) not in greedy),
                     key=lambda plan: expected_interception(train, plan, cfg))
    fitted = optimize_interception(train, rules, cfg, 4, incumbent=greedy, target_hours=2)
    return dict(seed=seed, greedy=expected_interception(test, greedy, cfg),
                optimized=expected_interception(test, fitted.plan, cfg),
                seconds=fitted.total_seconds, gap=fitted.absolute_gap)


def main() -> None:
    cfg = json.loads((DATA / "research.json").read_text())
    cfg.update(detection_probability=.6, processing_per_crew_hour=240)
    runs = [compare(seed, cfg) for seed in range(42, 62)]
    gains = [r["optimized"] - r["greedy"] for r in runs]
    wins = sum(gain > 1e-9 for gain in gains)
    print(json.dumps(dict(runs=runs, wins=wins, win_share=wins/len(runs),
                          losses=sum(gain < -1e-9 for gain in gains), gain_ci95=interval(gains, 42),
                          mean_seconds=mean(r["seconds"] for r in runs), max_gap=max(r["gap"] for r in runs))))


if __name__ == "__main__":
    main()
