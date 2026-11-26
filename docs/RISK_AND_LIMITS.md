# Risk framing and limits

## Research framing

This is a **synthetic preparedness simulator**, not an intelligence product or a claim about real illicit traffic. The contingency framing asks how a checkpoint-planning policy behaves under hypothetical post-conflict or ceasefire-related changes in network conditions and adversary behavior. Frontex's [Annual Risk Analysis 2024/2025](https://prd.frontex.europa.eu/wp-content/uploads/annual-risk-analysis-2024-2025.pdf) discusses a potential post-war firearms-smuggling risk. GI-TOC's [Tomorrow's Fire](https://globalinitiative.net/analysis/future-ukraine-russia-conflict-europe-illicit-arms-market/) and [Crime and Peace](https://globalinitiative.net/analysis/the-future-of-organized-crime-beyond-the-russo-ukrainian-war/) use scenarios to consider possible organized-crime and illicit-arms-market effects. These sources motivate scenario analysis; they do **not** establish actual routes, shipment volumes, crossing use, or current threat levels for this simulator.

## Scope and safeguards

- The modeled system is road infrastructure and synthetic aggregate flow. It has no person, vehicle, identity, or case-level records.
- The simulator does not rank people or predict whether a person will commit a crime. Its decisions allocate hypothetical checkpoint-hours to hypothetical road links.
- This is a scope statement, **not** a legal compliance assessment. AI Act Article 5(1)(d) prohibits a specified kind of criminal-offence risk assessment of natural persons based solely on profiling or personality traits/characteristics, with a stated exception tied to human assessment based on objective, verifiable facts. This project does not implement individual assessment; that alone does not establish compliance with the AI Act or other law. See the [official EUR-Lex text](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng).
- Candidate checkpoint sites are hypothetical. Any crossing's operational accessibility, legal authority, inspection capacity, staffing, and safety status remain **unverified** until independently curated by the responsible authorities.
- VIIRS/night-light data were skipped. No night-light values are included and no inference about illicit origins is made from lights or population proxies.

## Measured versus assumed

| Quantity or claim | Measured by the current code/run | Assumed, synthetic, or unverified |
| --- | --- | --- |
| Road topology in current checked-in study | 28 directed edges in the fictional regional fixture; the grid-scale run is synthetic | No real corridor graph has yet been built in this checkout. The OSM build recipe is in [OSM_CORRIDOR.md](OSM_CORRIDOR.md). |
| Road length, direction, class | Parsed from OSM geometry/tags if the PBF recipe is run | OSM tags may be incomplete; class-default speeds are modeling defaults, not observed travel speeds. |
| Road capacity and closures | Computed in the simulator from configured parameters | Synthetic capacities, closure probabilities, scenario shifts, origins, supplies, and destination demands; not observed traffic or illicit shipments. |
| Candidate checkpoints and border crossings | Nothing operationally verified | Candidate sites are hypothetical; crossing status and jurisdictional permission are unverified. |
| Delivered flow | NetworkX max-flow value under the modeled graph and capacities | A modeled capacity outcome, not measured real movement. A reduction in delivery alone does not prove seizure or interception. |
| Intercepted, deferred, and undeparted quantities | Ledger accounting under configured detection probability, processing capacity, and flow; kept as separate quantities | Detection, inspection capacity, attempt costs, and loss values are assumptions. These values are not real seizures or observed delays. |
| Interception-first comparison | 10 paired seeds, same checkpoint-hours, synthetic held-out scenarios. Baseline nominal mean optimizer-minus-greedy gain: **−0.0221**, 95% CI **[−0.0663, 0]**, win rate **0/10**. Baseline shifted mean: **+0.0239**, CI **[0, +0.0717]**, win rate **1/10**. High-detection and high-capacity runs had zero gain. Solver gaps were zero on these small fixture instances. | One exploratory synthetic regime had a slight positive mean under shifted tests, but its interval touches zero and only one seed won. This is not a reliable advantage over greedy and does not support the hypothesis that optimization consistently beats greedy. No corridor result exists. Reproduce the comparison with the research study command in the README. |
| DOBSS solver verification | 20 seeded random tiny games match multiple-LP values within `1e-6`; a constructed game has mixed value **0.5** versus best pure **0.0** | Those checks validate the finite-game implementation, not the realism of utility inputs. |
| Value of randomization on the main study family | DOBSS mixed value **1.505625**, best-pure value **1.505625**, measured difference approximately **0**; 38 feasible schedules enumerated; solve time **0.014 s**, optimality gap **0** | Type priors and payoff coefficients are declared assumptions in `data/research.json`. The main family did not benefit from randomization. |
| Runtime and optimality | The separating suite used at least 10,711 directed edges per hourly graph. See the runtime and gap table below. | Synthetic-grid speed does not establish runtime on a real 10,000-edge corridor. |
| Corridor snapshot verification | Both CLIs verified the offline OSM fixture manifest, SHA-256, four nodes and five directed edges. The tamper test rejected modified GraphML. | Real snapshot download, candidate siting, corridor optimization and corridor flow reduction remain unverified. The CLI corridor mode checks geometry and integrity only. |
| VIIRS prior | Not used | Skipped; no conclusions based on VIIRS or nighttime lights. |

### Separating experiment

The grid is 60×60, with three candidate sites in one slot. Each case uses seeds 42–51 with two nominal training days, two independent nominal test days and two shifted test days. A separate shifted training stream supplies the second DOBSS type. The two types have equal prior probability. Inspection uses the shared aggregate ledger. Fixed-hours comparisons use one or two feasible hours as shown. The serial layout adds two parallel fictional branches, with two candidates sharing one branch in series. The four declared parameter combinations are a targeted sweep, not a full factorial experiment.

| Layout and settings (budget / crews / capacity factor / detection / rate) | Nominal paired gain [95% CI] | Shifted paired gain [95% CI] | Wins per split | Interception mean time / max gap | DOBSS mean time / max pool gap | Mean restricted-pool mixed minus pure |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Grid low rate (2 / 2 / .3 / .25 / 3) | 0 [0, 0] | 0 [0, 0] | 0/10 | 1.40 s / 0 | 0.007 s / 0 | 0 |
| Grid high rate (2 / 2 / .3 / .60 / 240) | 0 [0, 0] | 0 [0, 0] | 0/10 | 2.59 s / 0 | 0.049 s / 0 | 28.67 |
| Serial pair (2 / 2 / .3 / .60 / 240) | 4.20 [4.20, 4.20] | 5.46 [5.46, 5.46] | 10/10 | 3.53 s / 0 | 0.016 s / 0.0024 | 39.01 |
| Serial pair, single crew (2 / 1 / .5 / .25 / 240) | 0 [0, 0] | 0 [0, 0] | 0/10 | 4.14 s / 1.25 | 0.006 s / 0 | 0 |

Gains are modeled intercepts per day relative to greedy at equal hours. The serial-pair advantage is identical across seeds because the constructed branch contribution is fixed inside each split. It is evidence that the methods can separate under the stated assumptions. The single-crew case has one available checkpoint-hour and one solve with an open bound.

DOBSS values are training utility, including modeled civilian delay. Mixed and pure are compared within the same generated pool. The interception optimizer supplies a response candidate, which is a heuristic for general-sum DOBSS. A cap from detection probability times inspection rate times feasible hours bounds the unrestricted game. Mean unrestricted gaps in table order were 0.30, 259.33, 248.99 and 29.99 utility units. Pool solver times exclude response generation.

## Interpretation rule

Treat every output as conditional on the graph, synthetic flow-generation rules, assumed priors and utilities, and the observation model supplied to the code. Report interception separately from delivery reduction, deferral, and undeparted flow. Do not label modeled flow as detected criminal activity, call a hypothetical site an operational checkpoint, or infer that a route is used by illicit actors.

### Fictional corridor subdivision

Ten seeds (42–51), 10,005 detailed arcs, nine reduced arcs and two candidate sites. Mean optimized-minus-greedy interception and paired 95% interval were 0 [0, 0] on both test mixes. The maximum absolute error across 60 flow comparisons and maximum training MILP gap were both zero. Mean optimizer wall time was 0.006 s. The five-arc topology, single active hour and saturated inspection capacity limit this comparison. Crossings are unverified.
