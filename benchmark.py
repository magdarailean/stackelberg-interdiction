import argparse
import json
from pathlib import Path

from checkpoints.defender import Rules
from checkpoints.evaluate import Sample
from checkpoints.experiment import experiment
from checkpoints.network import synthetic_network


def run(rows: int, columns: int, budget: int, seed: int, train_count: int,
        test_count: int, time_limit: float, slots: int = 4, crews: int = 1,
        shift: int = 1, factor: float = 0.3) -> dict:
    sites, make = synthetic_network(rows, columns)
    rules = Rules((sites,) * slots, budget, crews, shift)
    seeds = iter(range(seed, seed + slots*(train_count+2*test_count)))

    def sample(count: int, shifted: bool = False) -> Sample:
        return Sample(tuple(tuple(make(next(seeds), shifted) for _ in range(slots))
                            for _ in range(count)), factor)

    train = sample(train_count)
    tests = {"nominal_test": sample(test_count), "shifted_test": sample(test_count, True)}
    return dict(seed=seed, grid=[rows, columns], slots=slots, crews=crews, shift=shift,
                budget_checkpoint_hours=budget, factor=factor, candidate_count=len(sites),
                **experiment(train, tests, rules, train.days[0][0].graph, seed, time_limit))


def main() -> None:
    parser = argparse.ArgumentParser(description='Grid benchmark for time-indexed checkpoint schedules.')
    parser.add_argument("--network", choices=("grid", "regional", "corridor"), default="grid")
    parser.add_argument("--corridor-dir", type=Path, default=Path("data/corridor"))
    parser.add_argument("--planner", choices=("single", "coalition"), default="single")
    parser.add_argument("--rows", type=int, default=6)
    parser.add_argument("--columns", type=int, default=8)
    parser.add_argument("--budget", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train", type=int, default=4)
    parser.add_argument("--test", type=int, default=8, help="Scenario count per test split")
    parser.add_argument("--time-limit", type=float, default=10, help="SCIP solve limit in seconds")
    parser.add_argument("--slots", type=int, default=4)
    parser.add_argument("--crews", type=int, default=1)
    parser.add_argument("--shift", type=int, default=1)
    parser.add_argument("--factor", type=float, default=0.3)
    args = parser.parse_args()
    if args.network == "corridor":
        from checkpoints.snapshot import corridor_report
        print(json.dumps(corridor_report(args.corridor_dir, args.seed),indent=2))
        return
    if min(args.rows, args.columns) < 2 or min(args.train, args.test) < 1:
        parser.error("The grid needs at least two rows and columns, and each split needs a scenario.")
    if args.budget < 0 or not 0 < args.time_limit < float("inf"):
        parser.error("Budget must be nonnegative and the time limit must be finite and positive.")
    if args.network == "regional":
        from checkpoints.geo import regional
        print(json.dumps(regional(args), indent=2))
        return
    print(json.dumps(run(args.rows, args.columns, args.budget, args.seed,
                         args.train, args.test, args.time_limit, args.slots,
                         args.crews, args.shift, args.factor), indent=2))


if __name__ == "__main__":
    main()
