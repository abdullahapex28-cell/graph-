"""Dynamic Programming optimization for learning path selection."""

from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass
from app.models import (
    DPResult, EdgeCostCalculation, NodeMetrics, 
    RelationshipResponse, PrerequisiteType
)
from app.cost_calculator import identify_hard_prerequisites


@dataclass
class DPState:
    """State for DP optimization."""
    selected: Set[str]
    total_cost: float
    total_value: float
    net_score: float
    valid: bool


def dp_optimize(
    target_node_id: str,
    nodes: List[NodeMetrics],
    edges: List[RelationshipResponse],
    edge_costs: List[EdgeCostCalculation],
    include_soft: bool = True,
    include_optional: bool = True
) -> DPResult:
    """
    Global DP optimization to select the optimal set of nodes.
    
    - HARD prerequisites are MANDATORY (always included)
    - SOFT prerequisites: included if value > cost (configurable)
    - OPTIONAL prerequisites: included if value > cost (configurable)
    
    Uses a knapsack-like DP approach on the DAG structure.
    """
    # Identify mandatory HARD prerequisites
    hard_prereqs = identify_hard_prerequisites(edges, target_node_id)
    
    # Build node lookup
    node_lookup = {n.node_id: n for n in nodes}
    edge_cost_lookup = {ec.edge_id: ec for ec in edge_costs}
    
    # Build prerequisite graph (target -> prerequisites)
    prereq_graph: Dict[str, List[Tuple[str, str, str]]] = {}  # target -> [(source, prereq_type, edge_id)]
    for edge in edges:
        if edge.type.value == "PREREQUISITE_OF":
            if edge.target not in prereq_graph:
                prereq_graph[edge.target] = []
            prereq_graph[edge.target].append((edge.source, edge.prerequisite_type.value if edge.prerequisite_type else "HARD", edge.id))

    # Topological sort of the prerequisite subgraph
    topo_order = _topological_sort_prereqs(target_node_id, prereq_graph, nodes)
    
    # DP: For each node in topological order, decide whether to include it
    # State: best net_score achievable for each subset of prerequisites
    # Since this is a DAG, we can use DP on the topological order
    
    # For each node, we compute the best decision (include/exclude) based on its prerequisites
    # HARD prerequisites are forced to be included
    
    selected = set(hard_prereqs)
    selected.add(target_node_id)  # Target is always selected
    
    optimization_steps = []
    
    # Process nodes in topological order (prerequisites first)
    for node_id in topo_order:
        if node_id == target_node_id:
            continue
            
        node = node_lookup.get(node_id)
        if not node:
            continue
            
        # Check if this node is a prerequisite of any selected node
        is_required = _is_required_for_selected(node_id, selected, prereq_graph)
        
        if node_id in hard_prereqs:
            # HARD: must include
            if node_id not in selected:
                selected.add(node_id)
                optimization_steps.append({
                    "node": node_id,
                    "name": node.name,
                    "decision": "INCLUDED (HARD prerequisite)",
                    "reason": "Mandatory HARD prerequisite"
                })
        elif is_required:
            # This node is a prerequisite (SOFT/OPTIONAL) of an already selected node
            prereq_type = _get_prereq_type(node_id, selected, prereq_graph)
            
            if prereq_type == "SOFT" and not include_soft:
                optimization_steps.append({
                    "node": node_id,
                    "name": node.name,
                    "decision": "EXCLUDED (SOFT disabled)",
                    "reason": "SOFT prerequisites disabled in config"
                })
                continue
            elif prereq_type == "OPTIONAL" and not include_optional:
                optimization_steps.append({
                    "node": node_id,
                    "name": node.name,
                    "decision": "EXCLUDED (OPTIONAL disabled)",
                    "reason": "OPTIONAL prerequisites disabled in config"
                })
                continue
            
            # Calculate cost vs value for this prerequisite
            incoming_cost = node.total_incoming_cost
            node_value = node.learning_value
            
            # Net benefit of including this node
            net_benefit = node_value - incoming_cost
            
            if net_benefit > 0 or prereq_type == "SOFT":
                # Include if positive net benefit or if SOFT (SOFT has some value even if slightly negative)
                selected.add(node_id)
                optimization_steps.append({
                    "node": node_id,
                    "name": node.name,
                    "decision": "INCLUDED",
                    "reason": f"Net benefit: {net_benefit:.3f} (value: {node_value:.3f}, cost: {incoming_cost:.3f})",
                    "prerequisite_type": prereq_type,
                    "net_benefit": net_benefit
                })
            else:
                optimization_steps.append({
                    "node": node_id,
                    "name": node.name,
                    "decision": "EXCLUDED",
                    "reason": f"Negative net benefit: {net_benefit:.3f} (value: {node_value:.3f}, cost: {incoming_cost:.3f})",
                    "prerequisite_type": prereq_type,
                    "net_benefit": net_benefit
                })
        else:
            # Not required by any selected node - optional inclusion based on standalone value
            incoming_cost = node.total_incoming_cost
            node_value = node.learning_value
            net_benefit = node_value - incoming_cost
            
            if net_benefit > 0.1:  # Small threshold for standalone inclusion
                selected.add(node_id)
                optimization_steps.append({
                    "node": node_id,
                    "name": node.name,
                    "decision": "INCLUDED (standalone value)",
                    "reason": f"Positive standalone net benefit: {net_benefit:.3f}",
                    "net_benefit": net_benefit
                })
            else:
                optimization_steps.append({
                    "node": node_id,
                    "name": node.name,
                    "decision": "EXCLUDED (low standalone value)",
                    "reason": f"Insufficient standalone net benefit: {net_benefit:.3f}",
                    "net_benefit": net_benefit
                })

    # Calculate totals
    total_cost = sum(node_lookup[n].total_incoming_cost for n in selected if n in node_lookup)
    total_value = sum(node_lookup[n].learning_value for n in selected if n in node_lookup)
    net_score = total_value - total_cost

    # Update node metrics with selection status
    for node in nodes:
        node.is_selected = node.node_id in selected

    return DPResult(
        selected_nodes=list(selected),
        total_cost=total_cost,
        total_value=total_value,
        net_score=net_score,
        optimization_steps=optimization_steps
    )


