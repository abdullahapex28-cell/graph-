"""Graph validation logic for the Knowledge Graph."""

from typing import List, Set, Dict, Tuple
from app.models import ValidationResult
from app.database import get_session


async def validate_graph() -> ValidationResult:
    """
    Validate the entire knowledge graph for:
    - Duplicate node IDs
    - Duplicate relationship IDs
    - Self-loops
    - Prerequisite cycles
    """
    errors = []
    warnings = []

    async with get_session() as session:
        # Check duplicate node IDs
        result = await session.run("""
            MATCH (n:Concept)
            WITH n.id as id, count(*) as cnt
            WHERE cnt > 1
            RETURN id, cnt
        """)
        duplicates = await result.data()
        for dup in duplicates:
            errors.append(f"Duplicate node ID: {dup['id']} (count: {dup['cnt']})")

        # Check duplicate relationship IDs
        result = await session.run("""
            MATCH ()-[r:RELATES_TO]->()
            WITH r.id as id, count(*) as cnt
            WHERE cnt > 1
            RETURN id, cnt
        """)
        duplicates = await result.data()
        for dup in duplicates:
            errors.append(f"Duplicate relationship ID: {dup['id']} (count: {dup['cnt']})")

        # Check self-loops
        result = await session.run("""
            MATCH (n:Concept)-[r:RELATES_TO]->(n)
            RETURN n.id as node_id, r.id as rel_id
        """)
        self_loops = await result.data()
        for loop in self_loops:
            errors.append(f"Self-loop detected: node {loop['node_id']} via relationship {loop['rel_id']}")

        # Check prerequisite cycles (only PREREQUISITE_OF edges)
        result = await session.run("""
            MATCH path = (n:Concept)-[:RELATES_TO*]->(n)
            WHERE ALL(r IN relationships(path) WHERE r.type = 'PREREQUISITE_OF')
            RETURN [n IN nodes(path) | n.id] as cycle_nodes,
                   [r IN relationships(path) | r.id] as cycle_edges
            LIMIT 10
        """)
        cycles = await result.data()
        for cycle in cycles:
            errors.append(f"Prerequisite cycle detected: {' -> '.join(cycle['cycle_nodes'])}")

        # Warning: nodes with no connections
        result = await session.run("""
            MATCH (n:Concept)
            WHERE NOT (n)-[:RELATES_TO]-()
            RETURN n.id as node_id, n.name as node_name
        """)
        isolated = await result.data()
        for node in isolated:
            warnings.append(f"Isolated node (no relationships): {node['node_id']} ({node['node_name']})")

        # Warning: PREREQUISITE_OF without prerequisite_type
        result = await session.run("""
            MATCH ()-[r:RELATES_TO]->()
            WHERE r.type = 'PREREQUISITE_OF' AND r.prerequisite_type IS NULL
            RETURN r.id as rel_id, r.source as source, r.target as target
        """)
        missing_type = await result.data()
        for rel in missing_type:
            warnings.append(f"PREREQUISITE_OF missing prerequisite_type: {rel['rel_id']} ({rel['source']} -> {rel['target']})")

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


async def validate_target_exists(target_node_id: str) -> Tuple[bool, str]:
    """Check if target node exists in the graph."""
    async with get_session() as session:
        result = await session.run(
            "MATCH (n:Concept {id: $id}) RETURN n.id as id",
            id=target_node_id
        )
        record = await result.single()
        if record:
            return True, ""
        return False, f"Target node '{target_node_id}' not found in graph"