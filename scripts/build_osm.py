import argparse
import hashlib
import json
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from xml.etree import ElementTree

import networkx as nx


def length_m(first: dict, second: dict) -> float:
    lat, other = radians(first["lat"]), radians(second["lat"])
    dx = radians(second["lon"] - first["lon"])
    a = sin((lat-other)/2)**2 + cos(lat)*cos(other)*sin(dx/2)**2
    return 12_742_000 * asin(sqrt(min(1., a)))


def speed_kmh(raw: str, default: float) -> float:
    parts = raw.lower().split()
    if len(parts) not in (1,2):
        return default
    try:
        speed = float(parts[0])
    except ValueError:
        return default
    if len(parts) == 2:
        if parts[1] == "mph":
            speed *= 1.609344
        elif parts[1] != "km/h":
            return default
    return speed if 0 < speed < float("inf") else default


def elements(path: Path, kind: str):
    events = ElementTree.iterparse(path,events=("start","end"))
    _, root = next(events)
    for event, element in events:
        if event == "end" and element.tag in ("node","way","relation"):
            if element.tag == kind:
                yield element
            root.clear()


def read_roads(path: Path, speeds: dict) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    for element in elements(path,"node"):
        graph.add_node(element.attrib["id"], lat=float(element.attrib["lat"]), lon=float(element.attrib["lon"]))
    for element in elements(path,"way"):
        tags = {t.attrib["k"]:t.attrib["v"] for t in element.findall("tag")}
        road = tags.get("highway")
        if road in speeds:
            refs = [n.attrib["ref"] for n in element.findall("nd")]
            one_way = tags.get("oneway", "yes" if tags.get("junction")=="roundabout" or road=="motorway" else "no")
            if one_way not in ("yes","1","true","-1","reverse","no","0","false"):
                raise ValueError(f"Unsupported direction {one_way}")
            speed = speed_kmh(tags.get("maxspeed",""),speeds[road])
            for i,(u,v) in enumerate(zip(refs,refs[1:])):
                if u not in graph or v not in graph:
                    raise ValueError("Extract is missing a referenced node")
                length = length_m(graph.nodes[u],graph.nodes[v])
                pairs = [(u,v)]
                if one_way in ("-1","reverse"):
                    pairs = [(v,u)]
                elif one_way in ("no","0","false") and u != v:
                    pairs.append((v,u))
                for start,end in pairs:
                    graph.add_edge(start,end,key=element.attrib["id"]+":"+str(i),way_id=element.attrib["id"],
                                   road_class=road,length_m=length,travel_time_s=length*3.6/speed,speed_kmh=speed)
    graph.remove_nodes_from(list(nx.isolates(graph)))
    return graph


def read_roads_pbf(paths: list[Path], speeds: dict, bbox: tuple[float, float, float, float]) -> nx.MultiDiGraph:
    """Read bounded road segments from PBFs through optional PyOsmium.

    bbox is (west, south, east, north). The function records road geometry and
    direction only: operational capacity, checkpoint authority and crossing status
    are not facts established by OSM.
    """
    try:
        import osmium
    except ImportError as exc:
        raise RuntimeError("PBF import requires optional PyOsmium; see requirements-osm.txt") from exc

    west, south, east, north = bbox
    if not (west < east and south < north):
        raise ValueError("Invalid bounding box")
    graph = nx.MultiDiGraph()

    class RoadHandler(osmium.SimpleHandler):
        def way(self, way):
            road = way.tags.get("highway")
            if road not in speeds:
                return
            refs = list(way.nodes)
            if len(refs) < 2 or any(not node.location.valid() for node in refs):
                return
            one_way = way.tags.get("oneway", "yes" if way.tags.get("junction") == "roundabout" or road == "motorway" else "no")
            if one_way not in ("yes", "1", "true", "-1", "reverse", "no", "0", "false"):
                return
            speed = speed_kmh(way.tags.get("maxspeed", ""), speeds[road])
            for i, (first, second) in enumerate(zip(refs, refs[1:])):
                lat1, lon1 = first.location.lat, first.location.lon
                lat2, lon2 = second.location.lat, second.location.lon
                if not (west <= lon1 <= east and south <= lat1 <= north
                        and west <= lon2 <= east and south <= lat2 <= north):
                    continue
                u, v = str(first.ref), str(second.ref)
                graph.add_node(u, lat=lat1, lon=lon1)
                graph.add_node(v, lat=lat2, lon=lon2)
                length = length_m({"lat": lat1, "lon": lon1}, {"lat": lat2, "lon": lon2})
                pairs = [(u, v)]
                if one_way in ("-1", "reverse"):
                    pairs = [(v, u)]
                elif one_way in ("no", "0", "false") and u != v:
                    pairs.append((v, u))
                for start, end in pairs:
                    graph.add_edge(start, end, key=f"{way.id}:{i}", way_id=str(way.id),
                                   road_class=road, length_m=length,
                                   travel_time_s=length * 3.6 / speed, speed_kmh=speed)

    for path in paths:
        RoadHandler().apply_file(str(path), locations=True)
    graph.remove_nodes_from(list(nx.isolates(graph)))
    return graph


