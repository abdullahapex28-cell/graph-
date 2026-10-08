"""
Orchestration service — runs the full pipeline and benchmarks the solvers.

Pipeline (strict order):

    FULL KG
      -> Global Graph Validation            (NetworkX DAG + cycle detection)
      -> Target Selection                   (request.target_node_id)
      -> Reverse DFS/BFS Subgraph Retrieval (AUTO heuristic)
      -> Target-Specific Constraints        (HARD / SOFT / OPTIONAL)
      -> Relevant DAG Construction
      -> Runtime Normalization & Cost Calc  (never persisted to Neo4j)
      -> DP-Based Global Optimization
      -> Best Valid Plan
      -> Topological Sort                   (NetworkX Kahn)
      -> Final Path & Visual Explanation
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Optional, Sequence, Set, Tuple

from app.cost_engine import OptimizationProblem, build_problem, path_raw_time
from app.graph_service import (
    choose_traversal,
    load_full_graph,
    retrieve_ancestor_subgraph,
    validate_graph,
)
from app.optimizers import ALL_SOLVERS, get_solver, learning_sequence
from app.schemas import (
    ConstraintConfig,
    PathCompareRequest,
    PathCompareResponse,
    PathOptimizeRequest,
    PathOptimizeResponse,
    SolverAlgorithm,
    SolverComparison,
    SolverMetrics,
    TraversalStrategy,
)
from app.validation import validate_target_exists

logger = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    """Raised when the pipeline cannot produce a valid result."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ============================================================================
# SHARED SUBGRAPH PREPARATION
# ============================================================================

async def _prepare(
    target_node_id: str,
    search_method: TraversalStrategy,
    constraints: ConstraintConfig,
    traversal_config,
) -> Tuple[OptimizationProblem, Dict[str, object], object, object, object]:
    """
    Steps 1-6 of the pipeline.

    Returns (problem, traversal_stats, validation_report, auto_decision).
    """
    # ---- Step 1: load + validate the FULL knowledge graph --------------
    full_graph = await load_full_graph()

    if full_graph.number_of_nodes() == 0:
        raise PipelineError("Knowledge graph is empty. Add concepts first.", 400)

    if target_node_id not in full_graph:
        raise PipelineError(
            f"Target node '{target_node_id}' not found in the knowledge graph.", 404
        )

    validation = validate_graph(full_graph)
    if not validation.is_valid:
        messages = "; ".join(issue.message for issue in validation.errors)
        raise PipelineError(
            f"Global graph validation failed: {messages}. "
            "Fix duplicate ids, self-loops or prerequisite cycles before optimizing.",
            400,
        )

    # ---- Step 2: search space reduction with AUTO strategy ------------
    auto_decision = choose_traversal(full_graph, target_node_id, search_method)

    subgraph, traversal_stats = retrieve_ancestor_subgraph(
        full_graph, target_node_id, auto_decision.selected, traversal_config
    )

    if subgraph.number_of_nodes() <= 1:
        # Target has no prerequisites — a valid but trivial path.
        subgraph.add_node(
            target_node_id,
            id=target_node_id,
            name=full_graph.nodes[target_node_id].get("name", target_node_id),
            description=full_graph.nodes[target_node_id].get("description", ""),
            target_relevance=full_graph.nodes[target_node_id].get("target_relevance", 0.0),
            downstream_utility=full_graph.nodes[target_node_id].get("downstream_utility", 0.0),
        )

    # ---- Steps 3-6: constraints, DAG, runtime normalisation ------------
    problem = build_problem(subgraph, target_node_id, constraints)

    return problem, traversal_stats, validation, auto_decision


# ============================================================================
# SINGLE-SOLVER OPTIMIZATION
# ============================================================================

async def optimize_path(request: PathOptimizeRequest) -> PathOptimizeResponse:
    """Run the pipeline with one solver and return the full explanation."""
    problem, traversal_stats, validation, auto_decision = await _prepare(
        request.target_node_id,
        request.search_method,
        request.constraints,
        request.traversal,
    )

    solver = get_solver(request.solver)
    metrics = await asyncio.to_thread(solver.run, problem)

    sequence = learning_sequence(problem, set(metrics.path_nodes))

    return PathOptimizeResponse(
        validation=validation,
        traversal=auto_decision,
        traversal_stats=traversal_stats,
        subgraph_nodes=list(problem.nodes.values()),
        subgraph_edges=list(problem.edges.values()),
        result=metrics,
        learning_sequence=sequence,
        explanation=_explain_single(problem, auto_decision, metrics, sequence),
    )


