import argparse
import hashlib
import json
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("extract",type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.extract,args.output)))