def build(path: Path, output: Path) -> dict:
    cfg = Path(__file__).resolve().parents[1]/"data"/"road_classes.json"
    speeds = json.loads(cfg.read_text())
    with path.open("rb") as stream:
        fingerprint = hashlib.file_digest(stream,"sha256").hexdigest()
    version = hashlib.sha256((fingerprint+json.dumps(speeds,sort_keys=True)+"1").encode()).hexdigest()[:16]
    graph = read_roads(path,speeds)
    output.mkdir(parents=True,exist_ok=True)
    target = output/f"roads_{version}.graphml"
    nx.write_graphml(graph,target)
    metadata = dict(schema_version=1,input_sha256=fingerprint,source=path.name,nodes=len(graph),
                    directed_edges=graph.number_of_edges(),graphml=target.name,class_defaults_kmh=speeds,
                    graphml_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                    attribution="OpenStreetMap contributors for OSM-derived data",license="ODbL-1.0",
                    license_url="https://www.openstreetmap.org/copyright")
    target.with_suffix(".json").write_text(json.dumps(metadata,indent=2))
    return metadata


def build_pbf(paths: list[Path], output: Path,
              bbox: tuple[float, float, float, float]) -> dict:
    cfg = Path(__file__).resolve().parents[1]/"data"/"road_classes.json"
    speeds = json.loads(cfg.read_text())
    fingerprints = {}
    for path in paths:
        with path.open("rb") as stream:
            fingerprints[path.name] = hashlib.file_digest(stream, "sha256").hexdigest()
    graph = read_roads_pbf(paths, speeds, bbox)
    output.mkdir(parents=True, exist_ok=True)
    input_hash = hashlib.sha256(json.dumps(fingerprints, sort_keys=True).encode()).hexdigest()
    version = hashlib.sha256((input_hash + json.dumps(speeds, sort_keys=True) + str(bbox)).encode()).hexdigest()[:16]
    target = output / f"roads_{version}.graphml"
    nx.write_graphml(graph, target)
    metadata = dict(schema_version=1, source="Geofabrik country PBF extracts", input_sha256=fingerprints,
                    bbox_west_south_east_north=bbox, data_snapshot_utc=datetime.now(timezone.utc).isoformat(),
                    nodes=len(graph), directed_edges=graph.number_of_edges(), graphml=target.name,
                    graphml_sha256=hashlib.sha256(target.read_bytes()).hexdigest(), class_defaults_kmh=speeds,
                    candidate_sites="hypothetical; added by the experiment configuration",
                    crossing_status="unverified; OSM geometry does not establish legal/operational access",
                    capacities="synthetic; not derived from OSM geometry",
                    attribution="© OpenStreetMap contributors", license="ODbL-1.0",
                    license_url="https://www.openstreetmap.org/copyright")
    target.with_suffix(".json").write_text(json.dumps(metadata, indent=2))
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("extract",type=Path,nargs="+")
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--bbox",nargs=4,type=float,metavar=("WEST","SOUTH","EAST","NORTH"))
    args = parser.parse_args()
    if args.bbox:
        print(json.dumps(build_pbf(args.extract,args.output,tuple(args.bbox))))
    elif len(args.extract) == 1 and args.extract[0].suffix.lower() == ".xml":
        print(json.dumps(build(args.extract[0],args.output)))
    else:
        parser.error("PBF inputs require --bbox WEST SOUTH EAST NORTH; XML mode accepts one .osm.xml")
