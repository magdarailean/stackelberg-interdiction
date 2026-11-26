import argparse
import json
from dataclasses import replace
from pathlib import Path
from statistics import mean
from time import perf_counter

from .defender import Rules, random_schedule
from .evaluate import Sample, interval
from .geo import DATA
from .interception import accounting_totals, expected_interception, optimize_interception
from .network import synthetic_network
from .study import dobss_main_family


GRID_SIZE = 60
SEEDS = tuple(range(42, 52))
CELLS = (
    dict(name="grid_low_rate", layout="grid", budget=2, crews=2, factor=.3, detection=.25, rate=3),
    dict(name="grid_high_rate", layout="grid", budget=2, crews=2, factor=.3, detection=.6, rate=240),
    dict(name="serial_pair", layout="serial_pair", budget=2, crews=2, factor=.3, detection=.6, rate=240),
    dict(name="serial_single_crew", layout="serial_pair", budget=2, crews=1, factor=.5, detection=.25, rate=240),
)


def serial_pair(scenario, shifted):
    graph = scenario.graph
    sites = (("branch-a", "branch-b"), ("branch-c", "branch-d"), ("branch-d", "branch-e"))
    for chain, capacity in (
        ((scenario.source, "branch-a", "branch-b", scenario.sink), 13 if shifted else 10),
        ((scenario.source, "branch-c", "branch-d", "branch-e", scenario.sink), 12 if shifted else 15),
    ):
        graph.add_weighted_edges_from(((u, v, capacity) for u, v in zip(chain, chain[1:])), weight="capacity")
    return sites


def sample_family(make, seed, cell, shifted=False):
    days = []
    sites = ()
    for day in range(2):
        scenario = make(seed + day, shifted)
        if cell["layout"] == "serial_pair":
            sites = serial_pair(scenario, shifted)
        days.append((scenario,))
    return Sample(tuple(days), cell["factor"]), sites


def fit_game(plans, train, rules, cfg, seconds):
    count = len(train)
    pooled = Sample(tuple(day for sample in train for day in sample.days), train[0].factor)
    game = dobss_main_family(plans, train, cfg, False)
    initial_pool = len(plans)
    response = game["type_responses"]
    responders = [sample for i, sample in enumerate(train) if response.get(i) == "depart"]
    if responders and len(responders) < count:
        days = tuple(day for sample in responders for day in sample.days)
        weights = tuple(cfg["dobss"]["type_priors"][i] * w for i,sample in enumerate(train)
                        if response.get(i) == "depart" for w in sample.weights)
        total = sum(weights)
        pooled = Sample(days, train[0].factor, tuple(w/total for w in weights))
    pricing = optimize_interception(pooled, rules, cfg, seconds, incumbent=plans[0])
    if pricing.plan not in plans:
        plans.append(pricing.plan)
        game = dobss_main_family(plans, train, cfg, False)
    global_upper = cfg["detection_probability"] * cfg["processing_per_crew_hour"] * rules.budget
    game.update(initial_pool_size=initial_pool, response_candidates_added=len(plans)-initial_pool,
                pricing="interception-only best response; heuristic for general-sum DOBSS",
                pool_status=game["status"], status="restricted", global_upper_bound=global_upper,
                response_seconds=pricing.total_seconds, response_gap=pricing.absolute_gap,
                global_absolute_gap=global_upper-game["lower_bound"])
    return game


def run_seed(cell, seed, seconds, cfg):
    start = perf_counter()
    candidates, make = synthetic_network(GRID_SIZE, GRID_SIZE)
    root = seed*100
    train, sites = sample_family(make, root, cell)
    nominal, _ = sample_family(make, root+20, cell)
    shifted, _ = sample_family(make, root+40, cell, True)
    second_type, _ = sample_family(make, root+60, cell, True)
    sites = sites or candidates[:3]
    hours = min(cell["budget"],cell["crews"],len(sites))
    rules = Rules((sites,), budget=hours, crews=cell["crews"], delay_cap=6., delay_per_slot=(3.,))
    inspection = dict(cfg, detection_probability=cell["detection"],processing_per_crew_hour=cell["rate"])
    score = lambda plan: -expected_interception(train, plan, inspection)
    baseline = frozenset()
    for _ in range(hours):
        baseline = min((baseline | {(0,edge)} for edge in sites if (0,edge) not in baseline),key=score)
    fitted = optimize_interception(train,rules,inspection,seconds,incumbent=baseline,target_hours=hours)
    game_cfg = dict(inspection, demand_profiles=[[1,0],[0,1]],dobss=dict(
                    cfg["dobss"],type_priors=[.5,.5],time_limit_seconds=seconds))
    plans = list(dict.fromkeys([frozenset(), baseline, fitted.plan, random_schedule(rules,seed)]))
    game = fit_game(plans,[train,second_type],rules,game_cfg,seconds)
    evaluations = {}
    for label, sample in (("nominal",nominal),("shifted",shifted)):
        evaluations[label] = {name: accounting_totals(sample,plan,inspection)
                              for name,plan in (("greedy",baseline),("optimized",fitted.plan))}
    return dict(seed=seed, edges=min(slot.graph.number_of_edges() for sample in (train,nominal,shifted)
                                     for day in sample.days for slot in day),
                hours=hours, evaluations=evaluations,
                optimizer=dict(status=fitted.status,seconds=fitted.total_seconds,gap=fitted.absolute_gap),
                game=game, total_seconds=perf_counter()-start)


def summary(runs):
    splits = {}
    for label in ("nominal","shifted"):
        gains = [r["evaluations"][label]["optimized"]["intercepted"]-
                 r["evaluations"][label]["greedy"]["intercepted"] for r in runs]
        value,lo,hi = interval(gains,42)
        splits[label] = dict(mean_gain=value, ci95=[lo,hi],wins=sum(x>1e-9 for x in gains),
                             losses=sum(x< -1e-9 for x in gains),seeds=len(gains))
    return dict(splits=splits, optimizer_mean_seconds=mean(r["optimizer"]["seconds"] for r in runs),
                optimizer_max_gap=max(r["optimizer"]["gap"] for r in runs),
                dobss_mean_seconds=mean(r["game"]["solve_seconds"] for r in runs),
                dobss_max_pool_gap=max(r["game"]["absolute_gap"] for r in runs),
                dobss_mean_global_gap=mean(r["game"]["global_absolute_gap"] for r in runs),
                mean_pool_randomization_value=mean(r["game"]["value_of_randomization"] for r in runs))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seconds",type=float,default=4)
    parser.add_argument("--cell",choices=[cell["name"] for cell in CELLS])
    args=parser.parse_args()
    cfg=json.loads((DATA/"research.json").read_text())
    results=[]
    for cell in CELLS:
        if args.cell and cell["name"] != args.cell:
            continue
        runs=[run_seed(cell,seed,args.seconds,cfg) for seed in SEEDS]
        results.append(dict(parameters=cell,summary=summary(runs),runs=runs))
    content=json.dumps(results,indent=2,allow_nan=False)
    if args.output:
        args.output.write_text(content+"\n")
    else:
        print(content)


if __name__ == "__main__":
    main()
