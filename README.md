# Stackelberg checkpoint benchmark

For the real OSM corridor data recipe and its current status, see [docs/OSM_CORRIDOR.md](docs/OSM_CORRIDOR.md). For research framing, synthetic-data limits, and measured-versus-assumed quantities, see [docs/RISK_AND_LIMITS.md](docs/RISK_AND_LIMITS.md).

The defender commits to one binary site-by-hour schedule across all sampled days. A follower observes the schedule and maximizes delivered flow on each hourly directed graph. Lower daily delivery is better.

## Run with Python 3.11 (PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest -v
python -m checkpoints.run
python -m checkpoints.study --output results
python benchmark.py
python benchmark.py --rows 60 --columns 60 --train 2 --test 2 --time-limit 15
python -m checkpoints.separating --output separating.json
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
- The base benchmark's lost delivery is foregone modeled throughput, not interception. The optional research study adds assumed inspection capacity/detection and separate deferral/civilian-delay accounting; those values are synthetic model outputs, not observations.

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

The research study writes `matched_interception_vs_greedy` and `interception_first_validation` to `results.json`. The first is the existing delivered-flow MILP scored on interception as a secondary outcome. The second fits a separate interception-first MILP: it maximizes the accounting model's expected interceptions, with each sampled max-flow enforced by lazily separated min-cut constraints. SCIP's relaxation bound and the evaluated schedule give an upper and lower bound. It compares against greedy-on-interception at equal checkpoint-hours across 10 fixed seeds and nominal/shifted held-out scenario mixes, with paired 95% intervals and seed win rates. Inspection rate and detection probability regimes are in `data/research.json`. Interception is calculated from synthetic inspection capacity and an assumed detection probability; it is not an observed seizure rate. Deferral and delivered flow remain separate outcomes. A positive mean with an interval containing zero is weak evidence and must not be presented as a reliable advantage.

The same study includes a finite-schedule Bayesian general-sum DOBSS MILP. Follower types are origin-share profiles with priors; each chooses between adaptive-flow departure and deferral after observing the defender's schedule distribution. The defender payoff is modeled interception minus civilian-delay cost, and follower payoff is delivered flow minus attempt cost and expected interception loss. `results.json` reports the DOBSS value, best pure value, their difference (value of randomization), bounds, and solve time. The pool is enumerated when feasible and otherwise the output is explicitly restricted to the generated schedule pool. The DOBSS construction follows [Paruchuri et al. (AAMAS 2008)](https://u.cs.biu.ac.il/~krauss/data/articles/AAMAS_2008.pdf); its finite-game implementation is cross-checked against enumerated multiple-LP solutions.

The separating benchmark runs four parameter combinations on a 60×60 fictional grid for seeds 42–51. Two use ordinary grid candidates and two add a parallel branch with a pair of serial candidates. Both policies use the same checkpoint-hours and train on the same two days per seed. Nominal and shifted test draws are separate. The JSON retains every paired outcome, solve time, and bound. DOBSS tests a restricted schedule pool and an interception-based response candidate. Its restricted gap does not certify an optimum for the full game.

Both CLIs accept `--network corridor` for geometry verification and run a ten-seed interception comparison on the recognized fictional XML fixture. The loader checks GraphML SHA-256 and metadata counts, preserves direction and parallel edges, and reports crossing status as unverified. Use the [snapshot recipe and offline fixture commands](docs/OSM_CORRIDOR.md).

The serial-pair case beat greedy on all 10 seeds at two checkpoint-hours. Mean modeled interception gain was 4.20 on nominal days and 5.46 on shifted days. The other three cases tied. The [measured-versus-assumed table](docs/RISK_AND_LIMITS.md#measured-versus-assumed) gives paired intervals, runtimes, and restricted DOBSS results.

## Offline regional fixture

The regional mode uses an invented two-lane diagram with jurisdictions A, B and C. All inputs are generated locally. The snapshot contains no OpenStreetMap or Natural Earth data. OpenStreetMap distributes its database under the ODbL; the fixture has no OSM-derived geometry.

```powershell
python -m scripts.build_network
python benchmark.py --network regional --planner single > regional.json
python benchmark.py --network regional --planner coalition
python -m pip install -r requirements-plot.txt
python -m scripts.plot_map regional.json fixture.png
```

The benchmark loads the frozen GraphML and checks its metadata and input fingerprints. Rebuild after editing fixture inputs. The scaling rows in its JSON report use the configured candidate/slot/day combinations.

- Fictional node coordinates use diagram units. Gate coordinates in the CSV are blank; directed node pairs identify the locations.
- Only listed directional gates connect jurisdictions. Gate capacity is capped by the adjoining modeled road capacity.
- Primary segments have capacity 16 and speed 60 km/h; secondary segments have capacity 12 and speed 45 km/h.
- Every detailed segment represents 900 m. Travel time is descriptive and does not constrain crew relocation.
- Each independent hourly segment closure has probability 2% for primary or 4% for secondary, doubled under shift.
- Total hourly supply is a uniform integer from 12 to 26, split equally between the two origins or 75/25 under shift.
- Each destination independently draws integer demand uniformly from 8 to 15.
- Days have equal probability independent of supply. Train, tune, nominal test and shifted test use distinct deterministic seed streams.
- Single mode has two A crews. Coalition has two A crews and one each for B and C. Pools replace the grid crew cap, and only the local listed authority may staff a site.
- After applying hourly closures, a directed one-in/one-out chain takes its minimum capacity; parallel alternatives add their capacities. Sites, crossing endpoints and zones remain explicit, and a bypass cannot merge into a controllable edge.
- MILPs use the reduced hourly graphs. All policy delivery metrics use the paired detailed graphs, including the training metrics.
- The reduction check reports mean absolute relative error over hourly no-deployment flows, with denominator one when detailed flow is zero. The test also compares every single-site deployment.
- The scaling table uses prefixes of the sorted fictional candidate list and reports solver time separately from build time. Its results describe this small fixture only.

Edit `data/fixture.json` for class parameters, zone references, draw ranges, shift, resource pools, scaling sizes and the default 5% error tolerance. The two CSV files supply candidate permissions and hypothetical gate capacities.

## Browser strategy game

The local browser interface uses the same time-indexed `checkpoints` model as the command-line experiments. It compares a manual one-hour-per-site plan with greedy, centrality, random, MILP, and a clearly labeled unattainable test-set oracle. Every policy uses the same candidate edges, one-crew limit, planning horizon, checkpoint-hour budget, and scenario samples. The interface reports modeled delivered flow; it does not represent seizures or real traffic.

The game map shows Romania, Moldova, Odesa, and the Black Sea for orientation. Candidate markers and the directed grid used by the optimizer are fictional and synthetic; the map does not supply road or border data.

Create the Python environment as above, then start the web app from the repository root:

```powershell
.\launch_web.ps1
```

You can also double-click `Start Frontier Command.bat`. Keep its PowerShell window open while playing; stop the local server with Ctrl+C. The app is served at http://127.0.0.1:8765 and saves campaign progress in that browser on the same computer.
