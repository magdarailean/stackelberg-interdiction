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

The metadata sidecar records source-file SHA-256 hashes, exact bounds, output hash, timestamp, road-class speed defaults, and ODbL attribution. The importer does not add flow capacity, candidate checkpoints, or crossing status. Those are model inputs: flows/capacities must be synthetic and documented, candidate sites remain hypothetical, and every crossing's operational/legal status remains **unverified** until separately curated. OSM geometry does not establish border access or authority.

`osmium` is imported lazily by the PBF-only function. The XML fixture builder and the optimization core do not import it. No OSMnx or GeoPandas dependency is used.

This is a data-build recipe, not evidence that the 10,000-edge corridor experiment has run. The current run reports in `outputs/` use the fictional fixture or synthetic grid; corridor interception optimization, detailed-versus-reduced flow-error measurement, solver time and optimality gap remain to be measured after a local PBF build.
