"""Serve the Frontier Command browser UI on the checkpoint planning model."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import mean
from time import perf_counter
from urllib.parse import urlparse
import json
import os
import webbrowser

from checkpoints.defender import Rules, centrality, greedy, random_schedule
from checkpoints.evaluate import Sample, interval
from checkpoints.milp import optimize
from checkpoints.network import synthetic_network

ROOT = Path(__file__).resolve().parent
UI = ROOT / "ui"
HOST, PORT = "127.0.0.1", int(os.environ.get("FRONTIER_PORT", "8765"))
ROWS, COLUMNS, SLOTS, DEFAULT_BUDGET = 6, 8, 6, 4
CAPACITY_FACTOR = 0.3


def get_sites():
    """Return the directed edge candidates used by the time-indexed model."""
    return synthetic_network(ROWS, COLUMNS)[0]


def site_data(sites):
    return [{"id": f"site-{i + 1}", "number": i + 1,
             "row": edge[0] // COLUMNS, "hours": 1, "edge": list(edge)}
            for i, edge in enumerate(sites)]


def build_sample(make, count, seed, shifted):
    days = tuple(
        tuple(make(seed + day * SLOTS + slot, shift=shifted) for slot in range(SLOTS))
        for day in range(count)
    )
    return Sample(days, factor=CAPACITY_FACTOR)


def manual_plan(data, site_ids, rules):
    schedule = data.get("schedule")
    if schedule is not None:
        if not isinstance(schedule, list):
            raise ValueError("The schedule must be a list of assignments.")
        plan = set()
        for item in schedule:
            if (not isinstance(item, list) or len(item) != 2
                    or not isinstance(item[0], int) or isinstance(item[0], bool)
                    or not isinstance(item[1], str) or item[1] not in site_ids):
                raise ValueError("The selected schedule is invalid.")
            plan.add((item[0], site_ids[item[1]]))
        if len(plan) != len(schedule):
            raise ValueError("The schedule contains a duplicate assignment.")
    else:
        selected = data.get("selected_ids", [])
        if (not isinstance(selected, list) or any(not isinstance(site_id, str) for site_id in selected)
                or len(set(selected)) != len(selected)):
            raise ValueError("The site selection is invalid.")
        if any(site_id not in site_ids for site_id in selected):
            raise ValueError("The selection contains an unknown site.")
        if len(selected) > SLOTS:
            raise ValueError("The schedule cannot exceed the available time slots.")
        plan = {(slot, site_ids[site_id]) for slot, site_id in enumerate(selected)}
    frozen = frozenset(plan)
    if not rules.feasible(frozen):
        raise ValueError("The schedule exceeds the budget, crew limit, or shift constraints.")
    return frozen


def policy_score(sample, plans, seed, greedy_flows):
    baseline = sample.flows(frozenset())
    flows = [mean(row) for row in zip(*(sample.flows(plan) for plan in plans))]
    gains = [reference - value for reference, value in zip(greedy_flows, flows)]
    return {
        "mean_delivered": mean(flows),
        "mean_reduction": mean(baseline) - mean(flows),
        "mean_checkpoint_hours": mean(len(plan) for plan in plans),
        "mean_improvement_over_greedy": mean(gains),
        "delivered_ci95": interval(flows, seed)[1:],
        "gain_ci95": interval(gains, seed)[1:],
        "worst_tail": mean(sorted(flows, reverse=True)[:max(1, (len(flows) + 9) // 10)]),
    }


def simulate(data):
    sites = get_sites()
    site_ids = {f"site-{i + 1}": edge for i, edge in enumerate(sites)}
    budget = int(data.get("budget", DEFAULT_BUDGET))
    seed = int(data.get("seed", 42))
    train_n = int(data.get("train_count", 4))
    test_n = int(data.get("test_count", 8))
    limit = float(data.get("time_limit", 5))
    if not 0 <= budget <= SLOTS:
        raise ValueError(f"The budget must be between 0 and {SLOTS} hours.")
    if not 1 <= train_n <= 30 or not 1 <= test_n <= 30:
        raise ValueError("Each scenario count must be between 1 and 30.")
    if not 0.2 <= limit <= 30:
        raise ValueError("The solver time limit must be between 0.2 and 30 seconds.")

    rules = Rules((sites,) * SLOTS, budget=budget, crews=1, shift=1)
    manual = manual_plan(data, site_ids, rules)
    _, make = synthetic_network(ROWS, COLUMNS)
    train = build_sample(make, train_n, seed, shifted=False)
    nominal = build_sample(make, test_n, seed + train_n * SLOTS, shifted=False)
    shifted = build_sample(make, test_n, seed + (train_n + test_n) * SLOTS, shifted=True)

    started = perf_counter()
    greedy_plan = greedy(rules, train.mean)
    greedy_seconds = perf_counter() - started
    fitted = optimize(train, rules, limit, incumbent=greedy_plan)
    random_plans = [random_schedule(rules, seed + i) for i in range(20)]
    centrality_plan = centrality(rules, train.days[0][0].graph, seed)
    plans = {
        "none": [frozenset()],
        "manual": [manual],
        "greedy": [greedy_plan],
        "milp": [fitted.plan],
        "centrality": [centrality_plan],
        "random": random_plans,
    }

    splits = {}
    for name, sample in (("train", train), ("nominal_test", nominal),
                         ("shifted_test", shifted)):
        split_plans = dict(plans)
        split_meta = {}
        if name != "train":
            incumbent = min((plan for group in plans.values() for plan in group),
                            key=sample.mean)
            oracle = optimize(sample, rules, limit, incumbent=incumbent)
            split_plans["oracle"] = [oracle.plan]
            split_meta["oracle_solver"] = {
                "status": oracle.status,
                "seconds": oracle.build_seconds + oracle.solve_seconds,
                "bound": oracle.lower,
            }
        reference = sample.flows(greedy_plan)
        splits[name] = {
            "scenario_count": len(sample.days),
            "policies": {
                policy: policy_score(sample, policy_plans, seed, reference)
                for policy, policy_plans in split_plans.items()
            },
            **split_meta,
        }

    ids = {edge: site_id for site_id, edge in site_ids.items()}
    return {
        "seed": seed,
        "budget": budget,
        "selected_hours": len(manual),
        "candidate_sites": site_data(sites),
        "manual_plan": [[slot, ids[edge]] for slot, edge in sorted(manual)],
        "greedy_site_ids": [ids[edge] for _, edge in sorted(greedy_plan)],
        "milp_site_ids": sorted({ids[edge] for _, edge in fitted.plan}),
        "milp_plan": [[slot, ids[edge]] for slot, edge in sorted(fitted.plan)],
        "solver": {
            "status": fitted.status,
            "seconds": fitted.build_seconds + fitted.solve_seconds,
            "bound": fitted.lower,
            "absolute_gap": (None if fitted.lower is None else
                             max(0.0, train.mean(fitted.plan) - fitted.lower)),
            "greedy_seconds": greedy_seconds,
        },
        "model": {
            "slots": SLOTS,
            "crews": rules.crews,
            "minimum_shift": rules.shift,
            "capacity_factor": CAPACITY_FACTOR,
        },
        "splits": splits,
    }


class Handler(BaseHTTPRequestHandler):
    def reply(self, body, mime, status=200):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def json(self, data, status=200):
        self.reply(json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", status)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/config":
            return self.json({"rows": ROWS, "columns": COLUMNS, "slots": SLOTS,
                              "budget": DEFAULT_BUDGET,
                              "sites": site_data(get_sites())})
        assets = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/style.css": ("style.css", "text/css; charset=utf-8"),
            "/assets/map/theater.svg": ("assets/map/theater.svg", "image/svg+xml"),
            "/assets/fonts/DMSans-variable.ttf": ("assets/fonts/DMSans-variable.ttf", "font/ttf"),
            "/assets/fonts/Marcellus-Regular.ttf": ("assets/fonts/Marcellus-Regular.ttf", "font/ttf"),
        }
        if path not in assets:
            return self.json({"error": "Page not found."}, 404)
        name, mime = assets[path]
        self.reply((UI / name).read_bytes(), mime)

    def do_POST(self):
        if urlparse(self.path).path != "/api/simulate":
            return self.json({"error": "Unknown API route."}, 404)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 100_000:
                raise ValueError("The request size is invalid.")
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("The request must contain a JSON object.")
            self.json(simulate(payload))
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            self.json({"error": str(error)}, 400)
        except Exception as error:
            self.json({"error": "Simulation error: " + str(error)}, 500)

    def log_message(self, fmt, *args):
        print("[UI] " + (fmt % args))


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print(f"Game URL: {url}  (Ctrl+C to stop)")
    try:
        webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
