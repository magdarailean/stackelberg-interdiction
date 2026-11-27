# Building the real OSM corridor snapshot

The checked-in `data/snapshot_2026-11-26.graphml` is a 28-edge fictional fixture. It is not the Moldova–Odesa–Romania road network. A real extract was not generated in this environment: the public Overpass endpoint timed out, while Geofabrik transfers were throttled to about 0.1–0.25 MB/s (the Ukraine PBF alone was about 845 MB). The following PowerShell commands fetch the official country extracts and build a frozen, hashed corridor graph locally.

The corridor bounding box is WGS84 `(west, south, east, north) = (25.5, 45.0, 31.5, 48.6)`. It covers western Romania, Moldova and Odesa oblast. The builder retains directed motorway, trunk, primary, secondary and tertiary road segments. Increase the box if the resulting count is below 10,000 directed edges; record the changed bounds in the report.

```powershell
$osmDir = Join-Path $PWD 'data\osm-input'
New-Item -ItemType Directory -Force $osmDir | Out-Null
Invoke-WebRequest 'https://download.geofabrik.de/europe/romania-latest.osm.pbf' -OutFile (Join-Path $osmDir 'romania-latest.osm.pbf')
Invoke-WebRequest 'https://download.geofabrik.de/europe/moldova-latest.osm.pbf' -OutFile (Join-Path $osmDir 'moldova-latest.osm.pbf')
Invoke-WebRequest 'https://download.geofabrik.de/europe/ukraine-latest.osm.pbf' -OutFile (Join-Path $osmDir 'ukraine-latest.osm.pbf')
python -m pip install -r requirements-osm.txt
python scripts/build_osm.py `
  (Join-Path $osmDir 'romania-latest.osm.pbf') `
  (Join-Path $osmDir 'moldova-latest.osm.pbf') `
  (Join-Path $osmDir 'ukraine-latest.osm.pbf') `
  --output data\corridor `
  --bbox 25.5 45.0 31.5 48.6
```

The metadata sidecar records source-file SHA-256 hashes, exact bounds, output hash, timestamp, road-class speed defaults, and ODbL attribution. The importer exports road geometry and keeps crossing status **unverified**. OSM geometry does not establish border access or authority.

`osmium` is imported lazily by the PBF-only function. The XML fixture builder and the optimization core do not import it. No OSMnx or GeoPandas dependency is used.

After building a snapshot, inspect its schema, GraphML SHA-256, direction, and counts:

```powershell
python benchmark.py --network corridor
python -m checkpoints.study --network corridor
```

Both commands require exactly one matching manifest in the snapshot directory. For an offline check with the same manifest format:

```powershell
python -m scripts.build_osm data/fictional_roads.osm.xml --output corridor-fixture
python benchmark.py --network corridor --corridor-dir corridor-fixture
python -m checkpoints.study --network corridor --corridor-dir corridor-fixture
```

The offline file has four nodes and five directed arcs. Both commands recognize its source hash and check its graph against the bundled XML. On this fixture each arc becomes a separate chain of 2,001 equal segments. The two eligible primary arcs each carry one candidate at their midpoint (about 111 m along the fictional road between candidates). The reverse direction and parallel road retain distinct chains. Other snapshots receive geometry verification only.

The fixture config sets synthetic class capacities and terminal zones. One crew works one slot, the factor is 0.3, and the default research ledger applies. Each seed draws independent supply and demand at the two terminals once per split. Unprotected one-in/one-out chain nodes collapse to minimum series capacity; parallel capacities add. Candidate endpoints and zones remain explicit. The MILP and greedy fit on the reduced graph and both use the detailed graph for scoring. At one hour, greedy exhausts the feasible active choices. Subdivision tests flow preservation, not planning complexity. The real PBF recipe has not been run in this checkout.
