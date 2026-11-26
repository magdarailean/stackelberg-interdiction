import networkx as nx
from time import perf_counter

from .follower import Scenario


def subdivision_check(slot: Scenario, segments: int) -> dict:
    if segments < 1:
        raise ValueError("Expected positive subdivision count")
    graph = nx.DiGraph()
    graph.add_nodes_from(slot.graph)
    for index, (u, v, capacity) in enumerate(slot.graph.edges.data("capacity")):
        chain = [u, *((index, i) for i in range(1, segments)), v]
        graph.add_weighted_edges_from(((a, b, capacity) for a, b in zip(chain, chain[1:])),
                                      weight="capacity")
    start = perf_counter()
    measured = nx.maximum_flow_value(graph, slot.source, slot.sink,
                                     flow_func=nx.algorithms.flow.edmonds_karp)
    return dict(edges=graph.number_of_edges(), base_edges=slot.graph.number_of_edges(),
                delivered=measured, absolute_error=abs(measured-slot.delivered()),
                follower_seconds=perf_counter()-start, slots=1, scenarios=1)
