import argparse
import json
from pathlib import Path

from checkpoints.geo import load, rows


def main() -> None:
    import matplotlib.pyplot as plt
    import networkx as nx

    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_bytes())
    graph = load()
    positions = {n: (a["x"], a["y"]) for n, a in graph.nodes(data=True)}
    sites = [(r["from_node"], r["to_node"]) for r in rows("candidate_sites.csv")]
    gates = [(u, v) for u, v, k in graph.edges.data("crossing_id") if k]
    fig, axes = plt.subplots(report["slots"], 1, figsize=(10, 2*report["slots"]), squeeze=False)
    for t, (ax,) in enumerate(axes):
        nx.draw_networkx_nodes(graph, positions, node_size=12, ax=ax)
        active = [tuple(edge) for h, edge in report["fixture_schedule"] if h == t]
        for edges, color, width in [(list(graph.edges), "silver", 1), (gates, "purple", 3),
                                    (sites, "steelblue", 3), (active, "darkorange", 5)]:
            nx.draw_networkx_edges(graph, positions, edgelist=edges, edge_color=color,
                                   width=width, ax=ax, node_size=12)
        ax.set_title(f"Hour {t+1}", loc="left")
        ax.axis("off")
    fig.suptitle("Fictional region   |   blue: candidate   purple: crossing   orange: active")
    fig.tight_layout()
    fig.savefig(args.output, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
