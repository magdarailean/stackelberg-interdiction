import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from random import Random
from statistics import mean
from time import perf_counter

from .accounting import account
from .backlog import carry_day
from .defender import Plan, centrality, greedy, random_schedule
from .evaluate import Sample, interval
from .experiment import diagnostics
from .game import generate_responses, schedules, solve_game
from .geo import DATA, config, load, planning, samples
from .milp import optimize
from .matched import matched_fits
from .risk import risk_mixture, upper_tail
from .scale import subdivision_check
from .roadcheck import road_check


def response(matrix: list[list[float]], mass: dict[int, float]) -> int:
    return max(range(len(matrix[0])), key=lambda j: sum(p * matrix[i][j] for i, p in mass.items()))


def observed_choices(matrix: list[list[float]], mass: dict[int, float], revealed: bool) -> dict[int, int]:
    shared = response(matrix, mass)
    return {i: response(matrix, {i: 1}) if revealed else shared for i in mass}


def learn(training: list[list[float]], testing: list[list[float]], mass: dict[int, float],
          rounds: int, prior: float, seed: int) -> list[float]:
    rng = Random(seed)
    support = list(mass)
    counts = dict.fromkeys(range(len(training)), prior / len(training))
    values = []
    for _ in range(rounds):
        choice = response(training, counts)
        row = rng.choices(support, weights=list(mass.values()))[0]
        values.append(testing[row][choice])
        counts[row] += 1
    return values


def retention(curves, fraction):
    output = {}
    for name, curve in curves.items():
        gains = [a-b for a,b in zip(curves["none"],curve)]
        first_loss = None
        if gains[0] > 0:
            first_loss = next((t for t,g in enumerate(gains,1) if g < fraction*gains[0]),None)
        output[name] = dict(initial_gain=gains[0],final_gain=gains[-1],first_round_below=first_loss)
    return output


def learning_intervals(fit, testing, cfg, seed):
    output = {}
    for name,mass in fit.policies.items():
        curves = [learn(fit.matrices,testing,mass,cfg["learning_rounds"],cfg["learning_prior"],seed+i)
                  for i in range(cfg["learning_repetitions"])]
        output[name] = [dict(zip(("mean","lower","upper"),interval(list(values),seed)))
                        for values in zip(*curves)]
    return output


def ledger(sample: Sample, plan: Plan, cfg: dict) -> dict:
    daily = []
    for i, day in enumerate(sample.days):
        totals = Counter()
        for t, slot in enumerate(day):
            edges = frozenset(e for h, e in plan if h == t)
            supply = slot.graph.out_degree(slot.source, weight="capacity")
            demand = slot.graph.in_degree(slot.sink, weight="capacity")
            totals.update(account(supply, demand, sample.hourly(i, t, edges), len(edges), cfg,t))
        if cfg.get("carry_over"):
            delivered,deferred = carry_day(day,plan,sample.factor,cfg)
            totals.update(delivered_after_carryover=delivered,day_end_backlog=deferred)
        daily.append(totals)
    return {key: mean(row[key] for row in daily) for key in daily[0]}


def contract_utility(outcome: dict, cfg: dict) -> float:
    attempted = outcome["supply"] - outcome["undeparted"]
    return (cfg["delivered_unit_value"] * outcome["delivered"]
            - cfg["interception_loss_per_unit"] * outcome["intercepted"]
            - cfg["attempt_cost_per_unit"] * attempted)



@dataclass
class Fit:
    plans: list
    policies: dict
    matrices: list
    complete: bool
    game: dict
    solver: dict
    seconds: dict
    utilities: list
    selected_alpha: float
    matched: dict


def build_splits(args, cfg, rules, graph):
    full, small = {}, {}
    errors = []
    for split in ("train", "tune", "nominal_test", "shifted_test"):
        full[split], small[split] = [], []
        for profile in cfg["demand_profiles"]:
            detail, reduced, err = samples(graph, rules, args.train if split == "train" else args.test,
                                           f"{args.seed}:study:{split}", split == "shifted_test", args.factor,
                                           tuple(profile))
            full[split].append(detail)
            small[split].append(reduced)
            errors.extend(err)
    return full, small, errors


