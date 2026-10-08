"""Runtime cost calculations for edges in the subgraph."""

from typing import List, Dict, Tuple
from app.models import EdgeCostCalculation, NodeMetrics, RelationshipResponse, NodeResponse


def calculate_edge_costs(
    edges: List[RelationshipResponse],
    nodes: List[NodeResponse]
) -> List[EdgeCostCalculation]:
    """
    Calculate normalized costs for all edges in the subgraph.
    
    Normalization is done relative to the maximum values in the relevant candidate edges.
    """
    if not edges:
        return []

    # Find max time in subgraph
    max_time = max(edge.time_required_minutes for edge in edges)
    max_cognitive = 5  # Fixed max for cognitive effort (1-5 scale)

    # Create node lookup for learning value calculation
    node_lookup = {node.id: node for node in nodes}

    edge_costs = []
    for edge in edges:
        # Normalized time: edge time / max time in subgraph
        normalized_time = edge.time_required_minutes / max_time if max_time > 0 else 0
        
        # Normalized cognitive effort: edge effort / 5 (max scale)
        normalized_cognitive_effort = edge.cognitive_effort / max_cognitive
        
        # Edge cost: average of normalized time and cognitive effort
        edge_cost = (normalized_time + normalized_cognitive_effort) / 2
        
        # Learning value of target node: (target_relevance + downstream_utility) / 2
        target_node = node_lookup.get(edge.target)
        if target_node:
            learning_value = (target_node.target_relevance + target_node.downstream_utility) / 2
        else:
            learning_value = 0.5  # Default if node not found

        edge_costs.append(EdgeCostCalculation(
            edge_id=edge.id,
            source=edge.source,
            target=edge.target,
            time_required_minutes=edge.time_required_minutes,
            cognitive_effort=edge.cognitive_effort,
            normalized_time=normalized_time,
            normalized_cognitive_effort=normalized_cognitive_effort,
            edge_cost=edge_cost,
            learning_value=learning_value
        ))

    return edge_costs


def calculate_node_metrics(
    nodes: List[NodeResponse],
    edges: List[RelationshipResponse],
    edge_costs: List[EdgeCostCalculation],
    hard_prerequisites: set
) -> List[NodeMetrics]:
    """Calculate metrics for each node in the subgraph."""
    # Build incoming edge cost lookup
    incoming_costs: Dict[str, float] = {}
    for ec in edge_costs:
        if ec.target not in incoming_costs:
            incoming_costs[ec.target] = 0
        incoming_costs[ec.target] += ec.edge_cost

    node_metrics = []
    for node in nodes:
        is_hard = node.id in hard_prerequisites
        total_incoming = incoming_costs.get(node.id, 0)
        learning_value = (node.target_relevance + node.downstream_utility) / 2
        
        node_metrics.append(NodeMetrics(
            node_id=node.id,
            name=node.name,
            target_relevance=node.target_relevance,
            downstream_utility=node.downstream_utility,
            learning_value=learning_value,
            total_incoming_cost=total_incoming,
            is_hard_prerequisite=is_hard,
            is_selected=False  # Will be updated after DP
        ))

    return node_metrics


def identify_hard_prerequisites(
    edges: List[RelationshipResponse],
    target_node_id: str
) -> set:
    """
    Identify all nodes that are HARD prerequisites (transitive closure).
    HARD prerequisites are mandatory and cannot be skipped.
    """
    hard_nodes = set()
    
    # Build adjacency for prerequisite traversal
    prereq_adj: Dict[str, List[Tuple[str, str]]] = {}  # target -> [(source, prereq_type)]
    for edge in edges:
        if edge.type.value == "PREREQUISITE_OF" and edge.prerequisite_type:
            if edge.target not in prereq_adj:
                prereq_adj[edge.target] = []
            prereq_adj[edge.target].append((edge.source, edge.prerequisite_type.value))

    # DFS to find all HARD prerequisites (transitive)
    def collect_hard(node: str):
        if node in prereq_adj:
            for prereq, ptype in prereq_adj[node]:
                if ptype == "HARD":
                    if prereq not in hard_nodes:
                        hard_nodes.add(prereq)
                        collect_hard(prereq)
                elif ptype == "SOFT":
                    # SOFT prerequisites are not mandatory but we track them
                    pass

    collect_hard(target_node_id)
    return hard_nodes