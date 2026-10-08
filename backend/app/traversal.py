"""Graph traversal algorithms (Reverse DFS/BFS) for subgraph extraction."""

from typing import List, Set, Dict, Tuple, Optional
from collections import deque
from app.models import SearchMethod, TraversalExplanation
from app.database import get_session


async def reverse_traversal(
    target_node_id: str,
    method: SearchMethod = SearchMethod.DFS,
    max_depth: Optional[int] = None
) -> Tuple[Set[str], Set[str], List[str], TraversalExplanation]:
    """
    Perform reverse traversal (from target to ancestors) to extract relevant subgraph.
    
    Returns:
        - visited_nodes: Set of node IDs in the subgraph
        - visited_edges: Set of relationship IDs in the subgraph
        - traversal_order: Order in which nodes were visited
        - explanation: TraversalExplanation object with details
    """
    visited_nodes: Set[str] = set()
    visited_edges: Set[str] = set()
    traversal_order: List[str] = []
    nodes_pruned = 0
    max_depth_reached = 0

    async with get_session() as session:
        # Get all incoming relationships for traversal
        # We need to traverse REVERSE: from target to prerequisites (incoming edges)
        result = await session.run("""
            MATCH (source:Concept)-[r:RELATES_TO]->(target:Concept)
            WHERE target.id = $target_id
            RETURN source.id as source_id, r.id as rel_id, r.type as rel_type,
                   r.prerequisite_type as prereq_type, r.time_required_minutes as time,
                   r.cognitive_effort as effort
        """, target_id=target_node_id)
        
        incoming_edges = await result.data()
        
        if not incoming_edges:
            # Target has no prerequisites
            visited_nodes.add(target_node_id)
            traversal_order.append(target_node_id)
            explanation = TraversalExplanation(
                method=method,
                visited_nodes=list(visited_nodes),
                visited_edges=list(visited_edges),
                traversal_order=traversal_order,
                max_depth_reached=0,
                nodes_pruned=0
            )
            return visited_nodes, visited_edges, traversal_order, explanation

        # Build adjacency list for reverse traversal (target -> prerequisites)
        # For reverse traversal: we follow edges backwards (target <- source)
        adj: Dict[str, List[Dict]] = {}
        for edge in incoming_edges:
            source = edge['source_id']
            target = target_node_id
            if target not in adj:
                adj[target] = []
            adj[target].append({
                'neighbor': source,
                'rel_id': edge['rel_id'],
                'rel_type': edge['rel_type'],
                'prereq_type': edge['prereq_type'],
                'time': edge['time'],
                'effort': edge['effort']
            })

        # We need to recursively get all incoming edges for all visited nodes
        # Let's fetch all edges first, then traverse
        result = await session.run("""
            MATCH (source:Concept)-[r:RELATES_TO]->(target:Concept)
            RETURN source.id as source_id, target.id as target_id, 
                   r.id as rel_id, r.type as rel_type,
                   r.prerequisite_type as prereq_type, 
                   r.time_required_minutes as time,
                   r.cognitive_effort as effort
        """)
        all_edges = await result.data()

        # Build full adjacency for reverse traversal
        full_adj: Dict[str, List[Dict]] = {}
        for edge in all_edges:
            target = edge['target_id']
            source = edge['source_id']
            if target not in full_adj:
                full_adj[target] = []
            full_adj[target].append({
                'neighbor': source,
                'rel_id': edge['rel_id'],
                'rel_type': edge['rel_type'],
                'prereq_type': edge['prereq_type'],
                'time': edge['time'],
                'effort': edge['effort']
            })

        # Perform traversal
        if method == SearchMethod.DFS:
            visited_nodes, visited_edges, traversal_order, max_depth_reached, nodes_pruned = \
                await _dfs_reverse(target_node_id, full_adj, max_depth)
        else:
            visited_nodes, visited_edges, traversal_order, max_depth_reached, nodes_pruned = \
                await _bfs_reverse(target_node_id, full_adj, max_depth)

        # Always include the target node
        visited_nodes.add(target_node_id)
        if target_node_id not in traversal_order:
            traversal_order.insert(0, target_node_id)

    explanation = TraversalExplanation(
        method=method,
        visited_nodes=list(visited_nodes),
        visited_edges=list(visited_edges),
        traversal_order=traversal_order,
        max_depth_reached=max_depth_reached,
        nodes_pruned=nodes_pruned
    )

    return visited_nodes, visited_edges, traversal_order, explanation


async def _dfs_reverse(
    start_node: str,
    adj: Dict[str, List[Dict]],
    max_depth: Optional[int]
) -> Tuple[Set[str], Set[str], List[str], int, int]:
    """Reverse Depth-First Search traversal."""
    visited_nodes: Set[str] = set()
    visited_edges: Set[str] = set()
    traversal_order: List[str] = []
    max_depth_reached = 0
    nodes_pruned = 0

    def dfs(node: str, depth: int):
        nonlocal max_depth_reached, nodes_pruned
        
        if max_depth is not None and depth > max_depth:
            nodes_pruned += 1
            return
        
        if node in visited_nodes:
            return
        
        visited_nodes.add(node)
        traversal_order.append(node)
        max_depth_reached = max(max_depth_reached, depth)

        if node in adj:
            for edge in adj[node]:
                visited_edges.add(edge['rel_id'])
                dfs(edge['neighbor'], depth + 1)

    dfs(start_node, 0)
    return visited_nodes, visited_edges, traversal_order, max_depth_reached, nodes_pruned


async def _bfs_reverse(
    start_node: str,
    adj: Dict[str, List[Dict]],
    max_depth: Optional[int]
) -> Tuple[Set[str], Set[str], List[str], int, int]:
    """Reverse Breadth-First Search traversal."""
    visited_nodes: Set[str] = set()
    visited_edges: Set[str] = set()
    traversal_order: List[str] = []
    max_depth_reached = 0
    nodes_pruned = 0

    queue = deque([(start_node, 0)])
    
    while queue:
        node, depth = queue.popleft()
        
        if max_depth is not None and depth > max_depth:
            nodes_pruned += 1
            continue
        
        if node in visited_nodes:
            continue
        
        visited_nodes.add(node)
        traversal_order.append(node)
        max_depth_reached = max(max_depth_reached, depth)

        if node in adj:
            for edge in adj[node]:
                visited_edges.add(edge['rel_id'])
                if edge['neighbor'] not in visited_nodes:
                    queue.append((edge['neighbor'], depth + 1))

    return visited_nodes, visited_edges, traversal_order, max_depth_reached, nodes_pruned


async def get_subgraph_data(
    node_ids: Set[str],
    edge_ids: Set[str]
) -> Tuple[List[Dict], List[Dict]]:
    """Fetch full node and relationship data for the subgraph."""
    async with get_session() as session:
        # Get nodes
        nodes_result = await session.run("""
            MATCH (n:Concept)
            WHERE n.id IN $node_ids
            RETURN n.id as id, n.name as name, n.description as description,
                   n.target_relevance as target_relevance, n.downstream_utility as downstream_utility
        """, node_ids=list(node_ids))
        nodes = await nodes_result.data()

        # Get edges
        edges_result = await session.run("""
            MATCH (source:Concept)-[r:RELATES_TO]->(target:Concept)
            WHERE r.id IN $edge_ids
            RETURN r.id as id, r.type as type, r.prerequisite_type as prerequisite_type,
                   r.time_required_minutes as time_required_minutes,
                   r.cognitive_effort as cognitive_effort,
                   source.id as source, target.id as target
        """, edge_ids=list(edge_ids))
        edges = await edges_result.data()

    return nodes, edges