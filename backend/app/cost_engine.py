"""
Runtime cost & score engine.

ALL derived quantities are computed per-request against the retrieved subgraph
and are never written back to Neo4j:

    Normalized Time           = edge_time / max_subgraph_edge_time
    Normalized Cognitive Effort = edge_effort / 5.0
    Edge Cost                 = (Normalized Time + Normalized Cognitive Effort) / 2.0
    Node Learning Value       = (target_relevance + downstream_utility) / 2.0
    Path Score                = Average Learning Value / (Total Path Cost + 0.01)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

import networkx as nx

from app.schemas import (
    ConstraintConfig,
    EdgeMetrics,
    NodeMetrics,
    PrerequisiteType,
    RelationshipType,
)

COGNITIVE_EFFORT_SCALE = 5.0
SCORE_EPSILON = 0.01


# ============================================================================
# PROBLEM CONTEXT
# ============================================================================

@dataclass
class OptimizationProblem:
    """
    Fully-materialised, solver-agnostic view of a target-specific subgraph.

    This is the single object every solver consumes, which is what makes the
    Greedy / DP / ILP comparison apples-to-apples.
    """

    target_id: str
    graph: nx.DiGraph
    nodes: Dict[str, NodeMetrics]
    edges: Dict[str, EdgeMetrics]
    hard_prerequisites: Set[str]
    constraints: ConstraintConfig
    max_edge_time: int

    # Incoming prerequisite edges keyed by dependent node.
    incoming: Dict[str, List[str]] = field(default_factory=dict)
    # Outgoing dependent edges keyed by prerequisite node.
    outgoing: Dict[str, List[str]] = field(default_factory=dict)
    # node -> edge ids actually used to "reach" the node in the final path.
    prerequisite_only: nx.DiGraph = field(default_factory=nx.DiGraph)
    # (source, target) -> EdgeMetrics index. Relationship ids are user-supplied
    # and are NOT derivable from endpoints, so endpoints need their own index.
    edge_index: Dict[Tuple[str, str], EdgeMetrics] = field(default_factory=dict)

    def edge_between(self, source: str, target: str) -> Optional[EdgeMetrics]:
        return self.edge_index.get((source, target))

    def prereq_parents(self, node_id: str) -> List[Tuple[str, EdgeMetrics]]:
        """(prerequisite_id, edge_metrics) pairs for a node."""
        result: List[Tuple[str, EdgeMetrics]] = []
        for edge_id in self.incoming.get(node_id, []):
            edge = self.edges[edge_id]
            result.append((edge.source, edge))
        return result

    def topological_order(self) -> List[str]:
        """Kahn's algorithm (NetworkX) over prerequisite edges only."""
        return list(nx.topological_sort(self.prerequisite_only))


# ============================================================================
# METRIC COMPUTATION
# ============================================================================

def build_problem(
    graph: nx.DiGraph,
    target_id: str,
    constraints: ConstraintConfig,
) -> OptimizationProblem:
    """Compute all runtime metrics and assemble the shared problem context."""
    # ---- Edge normalisation ---------------------------------------------
    edge_times = [
        int(data.get("time_required_minutes") or 1) for _u, _v, data in graph.edges(data=True)
    ]
    max_edge_time = max(edge_times) if edge_times else 1

    nodes: Dict[str, NodeMetrics] = {}
    for node_id, data in graph.nodes(data=True):
        relevance = float(data.get("target_relevance") or 0.0)
        utility = float(data.get("downstream_utility") or 0.0)
        nodes[node_id] = NodeMetrics(
            node_id=node_id,
            name=data.get("name") or node_id,
            description=data.get("description") or "",
            target_relevance=relevance,
            downstream_utility=utility,
            learning_value=(relevance + utility) / 2.0,
            is_hard_prerequisite=False,
            skip_penalty=0.0,
        )

    edges: Dict[str, EdgeMetrics] = {}
    incoming: Dict[str, List[str]] = {node_id: [] for node_id in nodes}
    outgoing: Dict[str, List[str]] = {node_id: [] for node_id in nodes}
    edge_index: Dict[Tuple[str, str], EdgeMetrics] = {}
    prerequisite_only = nx.DiGraph()
    prerequisite_only.add_nodes_from(nodes)

    for source, target, data in graph.edges(data=True):
        raw_time = int(data.get("time_required_minutes") or 1)
        raw_effort = int(data.get("cognitive_effort") or 1)
        normalized_time = raw_time / max_edge_time if max_edge_time else 0.0
        normalized_effort = raw_effort / COGNITIVE_EFFORT_SCALE
        edge_cost = (normalized_time + normalized_effort) / 2.0

        rel_type = data.get("type") or RelationshipType.PART_OF.value
        prereq_type = data.get("prerequisite_type")

        metrics = EdgeMetrics(
            edge_id=str(data.get("id") or f"{source}->{target}"),
            source=source,
            target=target,
            relationship_type=RelationshipType(rel_type),
            prerequisite_type=PrerequisiteType(prereq_type) if prereq_type else None,
            raw_time_minutes=raw_time,
            raw_cognitive_effort=raw_effort,
            normalized_time=normalized_time,
            normalized_cognitive_effort=normalized_effort,
            edge_cost=edge_cost,
        )
        edges[metrics.edge_id] = metrics
        edge_index[(source, target)] = metrics

        if rel_type == RelationshipType.PREREQUISITE_OF.value:
            incoming[target].append(metrics.edge_id)
            outgoing[source].append(metrics.edge_id)
            prerequisite_only.add_edge(source, target, edge_id=metrics.edge_id)
            nodes[target].incoming_edge_ids.append(metrics.edge_id)

    # ---- Constraint-aware attributes ------------------------------------
    problem = OptimizationProblem(
        target_id=target_id,
        graph=graph,
        nodes=nodes,
        edges=edges,
        hard_prerequisites=set(),
        constraints=constraints,
        max_edge_time=max_edge_time,
        incoming=incoming,
        outgoing=outgoing,
        prerequisite_only=prerequisite_only,
        edge_index=edge_index,
    )

    _apply_constraint_attributes(problem)
    return problem


