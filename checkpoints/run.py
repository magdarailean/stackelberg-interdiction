import argparse
import json

from .defender import Rules
from .evaluate import Sample
from .experiment import experiment
from .network import SITES, toy_graph
from .scenarios import generate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slots", type=int, default=4)
    args = parser.parse_args()
    rules = Rules(tuple(SITES[:3] if t % 2 == 0 else SITES[1:] for t in range(args.slots)),
                  same_origin=True)
    train = Sample(generate(30, 42, 0.05, args.slots))
    test = Sample(generate(20, 43, 0.15, args.slots))
    print(json.dumps(experiment(train, {"shifted_test": test}, rules, toy_graph(), 42, 10), indent=2))


if __name__ == "__main__":
    main()
