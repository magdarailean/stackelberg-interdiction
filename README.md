# Stackelberg checkpoint benchmark

The defender commits to one binary site-by-hour schedule across all sampled days. A follower observes the schedule and maximizes delivered flow on each hourly directed graph. Lower daily delivery is better.

## Run with Python 3.11 (PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest -v
python -m checkpoints.run
python benchmark.py
python benchmark.py --rows 60 --columns 60 --train 2 --test 2 --time-limit 15
python benchmark.py --slots 6 --crews 2 --shift 2 --budget 8 --factor 0.5
```

Both experiments emit JSON. The grid uses 4 training days and 8 days per test split by default. The toy uses 30 training days and 20 shifted test days. Both start at seed 42.

## Model assumptions

- Networks are synthetic and flow is divisible, aggregate, and confined to its hour.
- Each site controls one directed edge and consumes one crew-hour per active slot.
- Active capacity is base hourly capacity times a common factor in (0, 1], default 0.3. Closed or absent edges carry zero.
- Every day starts and ends off duty. Each contiguous run at a site must last at least L slots entirely within the horizon.
- Defaults are four one-hour slots, one crew, a four-hour budget, and minimum shift length one.
- Grid crews are interchangeable and can move between any authorized sites at a slot boundary. All candidate sites are authorized throughout the grid experiment.
- Toy authorizations alternate between two three-site sets. Consecutive deployments must have the same upstream node, with an idle slot permitting relocation.
- Each hourly graph supplies its own capacities. Days have equal weight and daily delivery sums independent slot responses.
- Toy hourly supply is uniform integer 12–20, demand 13–21, and each interior edge closes independently with probability 5% in training and 15% in shifted testing.
- The grid independently draws hourly capacities, supply and closures. The shifted split widens per-row supply from 4–8 to 3–9 and adds diagonal links.
- Lost delivery measures foregone modeled throughput. Interception, deferral and civilian delay require additional observations or models.

## Optimization and evaluation

SCIP minimizes the mean daily cut cost. Each day and hour has an independent source-side partition. For an arc crossing its cut, d=1. A noncrossing arc can take d=0. With binary activation x and 0 ≤ z ≤ 1, impose z ≥ d − x. Minimizing fu·d + (1−f)u·z gives 0 off the cut, fu on an active crossing and u on an inactive crossing. At f=1 the z term can be omitted. NetworkX recomputes the returned schedule's objective.

- All policies share the same feasible region. Random averages 20 seeded shuffled feasible fills, conditional on those schedules.
- Centrality fills by unweighted directed edge betweenness on the toy topology or first training grid, sampling up to 32 source nodes.
- Greedy adds a feasible minimum-length block with greatest positive reduction per additional hour. Blocks can overlap to extend runs.
- The unattainable hindsight policy fits one common schedule to each entire test split, warm-started from the best evaluated schedule on that split.
- Each SCIP solve has its own time limit. Feasible and fallback statuses indicate an unproven incumbent. Fallback has no reported proof bound.
- Absolute gap is the nonnegative difference between evaluated incumbent and solver lower bound. Relative gap divides it by the incumbent, with zero for a zero objective.
- Worst-tail delivery averages the highest ceil(10% × day count) daily deliveries, after averaging random schedules within day.
- Approximate 95% percentile intervals resample entire days 2,000 times. Gain over greedy uses paired daily differences; positive means less delivery. Intervals condition on the fitted schedules, including hindsight selection.