def fit_policies(args, cfg, rules, graph, small):
    train = small["train"]
    pooled = Sample(tuple(day for sample in train for day in sample.days), args.factor)
    greedy_plan = greedy(rules, lambda p: max(s.mean(p) for s in train),lookahead=3)
    fixed = optimize(pooled, rules, args.time_limit, greedy_plan)
    randoms = [random_schedule(rules, args.seed+i) for i in range(20)]
    static = centrality(rules, graph, args.seed)
    plans, complete = schedules(rules, args.seed, cfg["schedule_limit"],
                                [frozenset(), greedy_plan, fixed.plan, static, *randoms])
    index = {plan: i for i, plan in enumerate(plans)}
    matrices = [[s.mean(p) for s in train] for p in plans]
    start = perf_counter()
    if complete:
        game = solve_game(matrices)
        game["stopping"] = "gap_tolerance"
    else:
        game = generate_responses(train, rules, plans, matrices, args.time_limit, 20)
        index = {plan: i for i, plan in enumerate(plans)}
    game_seconds = perf_counter()-start
    start = perf_counter()
    losses = [pooled.flows(p) for p in plans]
    candidates = {a: risk_mixture([losses], a)
                  for a in cfg["alpha_candidates"]}
    def tune_score(alpha):
        mass = candidates[alpha]
        values = [sum(p*v for p,v in zip(mass.values(), day)) for s in small["tune"]
                  for day in zip(*(s.flows(plans[i]) for i in mass))]
        return upper_tail(values, [1/len(values)]*len(values), cfg["tail_alpha"])
    selected_alpha = min(candidates, key=tune_score)
    robust_seconds = perf_counter()-start
    start = perf_counter()
    regimes = [losses]
    for level in cfg["shift_levels"][1:]:
        stressed = [samples(graph,rules,args.train,f"{args.seed}:risk-training",True,args.factor,
                            tuple(profile),level)[1] for profile in cfg["demand_profiles"]]
        regimes.append([[v for s in stressed for v in s.flows(plan)] for plan in plans])
    worst = risk_mixture(regimes, 0., cfg["contamination"])
    worst_seconds = perf_counter()-start
    policies = {name: {index[p]: 1.} for name, p in
                [("none", frozenset()), ("centrality", static), ("greedy", greedy_plan),
                 ("deterministic_milp", fixed.plan)]}
    policies["robust_cvar"] = candidates[selected_alpha]
    policies["worst_case"] = worst
    start = perf_counter()
    policies["optimized_pure_game"] = {min(range(len(plans)), key=lambda i: max(matrices[i])): 1.}
    pure_seconds = perf_counter()-start
    policies["random"] = {index[p]: n/len(randoms) for p, n in Counter(randoms).items()}
    policies["mixed"] = {i: x for i, x in game["mass"].items() if x > 0}
    seconds = {"mixed": game_seconds, "optimized_pure_game": pure_seconds, "robust_cvar": robust_seconds,
               "worst_case":worst_seconds}
    active = set().union(*policies.values())
    utilities = [[contract_utility(ledger(s, plans[i], cfg), cfg) for s in train]
                 if i in active else [] for i in range(len(plans))]
    matched = matched_fits(plans,policies,matrices,regimes,selected_alpha,cfg["contamination"])
    return Fit(plans, policies, matrices, complete, game, diagnostics(fixed, pooled), seconds, utilities, selected_alpha,matched)


def matched_report(full,fit,cfg):
    rows = []
    for split,pair in full.items():
        cache = {}
        for revealed in (False,True):
            for baseline,policies in fit.matched.items():
                for name,mass in {"baseline":fit.policies[baseline],**policies}.items():
                    choices = observed_choices(fit.matrices,mass,revealed)
                    delivered = 0.
                    hours = sum(p*len(fit.plans[i]) for i,p in mass.items())
                    for i,p in mass.items():
                        j = choices[i]
                        if (i,j) not in cache:
                            cache[i,j] = ledger(pair[j],fit.plans[i],cfg)["delivered"]
                        delivered += p*cache[i,j]
                    if name == "baseline":
                        reference = delivered
                    rows.append(dict(split=split,information="revealed" if revealed else "distribution",
                                     baseline=baseline,policy=name,checkpoint_hours=hours,delivered=delivered,
                                     gain=reference-delivered,gain_per_hour=(reference-delivered)/hours if hours else None))
    return rows