def _apply_constraint_attributes(problem: OptimizationProblem) -> None:
    """
    Attach constraint-driven per-node attributes.

    * HARD prerequisite nodes are flagged mandatory.
    * Skipping a SOFT prerequisite costs ``soft_skip_penalty`` in cognitive
      effort, which is folded into that node's own effective cost so solvers
      see the price of leaving it out.
    * OPTIONAL prerequisites are free to skip (penalty 0).
    """
    from app.graph_service import hard_prerequisite_closure

    problem.hard_prerequisites = hard_prerequisite_closure(
        problem.graph, problem.target_id
    )

    for node_id in problem.hard_prerequisites:
        if node_id in problem.nodes:
            problem.nodes[node_id].is_hard_prerequisite = True

    # A node is "skippable-with-penalty" if it is a SOFT prerequisite of a
    # selected node. Attribute the penalty to the prerequisite itself.
    for dependent_id, edge_ids in problem.incoming.items():
        for edge_id in edge_ids:
            edge = problem.edges[edge_id]
            if edge.prerequisite_type == PrerequisiteType.SOFT:
                node = problem.nodes.get(edge.source)
                if node:
                    node.skip_penalty = problem.constraints.soft_skip_penalty


# ============================================================================
# SCORING
# ============================================================================

def path_cost(problem: OptimizationProblem, path_nodes: Set[str]) -> float:
    """Sum of edge costs for prerequisite edges inside the selected set."""
    total = 0.0
    for source, target in problem.prerequisite_only.edges():
        if source in path_nodes and target in path_nodes:
            edge = problem.edge_between(source, target)
            if edge:
                total += edge.edge_cost
    return total


def path_raw_time(problem: OptimizationProblem, path_nodes: Set[str]) -> int:
    """Sum of raw minutes for prerequisite edges inside the selected set."""
    total = 0
    for source, target in problem.prerequisite_only.edges():
        if source in path_nodes and target in path_nodes:
            edge = problem.edge_between(source, target)
            if edge:
                total += edge.raw_time_minutes
    return total


def average_learning_value(problem: OptimizationProblem, path_nodes: Set[str]) -> float:
    if not path_nodes:
        return 0.0
    values = [
        problem.nodes[n].learning_value for n in path_nodes if n in problem.nodes
    ]
    return sum(values) / len(values) if values else 0.0


def path_score(
    problem: OptimizationProblem, path_nodes: Set[str]
) -> float:
    """
    Path Score (ROI) as specified:

        Path Score = Average Learning Value / (Total Path Cost + 0.01)

    IMPORTANT — this is a *reporting / ranking* metric, never an optimisation
    objective. It is strictly decreasing in cost for a fixed learning value,
    so maximising it directly is degenerate: the optimum is always "select
    nothing". Solver selection therefore optimises :func:`net_utility`
    (value − cost), which is well-posed, and Path Score is used only to rank
    and compare the plans the solvers actually produced.
    """
    value = average_learning_value(problem, path_nodes)
    cost = path_cost(problem, path_nodes)
    return value / (cost + SCORE_EPSILON)


