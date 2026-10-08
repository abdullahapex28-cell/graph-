"""CRUD operations for nodes and relationships."""

from typing import List, Optional
from app.database import get_session
from app.models import (
    NodeCreate, NodeUpdate, NodeResponse,
    RelationshipCreate, RelationshipUpdate, RelationshipResponse,
    RelationshipType, PrerequisiteType
)


# Node CRUD
async def create_node(node: NodeCreate) -> NodeResponse:
    async with get_session() as session:
        result = await session.run("""
            CREATE (n:Concept {
                id: $id, name: $name, description: $description,
                target_relevance: $target_relevance, downstream_utility: $downstream_utility
            })
            RETURN n.id as id, n.name as name, n.description as description,
                   n.target_relevance as target_relevance, n.downstream_utility as downstream_utility
        """, **node.model_dump())
        record = await result.single()
        return NodeResponse(**record)


async def get_node(node_id: str) -> Optional[NodeResponse]:
    async with get_session() as session:
        result = await session.run("""
            MATCH (n:Concept {id: $id})
            RETURN n.id as id, n.name as name, n.description as description,
                   n.target_relevance as target_relevance, n.downstream_utility as downstream_utility
        """, id=node_id)
        record = await result.single()
        return NodeResponse(**record) if record else None


async def get_all_nodes() -> List[NodeResponse]:
    async with get_session() as session:
        result = await session.run("""
            MATCH (n:Concept)
            RETURN n.id as id, n.name as name, n.description as description,
                   n.target_relevance as target_relevance, n.downstream_utility as downstream_utility
            ORDER BY n.name
        """)
        records = await result.data()
        return [NodeResponse(**r) for r in records]


async def update_node(node_id: str, node: NodeUpdate) -> Optional[NodeResponse]:
    async with get_session() as session:
        # Build dynamic update query
        updates = []
        params = {"id": node_id}
        for field, value in node.model_dump(exclude_unset=True).items():
            updates.append(f"n.{field} = ${field}")
            params[field] = value
        
        if not updates:
            return await get_node(node_id)
        
        query = f"""
            MATCH (n:Concept {{id: $id}})
            SET {", ".join(updates)}
            RETURN n.id as id, n.name as name, n.description as description,
                   n.target_relevance as target_relevance, n.downstream_utility as downstream_utility
        """
        result = await session.run(query, params)
        record = await result.single()
        return NodeResponse(**record) if record else None


async def delete_node(node_id: str) -> bool:
    async with get_session() as session:
        result = await session.run("""
            MATCH (n:Concept {id: $id})
            DETACH DELETE n
            RETURN count(n) as deleted
        """, id=node_id)
        record = await result.single()
        return record['deleted'] > 0


# Relationship CRUD
async def create_relationship(rel: RelationshipCreate) -> RelationshipResponse:
    async with get_session() as session:
        # Verify source and target exist
        source_check = await session.run(
            "MATCH (n:Concept {id: $id}) RETURN n.id as id", id=rel.source
        )
        if not await source_check.single():
            raise ValueError(f"Source node '{rel.source}' does not exist")
        
        target_check = await session.run(
            "MATCH (n:Concept {id: $id}) RETURN n.id as id", id=rel.target
        )
        if not await target_check.single():
            raise ValueError(f"Target node '{rel.target}' does not exist")
        
        # Check for duplicate relationship (same source, target, type)
        dup_check = await session.run("""
            MATCH (s:Concept {id: $source})-[r:RELATES_TO]->(t:Concept {id: $target})
            WHERE r.type = $type
            RETURN r.id as id
        """, source=rel.source, target=rel.target, type=rel.type.value)
        if await dup_check.single():
            raise ValueError(f"Relationship already exists between {rel.source} -> {rel.target} of type {rel.type.value}")
        
        params = rel.model_dump()
        params['type'] = rel.type.value
        params['prerequisite_type'] = rel.prerequisite_type.value if rel.prerequisite_type else None
        
        result = await session.run("""
            MATCH (source:Concept {id: $source}), (target:Concept {id: $target})
            CREATE (source)-[r:RELATES_TO {
                id: $id, type: $type, prerequisite_type: $prerequisite_type,
                time_required_minutes: $time_required_minutes, cognitive_effort: $cognitive_effort
            }]->(target)
            RETURN r.id as id, r.type as type, r.prerequisite_type as prerequisite_type,
                   r.time_required_minutes as time_required_minutes,
                   r.cognitive_effort as cognitive_effort,
                   source.id as source, target.id as target
        """, **params)
        record = await result.single()
        return RelationshipResponse(**record)


async def get_relationship(rel_id: str) -> Optional[RelationshipResponse]:
    async with get_session() as session:
        result = await session.run("""
            MATCH ()-[r:RELATES_TO {id: $id}]-()
            RETURN r.id as id, r.type as type, r.prerequisite_type as prerequisite_type,
                   r.time_required_minutes as time_required_minutes,
                   r.cognitive_effort as cognitive_effort,
                   startNode(r).id as source, endNode(r).id as target
        """, id=rel_id)
        record = await result.single()
        return RelationshipResponse(**record) if record else None


async def get_all_relationships() -> List[RelationshipResponse]:
    async with get_session() as session:
        result = await session.run("""
            MATCH (source:Concept)-[r:RELATES_TO]->(target:Concept)
            RETURN r.id as id, r.type as type, r.prerequisite_type as prerequisite_type,
                   r.time_required_minutes as time_required_minutes,
                   r.cognitive_effort as cognitive_effort,
                   source.id as source, target.id as target
            ORDER BY r.id
        """)
        records = await result.data()
        return [RelationshipResponse(**r) for r in records]


async def update_relationship(rel_id: str, rel: RelationshipUpdate) -> Optional[RelationshipResponse]:
    async with get_session() as session:
        updates = []
        params = {"id": rel_id}
        for field, value in rel.model_dump(exclude_unset=True).items():
            if field in ("type", "prerequisite_type") and value is not None:
                value = value.value
            updates.append(f"r.{field} = ${field}")
            params[field] = value
        
        if not updates:
            return await get_relationship(rel_id)
        
        query = f"""
            MATCH ()-[r:RELATES_TO {{id: $id}}]-()
            SET {", ".join(updates)}
            RETURN r.id as id, r.type as type, r.prerequisite_type as prerequisite_type,
                   r.time_required_minutes as time_required_minutes,
                   r.cognitive_effort as cognitive_effort,
                   startNode(r).id as source, endNode(r).id as target
        """
        result = await session.run(query, params)
        record = await result.single()
        return RelationshipResponse(**record) if record else None


async def delete_relationship(rel_id: str) -> bool:
    async with get_session() as session:
        result = await session.run("""
            MATCH ()-[r:RELATES_TO {id: $id}]-()
            DELETE r
            RETURN count(r) as deleted
        """, id=rel_id)
        record = await result.single()
        return record['deleted'] > 0


async def get_full_graph() -> Tuple[List[NodeResponse], List[RelationshipResponse]]:
    """Get all nodes and relationships for visualization."""
    nodes = await get_all_nodes()
    edges = await get_all_relationships()
    return nodes, edges