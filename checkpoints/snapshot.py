import hashlib
import hmac
import json
from pathlib import Path

import networkx as nx


def load_snapshot(directory: Path) -> tuple:
    directory = directory.resolve()
    manifests = sorted(directory.glob("roads_*.json"))
    if len(manifests) != 1:
        raise ValueError(f"Expected one roads_*.json manifest in {directory}")
    metadata = json.loads(manifests[0].read_text(encoding="utf-8"))
    if metadata.get("schema_version") != 1:
        raise ValueError("Unsupported road snapshot schema")
    name = metadata.get("graphml")
    if name != manifests[0].with_suffix(".graphml").name:
        raise ValueError("GraphML name does not match the manifest")
    graph_path = directory / name
    if graph_path.resolve().parent != directory:
        raise ValueError("GraphML must be inside the snapshot directory")
    with graph_path.open("rb") as stream:
        digest = hashlib.file_digest(stream,"sha256").hexdigest()
        expected = metadata.get("graphml_sha256", "")
        if not isinstance(expected,str) or not hmac.compare_digest(digest,expected):
            raise ValueError("GraphML SHA-256 does not match the manifest")
        stream.seek(0)
        graph = nx.read_graphml(stream,force_multigraph=True)
    if not graph.is_directed():
        raise ValueError("Road snapshot must be directed")
    if (len(graph),graph.number_of_edges()) != (metadata.get("nodes"),metadata.get("directed_edges")):
        raise ValueError("Road snapshot counts do not match the manifest")
    return graph, dict(network="corridor",mode="geometry_only", nodes=len(graph),
                directed_edges=graph.number_of_edges(),graphml_sha256=digest,
                crossing_status="unverified",metadata=metadata)


def inspect_snapshot(directory: Path) -> dict:
    return load_snapshot(directory)[1]


def corridor_report(directory: Path, seed: int) -> dict:
    from .geo import DATA
    from scripts.build_osm import read_roads

    graph, report = load_snapshot(directory)
    fixture = DATA / "fictional_roads.osm.xml"
    if report["metadata"].get("input_sha256") == hashlib.sha256(fixture.read_bytes()).hexdigest():
        reference = read_roads(fixture, json.loads((DATA / "road_classes.json").read_text()))
        if dict(graph.nodes(data=True)) != dict(reference.nodes(data=True)) or dict(graph.edges) != dict(reference.edges):
            raise ValueError("Snapshot differs from the fictional fixture")
        from .fixture_corridor import fixture_report
        report.update(fixture_report(graph, seed))
    return report
