import json
from random import Random
from statistics import mean

import networkx as nx

from .defender import Rules
from .evaluate import Sample, interval
from .follower import Scenario
from .geo import DATA, reduce_graph
from .interception import expected_interception, optimize_interception


def fixture_topology(roads: nx.MultiDiGraph, cfg: dict) -> tuple:
    count = cfg["subdivisions"]
    graph = nx.DiGraph()
    sites = []
    for u, v, key, road in roads.edges(keys=True, data="road_class"):
        chain = [u, *(f"{u}:{v}:{key}:{i}" for i in range(1, count)), v]
        edges = list(zip(chain, chain[1:]))
        graph.add_edges_from(edges, capacity=cfg["capacity"][road])
        if road in {"primary", "trunk", "motorway"}:
            sites.append(edges[count // 2])
    keep = {cfg["origin"], cfg["destination"], *(n for edge in sites for n in edge)}
    return graph, reduce_graph(graph, keep, tuple(sites)), tuple(sites)


def terminal_sample(graph, cfg, bounds, rng):
    scenario = graph.copy()
    scenario.add_edge("source", cfg["origin"], capacity=rng.randint(*bounds))
    scenario.add_edge(cfg["destination"], "sink", capacity=rng.randint(*bounds))
    return Sample(((Scenario(scenario, "source", "sink"),),))


def fixture_report(roads: nx.MultiDiGraph, seed: int) -> dict:
    cfg = json.loads((DATA / "fictional_corridor.json").read_text())
    ledger = json.loads((DATA / "research.json").read_text())
    detailed, reduced, sites = fixture_topology(roads, cfg)
    rules = Rules((sites,), budget=1, crews=1)
    plans = [frozenset({(0, site)}) for site in sites]
    runs = []
    errors = []
    for draw in range(seed, seed + 10):
        train = terminal_sample(reduced, cfg, cfg["nominal_terminal_capacity"], Random(f"{draw}:train"))
        greedy = max(plans, key=lambda plan: expected_interception(train, plan, ledger))
        fit = optimize_interception(train, rules, ledger, 4, incumbent=greedy, target_hours=1)
        row = dict(seed=draw, seconds=fit.total_seconds, gap=fit.absolute_gap)
        for split in ("nominal", "shifted"):
            bounds = cfg[f"{split}_terminal_capacity"]
            full, small = (terminal_sample(g, cfg, bounds, Random(f"{draw}:{split}"))
                           for g in (detailed, reduced))
            for plan in [frozenset(), *plans]:
                errors.append(abs(full.mean(plan) - small.mean(plan)))
            row[split] = [expected_interception(full, plan, ledger) for plan in (greedy, fit.plan)]
        runs.append(row)
    if max(errors) > 1e-9:
        raise ValueError("Fictional fixture reduction changed flow")
    return dict(mode="fictional_fixture", detailed_edges=detailed.number_of_edges(),
                reduced_edges=reduced.number_of_edges(), candidate_count=len(sites), runs=runs,
                mean_seconds=mean(r["seconds"] for r in runs), max_gap=max(r["gap"] for r in runs),
                max_flow_error=max(errors), comparisons=len(errors),
                gain_ci={s: interval([r[s][1] - r[s][0] for r in runs], seed)
                         for s in ("nominal", "shifted")})
