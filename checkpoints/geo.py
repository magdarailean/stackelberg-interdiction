import csv
import hashlib
import json
from argparse import Namespace
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from random import Random
from statistics import mean

import networkx as nx

from .defender import Rules
from .evaluate import Sample
from .experiment import diagnostics, experiment
from .follower import Edge, Scenario
from .milp import optimize

DATA = Path(__file__).resolve().parents[1] / "data"


def config() -> dict:
    return json.loads((DATA / "fixture.json").read_text())


def rows(name: str) -> list[dict]:
    with (DATA / name).open(newline="") as stream:
        return list(csv.DictReader(stream))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def build() -> Path:
    cfg = config()
    graph = nx.DiGraph()
    gates = {(r["from_node"], r["to_node"]): r for r in rows("crossings.csv")}
    for y, lane in enumerate("ab"):
        for i in range(10):
            graph.add_node(f"{lane}{i}", country="A" if i < 4 else "B" if i < 7 else "C",
                           x=i, y=y)
    pairs = [(f"{l}{i}", f"{l}{i+1}") for l in "ab" for i in range(9)]
    pairs.extend([("a3", "b3"), ("b6", "a6")])
    for lane in "ab":
        for i in (0, 2, 5, 8):
            u, v, mid = f"{lane}{i}", f"{lane}{i+1}", f"{lane}{i}m"
            graph.add_node(mid, country=graph.nodes[u]["country"], x=i+0.5, y=graph.nodes[u]["y"])
            pairs.remove((u, v))
            pairs.extend([(u, mid), (mid, v)])
    for u, v in pairs:
        country = graph.nodes[u]["country"]
        road = "primary" if u[0] == "a" else "secondary"
        spec = cfg["classes"][road]
        capacity = spec["capacity"]
        gate_id = ""
        if country != graph.nodes[v]["country"]:
            gate = gates.get((u, v))
            if not gate:
                continue
            if (gate["from_country"], gate["to_country"]) != (country, graph.nodes[v]["country"]):
                raise ValueError("Gate direction disagrees with node jurisdictions")
            gate_id = gate["crossing_id"]
            capacity = min(capacity, float(gate["capacity_flow_per_hour"]))
        graph.add_edge(u, v, country=country, road_class=road, capacity=float(capacity),
                       crossing_id=gate_id, length_m=cfg["segment_m"],
                       travel_time_s=cfg["segment_m"] * 3.6 / spec["speed_kmh"])
    path = DATA / (cfg["snapshot"] + ".graphml")
    nx.write_graphml(graph, path)
    metadata = dict(source="fictional fixture", bbox=None, osmnx_version=None,
                    created_utc=datetime.now(timezone.utc).isoformat(), nodes=len(graph),
                    edges=graph.number_of_edges(), sha256=digest(path),
                    layers={n: digest(DATA / n) for n in ("fixture.json", "candidate_sites.csv", "crossings.csv")})
    path.with_suffix(".json").write_text(json.dumps(metadata, indent=2))
    return path


def load() -> nx.DiGraph:
    path = DATA / (config()["snapshot"] + ".graphml")
    meta = json.loads(path.with_suffix(".json").read_text())
    if digest(path) != meta["sha256"] or any(digest(DATA / n) != d for n, d in meta["layers"].items()):
        raise ValueError("Snapshot inputs changed")
    graph = nx.read_graphml(path)
    if (len(graph), graph.number_of_edges()) != (meta["nodes"], meta["edges"]):
        raise ValueError("Snapshot count mismatch")
    return graph


def planning(graph: nx.DiGraph, mode: str, slots: int, budget: int, shift: int, large: bool = False) -> Rules:
    groups = {country: set() for country in config()["pools"][mode]}
    for row in rows("candidate_sites.csv"):
        edge = row["from_node"], row["to_node"]
        country = row["country"]
        if any(graph.nodes[n]["country"] != country for n in edge) or not graph.has_edge(*edge):
            raise ValueError("Invalid candidate reference")
        if country in row["allowed_authorities"].split("|"):
            groups[country].add(edge)
    if large:
        for u,v in config()["large"]["sites"]:
            if not graph.has_edge(u,v) or graph.nodes[u]["country"] != graph.nodes[v]["country"]:
                raise ValueError("Invalid hypothetical fixture site")
            groups[graph.nodes[u]["country"]].add((u,v))
    limits = config()["pools"][mode]
    pools = tuple((frozenset(sites), limits[c]) for c, sites in groups.items())
    sites = tuple(sorted(e for group in groups.values() for e in group))
    return Rules((sites,) * slots, budget, sum(limits.values()), shift, pools=pools)


