"""Topological sorting for final learning path ordering."""

from typing import List, Dict, Set, Tuple
from collections import deque
from app.models import NodeResponse, RelationshipResponse


def topological_sort(
    nodes: List[NodeResponse],
    edges: List[RelationshipResponse],
    selected_nodes: Set[str]
) -> List[str]:
    """
    Perform topological sort on the selected subgraph to get learning order.
    
    Uses Kahn's algorithm (BFS-based) for topological sorting.
    Only includes edges where both source and target are selected.
    """
    # Build adjacency and in-degree for selected nodes only
    adj: Dict[str, List[str]] = {n.id: [] for n in nodes if n.id in selected_nodes}
    in_degree: Dict[str, int] = {n.id: 0 for n in nodes if n.id in selected_nodes}
    
    # Filter edges to only include selected nodes
    selected_edges = [
        e for e in edges 
        if e.source in selected_nodes and e.target in selected_nodes
    ]
    
    for edge in selected_edges:
        adj[edge.source].append(edge.target)
        in_degree[edge.target] = in_degree.get(edge.target, 0) + 1
    
    # Kahn's algorithm
    queue = deque([node_id for node_id, deg in in_degree.items() if deg == 0])
    topo_order = []
    
    while queue:
        node = queue.popleft()
        topo_order.append(node)
        
        for neighbor in adj.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    
    # Check for cycles (should not happen if validation passed)
    if len(topo_order) != len(selected_nodes):
        # Fallback: return nodes in any order
        return list(selected_nodes)
    
    return topo_order


def build_final_path(
    topo_order: List[str],
    nodes: List[NodeResponse],
    edges: List[RelationshipResponse],
    edge_costs: List,
    node_metrics: List,
    dp_result
) -> List[Dict]:
    """Build the final learning path with all metadata for visualization."""
    node_lookup = {n.id: n for n in nodes}
    edge_cost_lookup = {ec.edge_id: ec for ec in edge_costs}
    metric_lookup = {m.node_id: m for m in node_metrics}
    
    # Build edge lookup for quick access
    edge_lookup: Dict[str, List[RelationshipResponse]] = {}
    for edge in edges:
        if edge.target not in edge_lookup:
            edge_lookup[edge.target] = []
        edge_lookup[edge.target].append(edge)
    
    path = []
    for i, node_id in enumerate(topo_order):
        node = node_lookup.get(node_id)
        metric = metric_lookup.get(node_id)
        
        if not node:
            continue
        
        # Get prerequisites for this node (incoming edges from selected nodes)
        prerequisites = []
        if node_id in edge_lookup:
            for edge in edge_lookup[node_id]:
                if edge.source in metric_lookup and metric_lookup[edge.source].is_selected:
                    ec = edge_cost_lookup.get(edge.id)
                    prerequisites.append({
                        "edge_id": edge.id,
                        "source": edge.source,
                        "source_name": node_lookup[edge.source].name if edge.source in node_lookup else edge.source,
                        "relationship_type": edge.type.value,
                        "prerequisite_type": edge.prerequisite_type.value if edge.prerequisite_type else None,
                        "time_required_minutes": edge.time_required_minutes,
                        "cognitive_effort": edge.cognitive_effort,
                        "normalized_time": ec.normalized_time if ec else 0,
                        "normalized_cognitive_effort": ec.normalized_cognitive_effort if ec else 0,
                        "edge_cost": ec.edge_cost if ec else 0,
                    })
        
        path.append({
            "step": i + 1,
            "node_id": node.id,
            "name": node.name,
            "description": node.description,
            "target_relevance": node.target_relevance,
            "downstream_utility": node.downstream_utility,
            "learning_value": metric.learning_value if metric else 0,
            "total_incoming_cost": metric.total_incoming_cost if metric else 0,
            "is_hard_prerequisite": metric.is_hard_prerequisite if metric else False,
            "is_selected": metric.is_selected if metric else False,
            "prerequisites": prerequisites,
            "estimated_time_minutes": sum(p["time_required_minutes"] for p in prerequisites)
        })
    
    return path