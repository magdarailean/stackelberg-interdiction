from collections import Counter
from statistics import mean

from .game import solve_game
from .risk import risk_mixture


def fixed_hours(indices, matrix, regimes, alpha, contamination):
    payoffs = [matrix[i] for i in indices]
    losses = [[regime[i] for i in indices] for regime in regimes]
    distributions = {
        "deterministic_milp": {min(range(len(indices)),key=lambda j:mean(payoffs[j])):1.},
        "optimized_pure_game": {min(range(len(indices)),key=lambda j:max(payoffs[j])):1.},
        "mixed": solve_game(payoffs)["mass"],
        "robust_cvar":risk_mixture(losses[:1],alpha),
        "worst_case":risk_mixture(losses,0,contamination)}
    return {name:{indices[j]:p for j,p in mass.items() if p>0} for name,mass in distributions.items()}


def matched_fits(plans, policies, matrix, regimes, alpha, contamination):
    fits = {}
    output = {}
    for name in ("none","greedy","centrality","random"):
        hours = Counter()
        for i,p in policies[name].items():
            hours[len(plans[i])] += p
        combined = {}
        for h,weight in hours.items():
            if h not in fits:
                members = [i for i,plan in enumerate(plans) if len(plan)==h]
                fits[h] = fixed_hours(members,matrix,regimes,alpha,contamination)
            for policy,mass in fits[h].items():
                total = combined.setdefault(policy,Counter())
                total.update({i:p*weight for i,p in mass.items()})
        output[name] = combined
    return output
