# Stackelberg checkpoint benchmark

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

The research study also writes `matched_interception_vs_greedy` to `results.json`. It compares the deterministic MILP with greedy at the same expected checkpoint-hour allocation on nominal and shifted held-out scenarios, and reports delivered, modeled intercepted, deferred, and undeparted flow separately. The interception estimate assumes synthetic inspection capacity and a configured detection probability; it is not an observed seizure rate. The MILP is still fitted to delivered-flow reduction, so this comparison evaluates interception as a secondary outcome rather than claiming an interception-optimal plan. Paired intervals resample held-out days. The `information` field distinguishes a follower responding to the schedule distribution from one responding after seeing the realized schedule.

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
