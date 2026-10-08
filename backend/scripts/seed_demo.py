"""
Seed the local Neo4j with a demo knowledge graph and exercise the live pipeline.

Usage:
    test/Scripts/python.exe -m scripts.seed_demo
    test/Scripts/python.exe -m scripts.seed_demo --reset
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.crud import create_node, create_relationship, get_all_nodes, get_all_relationships
from app.database import clear_database, init_database, verify_connectivity, close_driver
from app.optimization_service import PipelineError, compare_solvers, optimize_path
from app.schemas import (
    ConstraintConfig,
    PathCompareRequest,
    PathOptimizeRequest,
    TraversalStrategy,
)


def prereq(eid, s, t, p, time, effort):
    return {
        "id": eid, "source": s, "target": t,
        "type": "PREREQUISITE_OF", "prerequisite_type": p,
        "time_required_minutes": time, "cognitive_effort": effort,
    }


NODES = [
    {"id": "var", "name": "Variables", "description": "Binding, types and scope", "target_relevance": 0.30, "downstream_utility": 0.95},
    {"id": "fn", "name": "Functions", "description": "Definition, arguments, calls", "target_relevance": 0.50, "downstream_utility": 0.90},
    {"id": "loop", "name": "Loops", "description": "Iteration constructs", "target_relevance": 0.60, "downstream_utility": 0.85},
    {"id": "rec", "name": "Recursion", "description": "Recursive problem decomposition", "target_relevance": 0.70, "downstream_utility": 0.75},
    {"id": "ds", "name": "Data Structures", "description": "Arrays, lists, trees, heaps", "target_relevance": 0.65, "downstream_utility": 0.92},
    {"id": "algo", "name": "Algorithms", "description": "Design and complexity analysis", "target_relevance": 0.85, "downstream_utility": 0.70},
    {"id": "graph", "name": "Graph Structures", "description": "Adjacency, traversal, trees", "target_relevance": 0.80, "downstream_utility": 0.80},
    {"id": "dyn", "name": "Dynamic Programming", "description": "Memoisation and optimal substructure", "target_relevance": 0.95, "downstream_utility": 0.40},
    {"id": "num", "name": "Number Theory", "description": "Optional detour off the main line", "target_relevance": 0.15, "downstream_utility": 0.10},
    {"id": "opt", "name": "Graph Optimization", "description": "Cost-aware search and planning", "target_relevance": 1.00, "downstream_utility": 0.20},
]

EDGES = [
    prereq("r1", "var", "fn", "HARD", 30, 2),
    prereq("r2", "fn", "loop", "HARD", 40, 3),
    prereq("r3", "loop", "rec", "SOFT", 50, 4),
    prereq("r4", "fn", "ds", "HARD", 35, 2),
    prereq("r5", "ds", "algo", "HARD", 55, 4),
    prereq("r6", "rec", "algo", "SOFT", 60, 5),
    prereq("r7", "algo", "dyn", "HARD", 70, 5),
    prereq("r8", "ds", "graph", "HARD", 45, 3),
    prereq("r9", "graph", "opt", "HARD", 65, 4),
    prereq("r10", "dyn", "opt", "SOFT", 80, 5),
    prereq("r11", "num", "opt", "OPTIONAL", 120, 5),
    prereq("r12", "loop", "ds", "HARD", 25, 2),
]


async def seed(reset: bool) -> None:
    if not await verify_connectivity():
        print("[ERROR] Neo4j is not reachable on bolt://localhost:7687")
        print("        Start Neo4j, then re-run this script.")
        return

    await init_database()

    if reset:
        await clear_database()
        print("Cleared existing data.")
    elif await get_all_nodes():
        print("Database already has data. Re-run with --reset to reseed.")
        return

    from app.models import NodeCreate, RelationshipCreate

    for node in NODES:
        await create_node(NodeCreate(**node))
    print(f"Created {len(NODES)} nodes.")

    created = 0
    for edge in EDGES:
        try:
            await create_relationship(RelationshipCreate(**edge))
            created += 1
        except ValueError as exc:
            print(f"  skipped {edge['id']}: {exc}")
    print(f"Created {created} relationships.")


async def demo_pipeline(target: str) -> None:
    print("\n" + "=" * 70)
    print(f"LIVE PIPELINE DEMO -> target '{target}'")
    print("=" * 70)

    constraints = ConstraintConfig()

    for method in (TraversalStrategy.AUTO, TraversalStrategy.BFS, TraversalStrategy.DFS):
        try:
            result = await compare_solvers(
                PathCompareRequest(
                    target_node_id=target,
                    search_method=method,
                    constraints=constraints,
                )
            )
        except PipelineError as exc:
            print(f"\n[{method.value}] pipeline error: {exc.message}")
            continue

        traversal = result.traversal
        comparison = result.comparison

        print(f"\n--- search_method = {method.value} ---")
        if method == TraversalStrategy.AUTO:
            print(f"  AUTO chose: {traversal.selected.value}")
            print(f"  reason: {traversal.reason}")
        else:
            print(f"  traversal: {traversal.selected.value} (pinned)")

        print(f"  subgraph: {comparison.subgraph_size['retrieved_nodes']} nodes / "
              f"{comparison.subgraph_size['retrieved_edges']} edges "
              f"(from {comparison.subgraph_size['full_graph_nodes']})")

        print(f"\n  {'Solver':<28} {'ROI':>9} {'Utility':>9} {'Cost':>8} {'Time':>7} {'ms':>8}  OK")
        print("  " + "-" * 78)
        for r in comparison.results:
            print(
                f"  {r.display_name:<28} {r.path_score:>9.4f} {r.net_utility:>9.4f} "
                f"{r.total_path_cost:>8.4f} {r.total_time_minutes:>5}m "
                f"{r.execution_time_ms:>8.1f}  {'Y' if r.is_feasible else 'N'}"
            )

        print(f"\n  BEST: {comparison.best_solver}")
        for line in comparison.recommendation_rationale:
            print(f"    - {line}")

        best = next(r for r in comparison.results if r.solver == comparison.best_solver)
        sequence = result.learning_sequences.get(comparison.best_solver.value, [])
        print(f"\n  Learning sequence ({best.display_name}):")
        for step in sequence:
            lock = " [HARD]" if step["is_hard_prerequisite"] else ""
            print(f"    {step['step']}. {step['name']}{lock} "
                  f"(value {step['learning_value']:.3f}, ~{step['estimated_time_minutes']}m)")

    # Single-solver explanation output
    print("\n" + "=" * 70)
    print("SINGLE-SOLVER EXPLANATION (DP)")
    print("=" * 70)
    result = await optimize_path(
        PathOptimizeRequest(
            target_node_id=target,
            search_method=TraversalStrategy.AUTO,
            solver="DP",
            constraints=constraints,
        )
    )
    print(result.explanation)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="wipe existing data first")
    parser.add_argument("--target", default="opt", help="target node id for the demo")
    parser.add_argument("--skip-demo", action="store_true")
    args = parser.parse_args()

    await seed(args.reset)

    if not args.skip_demo:
        await demo_pipeline(args.target)

    await close_driver()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
