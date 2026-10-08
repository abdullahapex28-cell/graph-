"""Report prerequisite cycles in the seeded graph."""

import asyncio
import sys
from pathlib import Path

import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.graph_service import (
    build_graph_from_records,
    load_full_graph,
    prerequisite_subgraph,
    validate_graph,
)


async def main() -> None:
    graph = await load_full_graph()
    report = validate_graph(graph)

    print(f"nodes={report.total_nodes} edges={report.total_edges} valid={report.is_valid}")
    for err in report.errors:
        print(f"  ERROR {err.code}: {err.message}")
    for cycle in report.cycle_details:
        print(f"  cycle: {' -> '.join(cycle)}")

    prereq = prerequisite_subgraph(graph)
    for cycle in nx.simple_cycles(prereq):
        print("\n  cycle with edge detail:")
        nodes = list(cycle)
        for i, u in enumerate(nodes):
            v = nodes[(i + 1) % len(nodes)]
            data = graph.edges[u, v]
            print(
                f"    {u} -> {v}  "
                f"({data.get('prerequisite_type')}, {data.get('id')})"
            )


if __name__ == "__main__":
    asyncio.run(main())
