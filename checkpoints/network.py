"""Fictional six-node directed network."""
import networkx as nx

Edge = tuple[str, str]
SITES = (("A", "C"), ("A", "D"), ("B", "C"), ("B", "D"))

def toy_graph() -> nx.DiGraph:
    """Return fresh capacities in flow units per hour."""
    graph = nx.DiGraph()
    graph.add_weighted_edges_from([
        ("S", "A", 10), ("S", "B", 8), ("A", "C", 7), ("A", "D", 4),
        ("B", "C", 4), ("B", "D", 7), ("C", "T", 8), ("D", "T", 9)
    ], weight="capacity")
    return graph