# ============================================================================
# MULTI-SOLVER COMPARISON
# ============================================================================

async def compare_solvers(request: PathCompareRequest) -> PathCompareResponse:
    """
    Run Reverse Traversal ONCE, then execute Greedy, DP and ILP over the exact
    same subgraph so the comparison isolates the algorithm, not the subgraph.
    """
    problem, traversal_stats, validation, auto_decision = await _prepare(
        request.target_node_id,
        request.search_method,
        request.constraints,
        request.traversal,
    )

    requested: Sequence[SolverAlgorithm] = request.solvers or ALL_SOLVERS
    solvers = [get_solver(algorithm) for algorithm in requested]

    # Sequential execution keeps timing measurements honest (no CPU contention
    # inflating one solver's wall-clock number). The ILP dominates runtime.
    results: List[SolverMetrics] = []
    for solver in solvers:
        results.append(await asyncio.to_thread(solver.run, problem))

    best, rationale = _pick_winner(results, problem)

    comparison = SolverComparison(
        target_node_id=problem.target_id,
        target_node_name=problem.nodes[problem.target_id].name,
        subgraph_size={
            "full_graph_nodes": traversal_stats.get("full_graph_nodes", 0),
            "full_graph_edges": traversal_stats.get("full_graph_edges", 0),
            "retrieved_nodes": problem.graph.number_of_nodes(),
            "retrieved_edges": problem.graph.number_of_edges(),
            "reduction_ratio": traversal_stats.get("reduction_ratio", 0.0),
        },
        shared_subgraph_node_ids=sorted(problem.nodes),
        shared_subgraph_edge_ids=sorted(problem.edges),
        results=results,
        best_solver=best.solver if best else None,
        best_path_score=best.path_score if best else 0.0,
        recommendation=_recommendation(best, results, problem),
        recommendation_rationale=rationale,
        constraints_applied=request.constraints,
    )

    sequences = {
        result.solver.value: learning_sequence(problem, set(result.path_nodes))
        for result in results
    }

    return PathCompareResponse(
        validation=validation,
        traversal=auto_decision,
        subgraph_nodes=list(problem.nodes.values()),
        subgraph_edges=list(problem.edges.values()),
        comparison=comparison,
        learning_sequences=sequences,
    )


# ============================================================================
# WINNER SELECTION & NARRATIVE
# ============================================================================

def _pick_winner(
    results: List[SolverMetrics], problem: OptimizationProblem
) -> Tuple[Optional[SolverMetrics], List[str]]:
    """
    Only *feasible* solvers compete.

    Ranking key, in order:
      1. Highest Path Score (ROI)     - the headline comparison metric
      2. Highest Net Utility         - tie-break on learning value minus cost
      3. Lower total time, then lower runtime

    All solvers optimise the same Net Utility objective, so a divergence in
    Path Score reflects genuinely different plans, not different goals.
    """
    feasible = [r for r in results if r.is_feasible]
    rationale: List[str] = []

    for solver in (r for r in results if not r.is_feasible):
        rationale.append(
            f"{solver.display_name} excluded - infeasible ({solver.feasibility_reason})"
        )

    if not feasible:
        rationale.append(
            "No solver produced a feasible plan; the constraints are mutually "
            "unsatisfiable. Relax the time budget or enable SOFT/OPTIONAL prerequisites."
        )
        return None, rationale

    best = min(
        feasible,
        key=lambda r: (
            -r.path_score,
            -r.net_utility,
            r.total_time_minutes,
            r.execution_time_ms,
        ),
    )

    if len(feasible) == 1:
        rationale.append(
            f"{best.display_name} was the only feasible solver and is therefore optimal."
        )
    else:
        for other in (r for r in feasible if r.solver != best.solver):
            if abs(best.path_score - other.path_score) < 1e-9:
                rationale.append(
                    f"Tied with {other.display_name} on Path Score "
                    f"({best.path_score:.3f}); broken on net utility "
                    f"({best.net_utility:.3f} vs {other.net_utility:.3f})."
                )
            elif best.net_utility >= other.net_utility - 1e-9:
                rationale.append(
                    f"{best.display_name} wins on Path Score "
                    f"{best.path_score:.3f} vs {other.path_score:.3f} while matching "
                    f"or beating it on net utility ({best.net_utility:.3f} vs "
                    f"{other.net_utility:.3f}), covering {len(best.path_nodes)} nodes "
                    f"in {best.total_time_minutes} min versus "
                    f"{len(other.path_nodes)} nodes / {other.total_time_minutes} min."
                )
            else:
                rationale.append(
                    f"{best.display_name} leads on Path Score "
                    f"({best.path_score:.3f} vs {other.path_score:.3f}) but yields "
                    f"less net utility ({best.net_utility:.3f} vs "
                    f"{other.net_utility:.3f}); {other.display_name} covers "
                    f"{len(other.path_nodes) - len(best.path_nodes)} more concept(s) "
                    f"for {other.total_time_minutes - best.total_time_minutes:+d} min. "
                    "Prefer it if breadth matters more than ROI."
                )

    fastest = min(feasible, key=lambda r: r.execution_time_ms)
    slowest = max(feasible, key=lambda r: r.execution_time_ms)
    rationale.append(
        f"Runtime spread: {fastest.display_name} {fastest.execution_time_ms:.1f} ms "
        f"-> {slowest.display_name} {slowest.execution_time_ms:.1f} ms."
    )

    return best, rationale


