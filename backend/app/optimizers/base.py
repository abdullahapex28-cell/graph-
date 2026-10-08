"""
Shared scaffolding for the three optimization solvers.

Every solver receives the *same* :class:`OptimizationProblem` instance, which
is what makes the Greedy / DP / ILP comparison a fair, apples-to-apples
benchmark rather than three separate pipelines.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Dict, List, Set

from networkx import topological_sort as nx_topological_sort

from app.cost_engine import (
    OptimizationProblem,
    average_learning_value,
    collect_used_edges,
    net_utility,
    path_cost,
    path_raw_time,
    path_score,
    validate_solution,
)
from app.schemas import SolverAlgorithm, SolverMetrics

DISPLAY_NAMES: Dict[SolverAlgorithm, str] = {
    SolverAlgorithm.GREEDY_FRONTIER: "Greedy Frontier",
    SolverAlgorithm.DYNAMIC_PROGRAMMING: "Dynamic Programming",
    SolverAlgorithm.INTEGER_LINEAR_PROGRAMMING: "Integer Linear Programming",
}


class BaseSolver(ABC):
    """Common timing / metric assembly for all solvers."""

    algorithm: SolverAlgorithm

    @property
    def display_name(self) -> str:
        return DISPLAY_NAMES[self.algorithm]

    @abstractmethod
    def solve(self, problem: OptimizationProblem) -> Set[str]:
        """Return the selected node id set."""

    # ------------------------------------------------------------------
    def run(self, problem: OptimizationProblem) -> SolverMetrics:
        """Execute the solver and normalise its output into SolverMetrics."""
        started = time.perf_counter()
        try:
            selected = self.solve(problem)
            error: str | None = None
        except Exception as exc:  # a failing solver must not break comparison
            selected = {problem.target_id}
            error = f"{type(exc).__name__}: {exc}"
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        is_feasible, reason = validate_solution(problem, selected)
        if error:
            is_feasible = False
            reason = error

        cost = path_cost(problem, selected)
        avg_value = average_learning_value(problem, selected)
        score = path_score(problem, selected)

        return SolverMetrics(
            solver=self.algorithm,
            display_name=self.display_name,
            is_feasible=is_feasible,
            feasibility_reason=reason,
            path_nodes=sorted(selected),
            path_edges=collect_used_edges(problem, selected),
            total_path_cost=round(cost, 6),
            average_learning_value=round(avg_value, 6),
            path_score=round(score, 6),
            total_time_minutes=path_raw_time(problem, selected),
            execution_time_ms=round(elapsed_ms, 3),
            net_utility=round(net_utility(problem, selected), 6),
            solver_specific=self.describe(problem, selected),
        )

    # ------------------------------------------------------------------
    def describe(
        self, problem: OptimizationProblem, selected: Set[str]
    ) -> Dict[str, object]:
        """Solver-specific diagnostics surfaced in the comparison UI."""
        return {}


def learning_sequence(
    problem: OptimizationProblem, selected: Set[str]
) -> List[Dict[str, object]]:
    """
    Topological sort (NetworkX Kahn) over the selected subset, then decorate
    with per-step metrics for the UI.
    """
    induced = problem.prerequisite_only.subgraph(selected).copy()

    try:
        order = list(nx_topological_sort(induced))
    except Exception:
        # Fall back to a deterministic order if a residual cycle exists.
        order = sorted(selected)

    used_edges = set(collect_used_edges(problem, selected))
    edge_lookup = {e.edge_id: e for e in problem.edges.values()}

    sequence: List[Dict[str, object]] = []
    for index, node_id in enumerate(order, start=1):
        node = problem.nodes[node_id]
        prerequisites = [
            {
                "edge_id": edge_id,
                "source": edge_lookup[edge_id].source,
                "source_name": problem.nodes[edge_lookup[edge_id].source].name,
                "prerequisite_type": (
                    edge_lookup[edge_id].prerequisite_type.value
                    if edge_lookup[edge_id].prerequisite_type
                    else None
                ),
                "time_required_minutes": edge_lookup[edge_id].raw_time_minutes,
                "cognitive_effort": edge_lookup[edge_id].raw_cognitive_effort,
                "edge_cost": round(edge_lookup[edge_id].edge_cost, 6),
            }
            for edge_id in problem.incoming.get(node_id, [])
            if edge_id in used_edges
        ]

        sequence.append(
            {
                "step": index,
                "node_id": node_id,
                "name": node.name,
                "description": node.description,
                "learning_value": round(node.learning_value, 6),
                "is_hard_prerequisite": node.is_hard_prerequisite,
                "estimated_time_minutes": sum(
                    p["time_required_minutes"] for p in prerequisites
                ),
                "prerequisites": prerequisites,
            }
        )

    return sequence