def reduce_graph(graph: nx.DiGraph, keep: set, candidates: tuple[Edge, ...]) -> nx.DiGraph:
    reduced = graph.copy()
    for n in tuple(graph):
        if n in keep or reduced.in_degree(n) != 1 or reduced.out_degree(n) != 1:
            continue
        u, = reduced.predecessors(n)
        v, = reduced.successors(n)
        if u == v or (u, v) in candidates:
            continue
        cap = min(reduced[u][n]["capacity"], reduced[n][v]["capacity"])
        reduced.remove_node(n)
        reduced.add_edge(u, v, capacity=cap + reduced.get_edge_data(u, v, {}).get("capacity", 0))
    return reduced


def samples(graph: nx.DiGraph, rules: Rules, count: int, seed: str, shifted: bool,
            factor: float, demand_factors: tuple[float, ...] | None = None,
            shift_level: float | None = None) -> tuple[Sample, Sample, list[float]]:
    cfg = config()
    sites = rules.allowed[0]
    keep = set(cfg["origins"] + cfg["destinations"] + ["source", "sink"])
    keep.update(n for e in sites for n in e)
    keep.update(n for u, v, gate in graph.edges.data("crossing_id") if gate for n in (u, v))
    rng = Random(seed)
    level = float(shifted) if shift_level is None else shift_level
    multiplier = 1 + level*(cfg["shift_multiplier"]-1)
    shares = [(1-level)*a+level*b for a,b in zip(cfg["shares"],cfg["shifted_shares"])]
    full, small, errors = [], [], []
    for _ in range(count):
        day, compressed = [], []
        for _ in rules.allowed:
            g = graph.copy()
            for u, v, road in graph.edges.data("road_class"):
                if rng.random() < cfg["classes"][road]["closure"] * multiplier:
                    g[u][v]["capacity"] = 0
            total = rng.randint(*cfg["supply"])
            for n, share in zip(cfg["origins"], shares, strict=True):
                g.add_edge("source", n, capacity=total * share)
            modifiers = demand_factors or (1,) * len(cfg["destinations"])
            for n, modifier in zip(cfg["destinations"], modifiers, strict=True):
                g.add_edge(n, "sink", capacity=rng.randint(*cfg["demand"]) * modifier)
            a = Scenario(g, "source", "sink")
            b = Scenario(reduce_graph(g, keep, sites), "source", "sink")
            flow = a.delivered()
            errors.append(abs(flow-b.delivered()) / (flow or 1))
            day.append(a)
            compressed.append(b)
        full.append(tuple(day))
        small.append(tuple(compressed))
    return Sample(tuple(full), factor), Sample(tuple(small), factor), errors


def regional(args: Namespace) -> dict:
    graph = load()
    rules = planning(graph, args.planner, args.slots, args.budget, args.shift)
    detailed, reduced, errors = {}, {}, []
    for split in ("train", "tune", "nominal_test", "shifted_test"):
        count = args.train if split == "train" else args.test
        detailed[split], reduced[split], err = samples(graph, rules, count, f"{args.seed}:{split}",
                                                      split == "shifted_test", args.factor)
        errors.extend(err)
    train = reduced.pop("train")
    report = experiment(train, reduced, rules, graph, args.seed, args.time_limit, detailed)
    report.update(network="fictional regional fixture", planner=args.planner, slots=args.slots,
                  candidate_count=len(rules.allowed[0]), detailed_edges=graph.number_of_edges(),
                  reduced_edges=train.days[0][0].graph.number_of_edges()
                  - len(config()["origins"]) - len(config()["destinations"]),
                  mean_relative_flow_error=mean(errors), checked_slots=len(errors), scaling=[])
    if mean(errors) > config()["tolerance"]:
        raise ValueError("Flow discrepancy exceeds tolerance")
    for candidates, slots, days in config()["scaling"]:
        subset = rules.allowed[0][:candidates]
        scoped = replace(rules, allowed=(subset,) * slots)
        _, sample, _ = samples(graph, scoped, days, f"{args.seed}:scaling", False, args.factor)
        result = diagnostics(optimize(sample, scoped, args.time_limit), sample)
        report["scaling"].append(dict(candidates=len(subset), slots=slots, scenarios=days,
                                      solve_seconds=result["solve_seconds"], gap=result["relative_gap"]))
    return report