def matched_interception_report(full, fit, cfg, seed):
    """Compare modeled interception with greedy at the same checkpoint-hour distribution."""
    rows = []
    policy_pairs = {
        "deterministic_milp_matched_hours": fit.matched["greedy"]["deterministic_milp"],
        "greedy": fit.policies["greedy"],
    }
    for split in ("nominal_test", "shifted_test"):
        pair = full[split]
        for revealed in (False, True):
            observed = {
                name: observed_choices(fit.matrices, mass, revealed)
                for name, mass in policy_pairs.items()
            }
            daily = {
                name: [Counter() for _ in pair[0].days]
                for name in policy_pairs
            }
            hours = {}
            for name, mass in policy_pairs.items():
                hours[name] = sum(p * len(fit.plans[i]) for i, p in mass.items())
                for i, probability in mass.items():
                    sample = pair[observed[name][i]]
                    for day_index, day in enumerate(sample.days):
                        result = ledger(Sample((day,), sample.factor), fit.plans[i], cfg)
                        daily[name][day_index].update(
                            {key: probability * result[key]
                             for key in ("delivered", "intercepted", "deferred", "undeparted")}
                        )
            gains = [
                daily["deterministic_milp_matched_hours"][d]["intercepted"]
                - daily["greedy"][d]["intercepted"]
                for d in range(len(pair[0].days))
            ]
            for metric in ("delivered", "intercepted", "deferred", "undeparted"):
                rows.append({
                    "split": split,
                    "information": "revealed" if revealed else "distribution",
                    "baseline": "greedy",
                    "policy": "deterministic_milp_matched_hours",
                    "checkpoint_hours": hours["deterministic_milp_matched_hours"],
                    "hours_match_greedy": abs(hours["deterministic_milp_matched_hours"]
                                              - hours["greedy"]) <= 1e-9,
                    "outcome": metric,
                    "greedy_mean": mean(row[metric] for row in daily["greedy"]),
                    "policy_mean": mean(row[metric]
                                         for row in daily["deterministic_milp_matched_hours"]),
                    "interception_gain_over_greedy": mean(gains) if metric == "intercepted" else None,
                    "interception_gain_ci95": interval(gains, seed)[1:]
                    if metric == "intercepted" else None,
                })
    return rows


def flow_accounting(mass, choices, utilities, accounts, revealed):
    components = Counter()
    rich_choices = observed_choices(utilities, mass, revealed)
    expected_utility = sum(p*utilities[i][rich_choices[i]] for i,p in mass.items())
    rich_components = Counter()
    for i,p in mass.items():
        for k,v in accounts[i][choices[i]].items():
            components[k] += p*v
        choice = rich_choices[i]
        rich = accounts[i][choice].copy()
        if (utilities[i][choice] if revealed else expected_utility) <= 0:
            rich.update(delivered=0., intercepted=0., deferred=0., undeparted=rich["supply"])
        for k in ("supply", "delivered", "intercepted", "deferred", "undeparted"):
            rich_components["utility_follower_"+k] += p*rich[k]
    return components, rich_components


def policy_rows(split, pair, local, values, matrix, accounts, utilities, revealed, cfg, args, fit, oracle):
    plans = fit.plans
    measured = []
    score_rows = {}
    for name, mass in local.items():
        decision = matrix if name == "hindsight_unattainable" else fit.matrices
        choices = observed_choices(decision, mass, revealed)
        flows = [sum(p*values[i][choices[i]][d] for i,p in mass.items())
                 for d in range(len(pair[0].days))]
        score_rows[name] = flows
    for name, mass in local.items():
        decision = matrix if name == "hindsight_unattainable" else fit.matrices
        choices = observed_choices(decision, mass, revealed)
        flows = score_rows[name]
        gains = [g-f for g,f in zip(score_rows["greedy"], flows)]
        payoffs = utilities if name == "hindsight_unattainable" else fit.utilities
        components, rich_components = flow_accounting(mass, choices, payoffs, accounts, revealed)
        row = dict(split=split, information="revealed" if revealed else "distribution",
                   policy=name, throughput=mean(flows), gain_over_greedy=mean(gains),
                   throughput_ci95=interval(flows, args.seed)[1:],
                   gain_ci95=interval(gains, args.seed)[1:],
                   tail_cvar=upper_tail(flows, [1/len(flows)]*len(flows), cfg["tail_alpha"]),
                   checkpoint_hours=sum(p*len(plans[i]) for i,p in mass.items()), **components,
                   **rich_components)
        status, gap, seconds = "baseline", None, None
        if name == "deterministic_milp":
            status = fit.solver["status"]
            gap = fit.solver["absolute_gap"]
            seconds = fit.solver["solve_seconds"]
        elif name in fit.seconds or name == "hindsight_unattainable":
            status = "optimal" if fit.complete else "restricted"
            gap = 0. if fit.complete else None
            if name == "hindsight_unattainable":
                game, hidden_seconds, pure_seconds = oracle
                seconds = pure_seconds if revealed else hidden_seconds
                if fit.complete and not revealed:
                    gap = max(0., game["upper"]-game["lower"])
            else:
                seconds = fit.seconds[name]
                if name == "mixed":
                    gap = max(0., fit.game["upper"]-fit.game["lower"])
                    status = "optimal" if gap <= 1e-8 else "restricted"
        row.update(solver_status=status, fit_gap=gap, solve_seconds=seconds)
        measured.append(row)
    return measured


