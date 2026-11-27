from pathlib import Path
from random import Random
from statistics import mean
from tempfile import TemporaryDirectory
from time import perf_counter
from xml.etree import ElementTree as ET

import networkx as nx

from .geo import reduce_graph
from scripts.build_osm import read_roads


def artificial_extract(path: Path, width: int, segments: int) -> tuple[str,str,list]:
    root = ET.Element("osm",version="0.6",generator="synthetic-road-test")
    sites = []
    def node(key,x,y):
        ET.SubElement(root,"node",id=key,lat=str(y/1000),lon=str(x/1000))
    for y in range(width):
        for x in range(width):
            node(f"{x}.{y}",x,y)
    for y in range(width):
        for x in range(width):
            for dx,dy in ((1,0),(0,1)):
                if x+dx >= width or y+dy >= width:
                    continue
                a,b = f"{x}.{y}", f"{x+dx}.{y+dy}"
                refs = [a]
                for k in range(1,segments):
                    key = f"{a}-{b}-{k}"
                    node(key,x+dx*k/segments,y+dy*k/segments)
                    refs.append(key)
                refs.append(b)
                way = ET.SubElement(root,"way",id=f"{a}-{b}")
                for key in refs:
                    ET.SubElement(way,"nd",ref=key)
                ET.SubElement(way,"tag",k="highway",v="primary")
                ET.SubElement(way,"tag",k="oneway",v="yes")
                if x==y and dx and len(sites)<3:
                    sites.append(tuple(refs[:2]))
    ET.ElementTree(root).write(path)
    return "0.0", f"{width-1}.{width-1}", sites


def road_check(cfg,seed):
    with TemporaryDirectory() as directory:
        path = Path(directory)/"fictional.osm.xml"
        source,sink,sites = artificial_extract(path,cfg["width"],cfg["segments"])
        roads = read_roads(path,{"primary":60})
    keep = {source,sink}.union(n for edge in sites for n in edge)
    rng = Random(seed)
    errors = []
    elapsed = 0.
    for _ in range(cfg["scenarios"]):
        graph = nx.DiGraph()
        for u,v in roads.edges():
            capacity = 0 if rng.random()<cfg["closure_probability"] else cfg["capacity"]
            graph.add_edge(u,v,capacity=capacity)
        reduced = reduce_graph(graph,keep,tuple(sites))
        for site in [None,*sites]:
            flows = []
            for g in (graph,reduced):
                if site:
                    original = g.edges[site]["capacity"]
                    g.edges[site]["capacity"] *= cfg["factor"]
                start = perf_counter()
                flows.append(nx.maximum_flow_value(g,source,sink,flow_func=nx.algorithms.flow.edmonds_karp))
                elapsed += perf_counter()-start
                if site:
                    g.edges[site]["capacity"] = original
            errors.append(abs(flows[0]-flows[1])/(flows[0] or 1))
    error = mean(errors)
    if error>cfg["tolerance"]:
        raise ValueError("Synthetic road reduction exceeds tolerance")
    return dict(source="generated OSM XML",detailed_edges=roads.number_of_edges(),
                reduced_edges=reduced.number_of_edges(),candidates=len(sites),slots=1,
                scenarios=cfg["scenarios"],comparisons=len(errors),mean_relative_error=error,
                max_relative_error=max(errors),follower_solve_seconds=elapsed)