def _topological_sort_prereqs(
    target: str,
    prereq_graph: Dict[str, List[Tuple[str, str, str]]],
    nodes: List[NodeMetrics]
) -> List[str]:
    """Topological sort of prerequisite subgraph (prerequisites before dependents)."""
    node_ids = {n.node_id for n in nodes}
    visited = set()
    temp = set()
    order = []
    
    def visit(node: str):
        if node in temp:
            return  # Cycle detected, but we validated earlier
        if node in visited:
            return
        temp.add(node)
        if node in prereq_graph:
            for prereq, _, _ in prereq_graph[node]:
                if prereq in node_ids:
                    visit(prereq)
        temp.remove(node)
        visited.add(node)
        order.append(node)
    
    visit(target)
    return order


def _is_required_for_selected(
    node_id: str,
    selected: Set[str],
    prereq_graph: Dict[str, List[Tuple[str, str, str]]]
) -> bool:
    """Check if node is a prerequisite (direct or transitive) of any selected node."""
    for sel in selected:
        if _is_prereq_of(node_id, sel, prereq_graph):
            return True
    return False


def _is_prereq_of(node: str, target: str, prereq_graph: Dict[str, List[Tuple[str, str, str]]]) -> bool:
    """Check if node is a prerequisite (transitive) of target."""
    if target not in prereq_graph:
        return False
    for prereq, _, _ in prereq_graph[target]:
        if prereq == node:
            return True
        if _is_prereq_of(node, prereq, prereq_graph):
            return True
    return False


def _get_prereq_type(
    node_id: str,
    selected: Set[str],
    prereq_graph: Dict[str, List[Tuple[str, str, str]]]
) -> str:
    """Get the prerequisite type for a node relative to selected nodes."""
    for sel in selected:
        if _is_prereq_of(node_id, sel, prereq_graph):
            # Find direct edge type
            if sel in prereq_graph:
                for prereq, ptype, _ in prereq_graph[sel]:
                    if prereq == node_id:
                        return ptype
                    # Check transitive
                    result = _get_prereq_type_transitive(node_id, prereq, prereq_graph)
                    if result:
                        return result
    return "UNKNOWN"


def _get_prereq_type_transitive(
    node: str,
    current: str,
    prereq_graph: Dict[str, List[Tuple[str, str, str]]]
) -> Optional[str]:
    if current not in prereq_graph:
        return None
    for prereq, ptype, _ in prereq_graph[current]:
        if prereq == node:
            return ptype
        result = _get_prereq_type_transitive(node, prereq, prereq_graph)
        if result:
            return result
    return None