def net_utility(problem: OptimizationProblem, path_nodes: Set[str]) -> float:
    """
    Well-posed selection objective:

        Net Utility = Σ LearningValue(v) − Σ EdgeCost(e) − Σ skip penalties

    Unlike the Path Score ratio this is additive and strictly rewards pulling
    in a prerequisite whose value exceeds its cost, while penalising one whose
    cost exceeds its value. It cannot be gamed by returning the empty set.
    """
    total_value = sum(
        problem.nodes[n].learning_value for n in path_nodes if n in problem.nodes
    )
    total_cost = 0.0
    for source, target in problem.prerequisite_only.edges():
        if source in path_nodes and target in path_nodes:
            edge = problem.edge_between(source, target)
            if edge:
                total_cost += edge.edge_cost

    # Charge the configured penalty for every SOFT prerequisite left uncovered.
    #
    # Only SOFT edges that are actually enabled are counted: when include_soft
    # is False the user has switched recommended prerequisites off entirely, so
    # charging a penalty for "skipping" them would be incoherent (and would
    # disagree with the ILP, which omits disabled edges from its model).
    uncovered_soft = [
        edge
        for edge in problem.edges.values()
        if edge.prerequisite_type == PrerequisiteType.SOFT
        and edge.target in path_nodes
        and edge.source not in path_nodes
    ] if problem.constraints.include_soft else []

    penalty = problem.constraints.soft_skip_penalty * len(uncovered_soft)

    return total_value - total_cost - penalty


def supported_nodes(
    problem: OptimizationProblem, path_nodes: Set[str]
) -> Set[str]:
    """
    Nodes that actually *enable* something else in the plan.

    A selected node counts as supported when at least one prerequisite edge from
    it into another selected node is traversed. The target is supported by
    definition.

    Rationale: ``downstream_utility`` describes value for topics that come
    later. If nothing later in the plan depends on a concept, studying it
    contributes learning value while incurring no prerequisite-edge cost — pure
    free value. Empirically this makes the optimiser attach unrelated ancestors
    (their whole chains skipped) purely to harvest that free value. Restricting
    the plan to supported nodes models a real learning path: every concept is
    learned because something in the plan needs it.
    """
    supported: Set[str] = {problem.target_id}
    for source, target in problem.prerequisite_only.edges():
        if source in path_nodes and target in path_nodes:
            supported.add(source)
    return supported


def validate_solution(
    problem: OptimizationProblem, path_nodes: Set[str]
) -> Tuple[bool, str]:
    """
    Feasibility check shared by all three solvers.

    Enforces:
      1. Target must be present.
      2. Every HARD prerequisite closure must be covered.
      3. Every HARD prerequisite of a selected node must itself be selected.
      4. Every selected non-target node must support another selected node.
      5. Time budget must not be exceeded.
    """
    if problem.target_id not in path_nodes:
        return False, "Target node is not part of the selected path."

    missing_hard = problem.hard_prerequisites - path_nodes
    if missing_hard:
        names = [problem.nodes[m].name for m in sorted(missing_hard) if m in problem.nodes]
        return False, f"HARD prerequisites not satisfied: {', '.join(names[:8])}"

    for node_id in path_nodes:
        for source, edge in problem.prereq_parents(node_id):
            if (
                edge.prerequisite_type == PrerequisiteType.HARD
                and source not in path_nodes
            ):
                return False, f"Closed-set violation: {source} required by {node_id}"

    unsupported = set(path_nodes) - supported_nodes(problem, path_nodes)
    if unsupported:
        names = [problem.nodes[u].name for u in sorted(unsupported) if u in problem.nodes]
        return False, (
            "Selected nodes support nothing in the plan (no selected topic "
            f"depends on them): {', '.join(names[:6])}"
        )

    budget = problem.constraints.max_time_budget_minutes
    if budget is not None:
        used = path_raw_time(problem, path_nodes)
        if used > budget:
            return False, f"Time budget exceeded: {used} min > {budget} min limit."

    return True, "Valid: all HARD prerequisites covered and budget respected."


def collect_used_edges(
    problem: OptimizationProblem, path_nodes: Set[str]
) -> List[str]:
    """Edge ids of prerequisite edges fully inside the selected set."""
    used: List[str] = []
    for source, target in problem.prerequisite_only.edges():
        if source in path_nodes and target in path_nodes:
            edge = problem.edge_between(source, target)
            if edge:
                used.append(edge.edge_id)
    return used
