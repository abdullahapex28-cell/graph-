"""Check that each solver is genuinely computing (not silently falling back)."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cost_engine import build_problem, net_utility
from app.graph_service import (
    choose_traversal, load_full_graph, retrieve_ancestor_subgraph,
)
from app.optimizers.dp import DynamicProgrammingSolver
from app.optimizers.greedy import GreedyFrontierSolver
from app.optimizers.ilp import ILPSolver
from app.schemas import ConstraintConfig, TraversalConfig, TraversalStrategy


async def run_target(target: str, cap: int = 60) -> None:
    graph = await load_full_graph()
    decision = choose_traversal(graph, target, TraversalStrategy.AUTO)
    subgraph, _ = retrieve_ancestor_subgraph(
        graph, target, decision.selected, TraversalConfig(max_subgraph_nodes=cap)
    )
    problem = build_problem(subgraph, target, ConstraintConfig())

    print(f"\n=== target {target} "
          f"(subgraph {problem.graph.number_of_nodes()} nodes, "
          f"HARD closure {len(problem.hard_prerequisites)}) ===")

    results = {}
    for name, solver in (
        ("GREEDY", GreedyFrontierSolver()),
        ("DP", DynamicProgrammingSolver()),
        ("ILP", ILPSolver()),
    ):
        m = solver.run(problem)
        results[name] = m
        print(f"  {name:7s} nodes={len(m.path_nodes):3d} "
              f"utility={m.net_utility:+9.4f} roi={m.path_score:.4f} "
              f"feasible={m.is_feasible} {m.execution_time_ms:8.1f}ms")

    # The sound invariant: the exact solver must never be beaten.
    if results["ILP"].is_feasible and results["DP"].is_feasible:
        gap = results["ILP"].net_utility - results["DP"].net_utility
        verdict = "OK" if gap >= -1e-6 else "VIOLATION"
        print(f"  ILP >= DP ? {verdict} (gap {gap:+.4f})")

    d = results["DP"].solver_specific
    if d.get("strategy") == "budget_infeasible_fallback":
        print("  WARNING: DP hit the fallback path")
    else:
        print(f"  DP target state: net={d.get('target_state_net')} "
              f"visited={d.get('nodes_visited')}")


async def main() -> None:
    for target in ("q_field", "th_string", "astro_cosmo", "rel_gw", "opt_laser", "mat_condense"):
        await run_target(target)


if __name__ == "__main__":
    asyncio.run(main())
