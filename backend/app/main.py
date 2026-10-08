"""FastAPI main application with all routes."""

from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os

from app.database import get_session, close_driver, init_database, clear_database, verify_connectivity
from app.models import (
    NodeCreate, NodeUpdate, NodeResponse,
    RelationshipCreate, RelationshipUpdate, RelationshipResponse,
    OptimizationRequest, OptimizationResponse,
    ValidationResult, SearchMethod
)
from app.validation import validate_graph, validate_target_exists
from app.traversal import reverse_traversal, get_subgraph_data
from app.cost_calculator import calculate_edge_costs, calculate_node_metrics, identify_hard_prerequisites
from app.optimizer import dp_optimize
from app.topological_sort import topological_sort, build_final_path
from app.crud import (
    create_node, get_node, get_all_nodes, update_node, delete_node,
    create_relationship, get_relationship, get_all_relationships,
    update_relationship, delete_relationship, get_full_graph
)
from app.graph_service import (
    choose_traversal,
    load_full_graph,
    retrieve_ancestor_subgraph,
)
from app.optimization_service import (
    PipelineError,
    compare_solvers,
    optimize_path,
)
from app.optimizers.ilp import ILPSolver
from app.schemas import (
    PathCompareRequest,
    PathCompareResponse,
    PathOptimizeRequest,
    PathOptimizeResponse,
    SolverAlgorithm,
    TraversalConfig,
    TraversalStrategy,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    connected = await verify_connectivity()
    if connected:
        await init_database()
        print("[OK] Neo4j connected successfully")
    else:
        print("[WARN] Neo4j not available - API will start but DB operations will fail")
        print("       Make sure Neo4j is running on bolt://localhost:7687")
    yield
    # Shutdown
    await close_driver()


app = FastAPI(
    title="Learning Path Engine",
    description="Optimized learning path generation from Knowledge Graph",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for the frontend dev server.
#
# Next.js falls back to the next free port when 3000 is taken, so the origin is
# not knowable ahead of time. Pinning a fixed list silently breaks the app the
# moment it lands on 3001 (every request fails as a network error). Allow any
# loopback port, including both "localhost" and "127.0.0.1" spellings, while
# still refusing non-local origins.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# ENHANCED PIPELINE ENDPOINTS (AUTO traversal + multi-solver)
# ============================================================================

@app.post("/api/path/optimize", response_model=PathOptimizeResponse)
async def api_optimize_path(request: PathOptimizeRequest):
    """
    Run the full pipeline with a single solver.

        FULL KG -> Validation -> Target -> Reverse Traversal (AUTO/BFS/DFS)
        -> Constraints (HARD/SOFT/OPTIONAL) -> DAG -> Runtime Normalization
        -> Optimisation -> Best Valid Plan -> Topological Sort -> Path + Explanation
    """
    try:
        return await optimize_path(request)
    except PipelineError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@app.post("/api/path/compare", response_model=PathCompareResponse)
async def api_compare_solvers(request: PathCompareRequest):
    """
    Run Reverse Traversal ONCE, then execute Greedy Frontier, Dynamic
    Programming and Integer Linear Programming over the *identical* subgraph,
    so the comparison isolates the algorithm rather than the input.
    """
    try:
        return await compare_solvers(request)
    except PipelineError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@app.get("/api/solvers")
async def api_list_solvers():
    """Solver catalogue with the ILP backend that will actually be used."""
    return {
        "solvers": [
            {
                "id": SolverAlgorithm.GREEDY_FRONTIER.value,
                "name": "Greedy Frontier",
                "strategy": "Local utility with N-step lookahead",
                "optimality": "approximate",
                "backend": "networkx",
            },
            {
                "id": SolverAlgorithm.DYNAMIC_PROGRAMMING.value,
                "name": "Dynamic Programming",
                "strategy": (
                    "Forward topological DP: exact best (value - cost) state per "
                    "node, then marginal-gain assembly"
                ),
                "optimality": "heuristic (exact per-node subproblem)",
                "backend": "networkx",
            },
            {
                "id": SolverAlgorithm.INTEGER_LINEAR_PROGRAMMING.value,
                "name": "Integer Linear Programming",
                "strategy": "Flow-conservation MILP with net-utility objective",
                "optimality": "global (exact)",
                "backend": ILPSolver.preferred_backend(),
            },
        ],
        "metrics": {
            "selection_objective": "NetUtility = Sum(LearningValue) - Sum(EdgeCost) - SkipPenalties",
            "reporting_metric": "PathScore = AvgLearningValue / (TotalPathCost + 0.01)",
        },
    }


@app.get("/api/traversal/preview")
async def api_traversal_preview(target_node_id: str, search_method: str = "AUTO"):
    """
    Dry-run the AUTO heuristic without running any solver.
    Useful for showing the user *why* a traversal strategy was chosen.
    """
    strategy = TraversalStrategy(search_method.upper())
    graph = await load_full_graph()
    if target_node_id not in graph:
        raise HTTPException(status_code=404, detail=f"Target node '{target_node_id}' not found.")

    decision = choose_traversal(graph, target_node_id, strategy)
    subgraph, stats = retrieve_ancestor_subgraph(
        graph, target_node_id, decision.selected, TraversalConfig()
    )
    return {"traversal": decision, "stats": stats}


# Health check
@app.get("/health")
async def health_check():
    neo4j_connected = await verify_connectivity()
    return {
        "status": "ok",
        "service": "learning-path-engine",
        "neo4j_connected": neo4j_connected,
        "neo4j_uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    }


# ============================================================
# NODE CRUD ENDPOINTS
# ============================================================

@app.post("/nodes", response_model=NodeResponse, status_code=201)
async def create_node_endpoint(node: NodeCreate):
    try:
        return await create_node(node)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/nodes", response_model=List[NodeResponse])
async def list_nodes():
    return await get_all_nodes()


@app.get("/nodes/{node_id}", response_model=NodeResponse)
async def get_node_endpoint(node_id: str):
    node = await get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    return node


@app.patch("/nodes/{node_id}", response_model=NodeResponse)
async def update_node_endpoint(node_id: str, node: NodeUpdate):
    updated = await update_node(node_id, node)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    return updated


@app.delete("/nodes/{node_id}", status_code=204)
async def delete_node_endpoint(node_id: str):
    deleted = await delete_node(node_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")


# ============================================================
# RELATIONSHIP CRUD ENDPOINTS
# ============================================================

@app.post("/relationships", response_model=RelationshipResponse, status_code=201)
async def create_relationship_endpoint(rel: RelationshipCreate):
    try:
        return await create_relationship(rel)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/relationships", response_model=List[RelationshipResponse])
async def list_relationships():
    return await get_all_relationships()


@app.get("/relationships/{rel_id}", response_model=RelationshipResponse)
async def get_relationship_endpoint(rel_id: str):
    rel = await get_relationship(rel_id)
    if not rel:
        raise HTTPException(status_code=404, detail=f"Relationship '{rel_id}' not found")
    return rel


@app.patch("/relationships/{rel_id}", response_model=RelationshipResponse)
async def update_relationship_endpoint(rel_id: str, rel: RelationshipUpdate):
    updated = await update_relationship(rel_id, rel)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Relationship '{rel_id}' not found")
    return updated


@app.delete("/relationships/{rel_id}", status_code=204)
async def delete_relationship_endpoint(rel_id: str):
    deleted = await delete_relationship(rel_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Relationship '{rel_id}' not found")


# ============================================================
# GRAPH VISUALIZATION ENDPOINT
# ============================================================

@app.get("/graph")
async def get_graph():
    """Get full graph for React Flow visualization."""
    nodes, edges = await get_full_graph()
    
    # Transform for React Flow
    rf_nodes = [
        {
            "id": n.id,
            "type": "conceptNode",
            "data": {"label": n.name, "fullData": n.model_dump()},
            "position": {"x": 0, "y": 0}  # Will be auto-laid out
        }
        for n in nodes
    ]
    
    rf_edges = [
        {
            "id": e.id,
            "source": e.source,
            "target": e.target,
            "type": "conceptEdge",
            "label": e.type.value,
            "data": {"label": e.type.value, "fullData": e.model_dump()},
            "animated": e.type.value == "PREREQUISITE_OF"
        }
        for e in edges
    ]
    
    return {"nodes": rf_nodes, "edges": rf_edges}


# ============================================================
# VALIDATION ENDPOINT
# ============================================================

@app.get("/validate", response_model=ValidationResult)
async def validate_graph_endpoint():
    return await validate_graph()


# ============================================================
# OPTIMIZATION ENDPOINT (MAIN ALGORITHM)
# ============================================================

@app.post("/optimize", response_model=OptimizationResponse)
async def optimize_learning_path(request: OptimizationRequest):
    """
    Main optimization pipeline:
    1. Validate graph
    2. Check target exists
    3. Reverse DFS/BFS traversal to get subgraph
    4. Runtime normalization & cost calculation
    5. DP-based global optimization
    6. Topological sort for learning sequence
    7. Return final optimized path with explanation
    """
    # Step 1: Global validation
    validation = await validate_graph()
    if not validation.is_valid:
        raise HTTPException(status_code=400, detail={
            "message": "Graph validation failed",
            "errors": validation.errors,
            "warnings": validation.warnings
        })

    # Step 2: Check target exists
    target_exists, error_msg = await validate_target_exists(request.target_node_id)
    if not target_exists:
        raise HTTPException(status_code=404, detail=error_msg)

    # Step 3: Reverse traversal (search space reduction)
    visited_nodes, visited_edges, traversal_order, traversal_explanation = await reverse_traversal(
        target_node_id=request.target_node_id,
        method=request.search_method,
        max_depth=request.max_depth
    )

    # Step 4: Get subgraph data
    subgraph_nodes_data, subgraph_edges_data = await get_subgraph_data(visited_nodes, visited_edges)
    
    # Convert to response models
    subgraph_nodes = [NodeResponse(**n) for n in subgraph_nodes_data]
    subgraph_edges = [RelationshipResponse(**e) for e in subgraph_edges_data]

    # Step 5: Runtime cost calculations
    edge_costs = calculate_edge_costs(subgraph_edges, subgraph_nodes)
    
    # Identify HARD prerequisites
    hard_prereqs = identify_hard_prerequisites(subgraph_edges, request.target_node_id)
    
    # Calculate node metrics
    node_metrics = calculate_node_metrics(subgraph_nodes, subgraph_edges, edge_costs, hard_prereqs)

    # Step 6: DP-based global optimization
    dp_result = dp_optimize(
        target_node_id=request.target_node_id,
        nodes=node_metrics,
        edges=subgraph_edges,
        edge_costs=edge_costs,
        include_soft=request.include_soft,
        include_optional=request.include_optional
    )

    # Step 7: Topological sort for final learning sequence
    selected_set = set(dp_result.selected_nodes)
    topo_order = topological_sort(subgraph_nodes, subgraph_edges, selected_set)
    
    # Step 8: Build final path with all metadata
    final_path = build_final_path(
        topo_order=topo_order,
        nodes=subgraph_nodes,
        edges=subgraph_edges,
        edge_costs=edge_costs,
        node_metrics=node_metrics,
        dp_result=dp_result
    )

    # Generate explanation
    explanation = _generate_explanation(
        traversal_explanation, dp_result, final_path, 
        request.search_method, request.include_soft, request.include_optional
    )

    return OptimizationResponse(
        validation=validation,
        traversal=traversal_explanation,
        subgraph_nodes=subgraph_nodes,
        subgraph_edges=subgraph_edges,
        edge_costs=edge_costs,
        node_metrics=node_metrics,
        dp_result=dp_result,
        topological_order=topo_order,
        final_path=final_path,
        explanation=explanation
    )


def _generate_explanation(
    traversal: any,
    dp_result: any,
    final_path: List[Dict],
    search_method: SearchMethod,
    include_soft: bool,
    include_optional: bool
) -> str:
    """Generate human-readable explanation of the optimization process."""
    lines = [
        f"# Learning Path Optimization Explanation",
        f"",
        f"## Search Strategy",
        f"- **Method**: {search_method.value} (Reverse traversal from target)",
        f"- **Nodes visited**: {len(traversal.visited_nodes)}",
        f"- **Edges traversed**: {len(traversal.visited_edges)}",
        f"- **Max depth reached**: {traversal.max_depth_reached}",
        f"- **Nodes pruned (depth limit)**: {traversal.nodes_pruned}",
        f"",
        f"## Constraint Configuration",
        f"- **HARD prerequisites**: Always included (mandatory)",
        f"- **SOFT prerequisites**: {'Included' if include_soft else 'Excluded'}",
        f"- **OPTIONAL prerequisites**: {'Included' if include_optional else 'Excluded'}",
        f"",
        f"## Dynamic Programming Optimization",
        f"- **Total selected nodes**: {len(dp_result.selected_nodes)}",
        f"- **Total cost**: {dp_result.total_cost:.3f}",
        f"- **Total learning value**: {dp_result.total_value:.3f}",
        f"- **Net score (value - cost)**: {dp_result.net_score:.3f}",
        f"",
        f"## Optimization Decisions",
    ]
    
    for step in dp_result.optimization_steps:
        lines.append(f"- **{step['node']}** ({step['name']}): {step['decision']} — {step['reason']}")
    
    lines.extend([
        f"",
        f"## Final Learning Path ({len(final_path)} steps)",
    ])
    
    for step in final_path:
        prereq_info = ""
        if step["prerequisites"]:
            prereq_names = [p["source_name"] for p in step["prerequisites"]]
            prereq_info = f" ← Prereqs: {', '.join(prereq_names)}"
        hard_marker = " 🔒" if step["is_hard_prerequisite"] else ""
        lines.append(f"{step['step']}. **{step['name']}** (value: {step['learning_value']:.2f}, cost: {step['total_incoming_cost']:.2f}){hard_marker}{prereq_info}")
    
    return "\n".join(lines)


# ============================================================
# UTILITY ENDPOINTS
# ============================================================

@app.post("/reset", status_code=200)
async def reset_database():
    """Clear all data (for testing)."""
    await clear_database()
    await init_database()
    return {"message": "Database cleared and reinitialized"}


@app.get("/stats")
async def get_stats():
    """Get graph statistics."""
    async with get_session() as session:
        node_count = await session.run("MATCH (n:Concept) RETURN count(n) as count")
        edge_count = await session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) as count")
        hard_count = await session.run("""
            MATCH ()-[r:RELATES_TO]->() 
            WHERE r.type = 'PREREQUISITE_OF' AND r.prerequisite_type = 'HARD' 
            RETURN count(r) as count
        """)
        soft_count = await session.run("""
            MATCH ()-[r:RELATES_TO]->() 
            WHERE r.type = 'PREREQUISITE_OF' AND r.prerequisite_type = 'SOFT' 
            RETURN count(r) as count
        """)
        optional_count = await session.run("""
            MATCH ()-[r:RELATES_TO]->() 
            WHERE r.type = 'PREREQUISITE_OF' AND r.prerequisite_type = 'OPTIONAL' 
            RETURN count(r) as count
        """)
        part_of_count = await session.run("""
            MATCH ()-[r:RELATES_TO]->() 
            WHERE r.type = 'PART_OF' 
            RETURN count(r) as count
        """)
        
        return {
            "nodes": (await node_count.single())["count"],
            "edges": (await edge_count.single())["count"],
            "hard_prerequisites": (await hard_count.single())["count"],
            "soft_prerequisites": (await soft_count.single())["count"],
            "optional_prerequisites": (await optional_count.single())["count"],
            "part_of_relationships": (await part_of_count.single())["count"],
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)