# Stackelberg interdiction benchmark

This research benchmark compares fixed checkpoint deployments on fictional directed
networks. A single deployment is selected on training scenarios. In each scenario,
an adaptive follower observes the deployment and maximizes delivered flow. A
checkpoint lowers the modeled capacity of one edge for the planning period.

## Run

With Python 3.11 or newer, create a local environment from PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest -v
.\.venv\Scripts\python.exe benchmark.py
.\.venv\Scripts\python.exe benchmark.py --rows 60 --columns 60 --train 2 --test 2 --time-limit 15
```

The CLI emits JSON. It evaluates no deployment, 20 seeded random feasible
deployments, greedy marginal benefit per checkpoint-hour, and the MILP. Every
deployment is subject to the same budget cap. The nominal and shifted test splits
use distinct seeds from training. The shifted split changes supply and adds
links unavailable in the training network. Use a fresh `--seed` for replication.

NetworkX computes follower responses. OR-Tools/SCIP minimizes a weighted sum of
scenario min cuts, using max-flow/min-cut duality. Each scenario has its own cut,
while all cuts share the same deployment decisions. The CLI independently
recomputes the chosen solution's training objective and reports it alongside the
solver's lower bound and absolute gap. A time limit can yield a feasible solution
or a greedy fallback. Model construction time is included in the reported time
and is outside the SCIP solve limit.

Delivery reduction is the difference between maximum flow without checkpoints
and maximum flow with them. It represents foregone delivery in the model.
The benchmark uses generated networks and aggregate synthetic supply, with no
person or vehicle data. Mixed strategies, actual interception, civilian delay,
and multi-period staffing are outside this first model.