def evaluate_split(split, pair, reduced_pair, fit, cfg, args):
    plans = fit.plans
    local = fit.policies.copy()
    hindsight, oracle_seconds, oracle_pure_seconds = None, None, None
    if split.endswith("test"):
        oracle_matrix = [[s.mean(p) for s in reduced_pair] for p in plans]
        start = perf_counter()
        hindsight = solve_game(oracle_matrix)
        oracle_seconds = perf_counter()-start
        local["hindsight_unattainable"] = {i: x for i, x in hindsight["mass"].items() if x > 0}
    active = set().union(*local.values())
    values = {i: [s.flows(plans[i]) for s in pair] for i in active}
    matrix = [[mean(v) for v in values[i]] if i in active else [0.] * len(pair) for i in range(len(plans))]
    if split.endswith("test"):
        start = perf_counter()
        pure = min(range(len(plans)), key=lambda i: max(oracle_matrix[i]))
        oracle_pure_seconds = perf_counter()-start
        if pure not in active:
            values[pure] = [s.flows(plans[pure]) for s in pair]
            matrix[pure] = list(map(mean, values[pure]))
    accounts = {i: [ledger(s, plans[i], cfg) for s in pair] for i in values}
    utilities = [[contract_utility(item, cfg) for item in accounts[i]]
                 if i in accounts else [0.] * len(pair) for i in range(len(plans))]
    measured = []
    for revealed in (False, True):
        if revealed and split.endswith("test"):
            local["hindsight_unattainable"] = {pure: 1.}
        measured.extend(policy_rows(split, pair, local, values, matrix, accounts, utilities, revealed,
                                    cfg, args, fit, (hindsight, oracle_seconds, oracle_pure_seconds)))
    return measured, matrix, hindsight