def _recommendation(
    best: Optional[SolverMetrics],
    results: List[SolverMetrics],
    problem: OptimizationProblem,
) -> str:
    """One-paragraph narrative for the UI."""
    if best is None:
        return (
            "No feasible learning path exists under the current constraints. "
            "Relax the time budget or enable SOFT/OPTIONAL prerequisites."
        )

    node_count = len(best.path_nodes)
    hours = round(best.total_time_minutes / 60.0, 1)
    budget = problem.constraints.max_time_budget_minutes
    budget_note = (
        f", within the {budget} min budget" if budget else ""
    )
    hard_note = (
        f" This includes all {len(problem.hard_prerequisites)} mandatory HARD "
        "prerequisite(s), which no solver is permitted to skip."
        if problem.hard_prerequisites
        else ""
    )

    return (
        f"Recommended: {best.display_name}. It returns the highest Path Score "
        f"(ROI) of {best.path_score:.3f}, covering {node_count} concepts in "
        f"{best.total_time_minutes} minutes (~{hours} h){budget_note}, with an "
        f"average learning value of {best.average_learning_value:.3f} against a "
        f"total path cost of {best.total_path_cost:.3f}.{hard_note} "
        f"It solved in {best.execution_time_ms:.1f} ms."
    )


# ============================================================================
# EXPLANATION TEXT
# ============================================================================

def _explain_single(
    problem: OptimizationProblem,
    auto_decision,
    metrics: SolverMetrics,
    sequence: List[Dict[str, object]],
) -> str:
    lines: List[str] = []
    lines.append("# Learning Path Optimization")
    lines.append("")
    lines.append("## Search Strategy")
    lines.append(f"- Requested: {auto_decision.requested.value}")
    lines.append(f"- Selected: {auto_decision.selected.value}")
    lines.append(f"- Rationale: {auto_decision.reason}")
    lines.append("")
    lines.append("## Constraints")
    lines.append(f"- HARD prerequisites: {len(problem.hard_prerequisites)} (mandatory)")
    lines.append(
        f"- SOFT prerequisites: "
        f"{'enabled' if problem.constraints.include_soft else 'disabled'} "
        f"(skip penalty {problem.constraints.soft_skip_penalty})"
    )
    lines.append(
        f"- OPTIONAL prerequisites: "
        f"{'enabled' if problem.constraints.include_optional else 'disabled'}"
    )
    budget = problem.constraints.max_time_budget_minutes
    lines.append(
        f"- Time budget: {f'{budget} minutes' if budget else 'unconstrained'}"
    )
    lines.append("")
    lines.append("## Solver Result")
    lines.append(f"- Algorithm: {metrics.display_name}")
    lines.append(f"- Feasible: {metrics.is_feasible} — {metrics.feasibility_reason}")
    lines.append(f"- Path Score (ROI): {metrics.path_score}")
    lines.append(f"- Total Path Cost: {metrics.total_path_cost}")
    lines.append(f"- Average Learning Value: {metrics.average_learning_value}")
    lines.append(f"- Total Time: {metrics.total_time_minutes} minutes")
    lines.append(f"- Execution Time: {metrics.execution_time_ms} ms")
    lines.append("")
    lines.append(f"## Learning Sequence ({len(sequence)} steps)")
    for step in sequence:
        lock = " [HARD]" if step["is_hard_prerequisite"] else ""
        minutes = step["estimated_time_minutes"]
        lines.append(
            f"{step['step']}. {step['name']}{lock} — "
            f"value {step['learning_value']}, ~{minutes} min"
        )

    return "\n".join(lines)
