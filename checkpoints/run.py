"""Run with python -m checkpoints.run."""
from statistics import mean

from .defender import Plan, feasible_plans, greedy, random_feasible
from .evaluate import daily_flow, interval
from .network import toy_graph
from .scenarios import generate

def main() -> None:
    """Fit on 30 days and compare frozen policies on 20 shifted days."""
    seed = 42
    graph = toy_graph()
    train = generate(30, seed, 0.05)
    test = generate(20, seed + 1, 0.15)
    plans = feasible_plans()

    def score(plan: Plan) -> float:
        """Mean daily delivery on training scenarios."""
        return mean(daily_flow(graph, day, plan) for day in train)

    fitted = greedy(plans, score)
    observations = {"none": [], "random": [], "greedy": []}
    for i, day in enumerate(test):
        draw = random_feasible(plans, seed + 100 + i)
        for name, schedule in (("none", frozenset()), ("random", draw), ("greedy", fitted)):
            observations[name].append(daily_flow(graph, day, schedule))
    print("policy    mean delivery [95% CI]     gain over greedy [95% CI]")
    for name, values in observations.items():
        gain = [g - v for g, v in zip(observations["greedy"], values)]
        avg, lo, hi = interval(values, seed)
        diff, lower, upper = interval(gain, seed)
        print(f"{name:8} {avg:6.2f} [{lo:.2f}, {hi:.2f}]     "
              f"{diff:6.2f} [{lower:.2f}, {upper:.2f}]")

if __name__ == "__main__":
    main()