def sensitivity_report(full, cfg, fit, curves, measured):
    plans, policies = fit.plans, fit.policies
    sensitivity = {}
    for factor in cfg["alternate_factors"]:
        pair = [Sample(s.days, factor) for s in full["shifted_test"]]
        sensitivity[factor] = {name: sum(p*pair[response(fit.matrices,mass)].mean(plans[i]) for i,p in mass.items())
                               for name,mass in policies.items()}
    for row in measured:
        comparable = row["split"] == "shifted_test" and row["information"] == "distribution"
        for factor, scores in sensitivity.items():
            row[f"throughput_factor_{factor}"] = scores.get(row["policy"]) if comparable else None
        curve = curves.get(row["policy"]) if comparable else None
        row["learning_first_quarter"] = mean(curve[:len(curve)//4]) if curve else None
        row["learning_last_quarter"] = mean(curve[-(len(curve)//4):]) if curve else None
    return sensitivity


def shares(row, baseline):
    reduction = baseline["delivered"]-row["delivered"]
    parts = {k:(row[k]-baseline[k])/reduction if reduction>1e-9 else None
             for k in ("intercepted","deferred","undeparted")}
    return dict(delivery_reduction=reduction,**{k+"_share":v for k,v in parts.items()},
                gain_per_checkpoint_hour=reduction/row["checkpoint_hours"] if row["checkpoint_hours"] else None)


def inspection_sweep(pair,fit,cfg):
    rows = []
    for rate in cfg["processing_sweep"]:
        for probability in cfg["detection_sweep"]:
            settings = dict(cfg,processing_per_crew_hour=rate,detection_probability=probability,carry_over=False)
            totals = {}
            cache = {}
            for name,mass in fit.policies.items():
                j = response(fit.matrices,mass)
                total = Counter()
                for i,p in mass.items():
                    if (i,j) not in cache:
                        cache[i,j] = ledger(pair[j],fit.plans[i],settings)
                    total.update({k:p*v for k,v in cache[i,j].items()})
                total["checkpoint_hours"] = sum(p*len(fit.plans[i]) for i,p in mass.items())
                totals[name] = total
            for name,total in totals.items():
                rank = 1+sum(v["delivered"]<total["delivered"]-1e-9 for v in totals.values())
                rows.append(dict(policy=name,processing=rate,detection=probability,rank=rank,
                                 **total,**shares(total,totals["none"])))
    return rows


def replication(args, cfg, rules, graph, fit):
    comparisons = []
    for offset in cfg["validation_seed_offsets"]:
        seed = args.seed+offset
        pair = [samples(graph,rules,args.test,f"{seed}:replicate",True,args.factor,tuple(profile))[0]
                for profile in cfg["demand_profiles"]]
        scores = {}
        for name in ("centrality","deterministic_milp","mixed","robust_cvar"):
            mass = fit.policies[name]
            sample = pair[response(fit.matrices,mass)]
            scores[name] = [sum(p*v for p,v in zip(mass.values(),day)) for day in
                            zip(*(sample.flows(fit.plans[i]) for i in mass))]
        diff = [m-c for m,c in zip(scores["deterministic_milp"],scores["centrality"])]
        comparisons.append(dict(seed=seed, centrality_gain=mean(diff), ci95=interval(diff,seed)[1:]))
    return dict(heldout=comparisons, centrality_wins=sum(x["centrality_gain"]>1e-9 for x in comparisons),
                milp_wins=sum(x["centrality_gain"] < -1e-9 for x in comparisons))


def frontier(args, cfg, rules, small, full):
    rows = []
    solutions = {}
    for budget in cfg["frontier_budgets"]:
        for cap in cfg["frontier_caps"]:
            effective = (budget,cap)
            if effective not in solutions:
                scoped = replace(rules,budget=budget,delay_cap=cap)
                pool,complete = schedules(scoped,args.seed,cfg["schedule_limit"],[frozenset()])
                def training_cost(plan):
                    return max(s.mean(plan) for s in small["train"])
                plan = min(pool,key=training_cost)
                j = max(range(len(small["train"])),key=lambda j:small["train"][j].mean(plan))
                sample = full["shifted_test"][j]
                totals = ledger(sample,plan,cfg)
                intervals = {}
                for metric in ("delivered","deferred","intercepted","civilian_delay"):
                    days = [ledger(Sample((day,),sample.factor),plan,cfg)[metric] for day in sample.days]
                    intervals[metric+"_ci95"] = interval(days,args.seed)[1:]
                solutions[effective] = dict(status="optimal" if complete else "restricted",
                    checkpoint_hours=len(plan), **totals, **intervals)
            rows.append(dict(budget=budget, delay_cap=cap, **solutions[effective]))
    return rows


def shift_sweep(args,cfg,rules,graph,fit):
    rows = []
    for level in cfg["shift_levels"]:
        pair = [samples(graph,rules,args.test,f"{args.seed}:sweep",True,args.factor,
                        tuple(profile),level)[0] for profile in cfg["demand_profiles"]]
        for name,mass in fit.policies.items():
            sample = pair[response(fit.matrices,mass)]
            values = [sum(p*v for p,v in zip(mass.values(),day)) for day in
                      zip(*(sample.flows(fit.plans[i]) for i in mass))]
            rows.append(dict(level=level,policy=name,throughput=mean(values),ci95=interval(values,args.seed)[1:]))
    return rows


def study(args: argparse.Namespace) -> dict:
    cfg = json.loads((DATA / "research.json").read_text())
    cfg["carry_over"] = args.carry_over
    graph = load()
    rules = planning(graph, args.planner, args.slots, args.budget, 1, args.large)
    if args.large:
        cfg["schedule_limit"] = config()["large"]["pool_limit"]
    cap = cfg["delay_cap_minutes"] if args.delay_cap is None else args.delay_cap
    arrivals = cfg["hourly_civilian_arrivals"]
    peak = tuple(arrivals[t%len(arrivals)]*cfg["minutes_per_arrival"] for t in range(args.slots))
    rules = replace(rules, delay_per_slot=peak,delay_cap=None if args.no_delay_cap else cap)
    full, small, errors = build_splits(args, cfg, rules, graph)
    fit = fit_policies(args, cfg, rules, graph, small)
    measured, proofs, curves = [], {}, {}
    for split, pair in full.items():
        rows, matrix, hindsight = evaluate_split(split, pair, small[split], fit, cfg, args)
        measured.extend(rows)
        if split == "shifted_test":
            for name, mass in fit.policies.items():
                curves[name] = learn(fit.matrices, matrix, mass, cfg["learning_rounds"], cfg["learning_prior"], args.seed)
    for name, source in [("training", fit.game), ("shifted_hindsight", hindsight)]:
        lower = source["lower"] if fit.complete or name == "training" else 0.
        proofs[name] = dict(lower=lower, upper=source["upper"], gap=max(0.,source["upper"]-lower),
                            stopping=source.get("stopping","pool_gap_tolerance"),
                            pool_lower=source["lower"], iterations=source["iterations"])
    sensitivity = sensitivity_report(full, cfg, fit, curves, measured)
    training_scores = {(r["policy"],r["information"]):r["throughput"] for r in measured if r["split"]=="train"}
    baselines = {(r["split"],r["information"]):r for r in measured if r["policy"]=="none"}
    for row in measured:
        key = row["policy"],row["information"]
        row["test_minus_train"] = row["throughput"]-training_scores[key] if key in training_scores else None
        baseline = baselines[row["split"],row["information"]]
        row.update(shares(row,baseline))
        row["paired_test_minus_train"] = (row["test_minus_train"]-baseline["throughput"]+
            training_scores["none",row["information"]]) if key in training_scores else None
    return dict(assumptions=dict(fixture=config(), study=cfg, args={k:v for k,v in vars(args).items()
                if k != "output"}, effective_budget=rules.budget), measured=measured, proofs=proofs,
                mean_relative_flow_error=mean(errors), complete_schedule_set=fit.complete, schedules=len(fit.plans),
                mixed_support=[dict(schedule=sorted(fit.plans[i]), probability=p) for i,p in fit.policies["mixed"].items()],
                training_milp=fit.solver, sensitivity=sensitivity, selected_alpha=fit.selected_alpha,
                matched_hours=matched_report(full,fit,cfg),
                matched_interception_vs_greedy=matched_interception_report(full,fit,cfg,args.seed),
                primary_metric="delivered",inspection_sweep=inspection_sweep(full["shifted_test"],fit,cfg),
                heldout_replication=replication(args,cfg,rules,graph,fit),
                shift_sweep=shift_sweep(args,cfg,rules,graph,fit), frontier=frontier(args,cfg,rules,small,full),
                learning_shifted_expected_throughput=curves,
                learning_retention=retention(curves,cfg["retention_fraction"]),
                learning_round_intervals=learning_intervals(fit,matrix,cfg,args.seed),
                osm_fixture_scaling=road_check(cfg["road_check"],args.seed),
                synthetic_subdivision=subdivision_check(full["train"][0].days[0][0], cfg["subdivision_segments"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("."))
    parser.add_argument("--planner", choices=("single", "coalition"), default="single")
    parser.add_argument("--large", action="store_true")
    parser.add_argument("--carry-over", action="store_true")
    parser.add_argument("--slots", type=int)
    parser.add_argument("--budget", type=int)
    parser.add_argument("--factor", type=float, default=.3)
    limits = parser.add_mutually_exclusive_group()
    limits.add_argument("--delay-cap", type=float)
    limits.add_argument("--no-delay-cap", action="store_true")
    parser.add_argument("--train", type=int, default=40)
    parser.add_argument("--test", type=int, default=8)
    parser.add_argument("--time-limit", type=float, default=10)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    preset = config()["large"] if args.large else dict(slots=4,budget=4)
    for key in ("slots","budget","delay_cap"):
        if getattr(args,key) is None:
            setattr(args,key,preset.get(key))
    if min(args.train, args.test, args.slots) < 1:
        parser.error("Counts must be positive")
    result = study(args)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/"results.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    with (args.output/"results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=result["measured"][0])
        writer.writeheader()
        writer.writerows(result["measured"])
    with (args.output/"frontier.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=result["frontier"][0])
        writer.writeheader()
        writer.writerows(result["frontier"])


if __name__ == "__main__":
    main()
