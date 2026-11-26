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
| Interception-first comparison | 10 paired seeds, same checkpoint-hours, synthetic held-out scenarios. Baseline nominal mean optimizer-minus-greedy gain: **−0.0221**, 95% CI **[−0.0663, 0]**, win rate **0/10**. Baseline shifted mean: **+0.0239**, CI **[0, +0.0717]**, win rate **1/10**. High-detection and high-capacity runs had zero gain. Solver gaps were zero on these small fixture instances. | One exploratory synthetic regime had a slight positive mean under shifted tests, but its interval touches zero and only one seed won. This is not a reliable advantage over greedy and does not support the hypothesis that optimization consistently beats greedy. No corridor result exists. Full values: [`outputs/interception_first.json`](../outputs/interception_first.json). |
| DOBSS solver verification | 20 seeded random tiny games match multiple-LP values within `1e-6`; a constructed game has mixed value **0.5** versus best pure **0.0** | Those checks validate the finite-game implementation, not the realism of utility inputs. |
| Value of randomization on the main study family | DOBSS mixed value **1.505625**, best-pure value **1.505625**, measured difference approximately **0**; 38 feasible schedules enumerated; solve time **0.014 s**, optimality gap **0** | Type priors and payoff coefficients are declared assumptions in `data/research.json`. The main family did not benefit from randomization. |
| Runtime and optimality | SCIP/OR-Tools status, bounds, gaps, and elapsed solver time on the stated synthetic instances | Synthetic-grid speed does not establish runtime on a real 10,000-edge corridor. |
| VIIRS prior | Not used | Skipped; no conclusions based on VIIRS or nighttime lights. |

## Interpretation rule

Treat every output as conditional on the graph, synthetic flow-generation rules, assumed priors and utilities, and the observation model supplied to the code. Report interception separately from delivery reduction, deferral, and undeparted flow. Do not label modeled flow as detected criminal activity, call a hypothetical site an operational checkpoint, or infer that a route is used by illicit actors.
