"""
Schemas for the enhanced Learning Path Engine.

Separated from the legacy `models.py` so the original CRUD contract stays intact
while the new AUTO traversal / multi-solver comparison contracts live here.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================================
# ENUMS
# ============================================================================

class TraversalStrategy(str, Enum):
    """Search-space reduction strategy (Step 2 of the pipeline)."""

    AUTO = "AUTO"
    BFS = "BFS"
    DFS = "DFS"


class SolverAlgorithm(str, Enum):
    """The three parallel optimization solvers (Step 3 of the pipeline)."""

    DYNAMIC_PROGRAMMING = "DP"
    GREEDY_FRONTIER = "GREEDY"
    INTEGER_LINEAR_PROGRAMMING = "ILP"


class PrerequisiteType(str, Enum):
    HARD = "HARD"
    SOFT = "SOFT"
    OPTIONAL = "OPTIONAL"


class RelationshipType(str, Enum):
    PART_OF = "PART_OF"
    PREREQUISITE_OF = "PREREQUISITE_OF"


class Feasibility(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


# ============================================================================
# CONSTRAINT CONFIGURATION
# ============================================================================

class ConstraintConfig(BaseModel):
    """Target-specific constraints applied to the retrieved subgraph."""

    max_time_budget_minutes: Optional[int] = Field(
        default=None,
        ge=1,
        description="Hard ceiling on total path time. None = unconstrained.",
    )
    include_soft: bool = Field(
        default=True,
        description="When False, SOFT prerequisites are only pulled in via DP/ILP if valuable.",
    )
    include_optional: bool = Field(
        default=True,
        description="When False, OPTIONAL prerequisites are never auto-included.",
    )
    soft_skip_penalty: float = Field(
        default=0.15,
        ge=0.0,
        description=(
            "Cognitive-effort penalty added when a SOFT prerequisite is skipped. "
            "Raises effective target cost, biasing the solver toward covering it."
        ),
    )
    greedy_lookahead_depth: int = Field(
        default=3,
        ge=1,
        le=10,
        description="N-step lookahead horizon for the Greedy Frontier solver.",
    )


class TraversalConfig(BaseModel):
    max_depth: Optional[int] = Field(
        default=None, ge=1, description="Depth limit for ancestor traversal."
    )
    max_subgraph_nodes: int = Field(
        default=60, ge=5, description="Safety cap on retrieved subgraph size."
    )


# ============================================================================
# REQUEST / RESPONSE MODELS
# ============================================================================

class PathOptimizeRequest(BaseModel):
    target_node_id: str = Field(..., min_length=1)
    search_method: TraversalStrategy = TraversalStrategy.AUTO
    solver: SolverAlgorithm = SolverAlgorithm.DYNAMIC_PROGRAMMING
    constraints: ConstraintConfig = Field(default_factory=ConstraintConfig)
    traversal: TraversalConfig = Field(default_factory=TraversalConfig)


class PathCompareRequest(BaseModel):
    """Input for POST /api/path/compare."""

    target_node_id: str = Field(..., min_length=1)
    search_method: TraversalStrategy = TraversalStrategy.AUTO
    constraints: ConstraintConfig = Field(default_factory=ConstraintConfig)
    traversal: TraversalConfig = Field(default_factory=TraversalConfig)
    solvers: Optional[List[SolverAlgorithm]] = Field(
        default=None,
        description="Subset of solvers to compare. Defaults to all three.",
    )


class ValidationIssue(BaseModel):
    code: str
    message: str
    severity: Severity
    entities: List[str] = Field(default_factory=list)


class ValidationReport(BaseModel):
    is_valid: bool
    total_nodes: int
    total_edges: int
    errors: List[ValidationIssue] = Field(default_factory=list)
    warnings: List[ValidationIssue] = Field(default_factory=list)
    cycle_details: List[List[str]] = Field(default_factory=list)


class AutoTraversalDecision(BaseModel):
    """Why the AUTO heuristic picked the traversal it picked."""

    requested: TraversalStrategy
    selected: TraversalStrategy
    reason: str
    metrics: Dict[str, float]


class EdgeMetrics(BaseModel):
    """Runtime-derived edge values. Never persisted in Neo4j."""

    edge_id: str
    source: str
    target: str
    relationship_type: RelationshipType
    prerequisite_type: Optional[PrerequisiteType] = None
    raw_time_minutes: int
    raw_cognitive_effort: int
    normalized_time: float
    normalized_cognitive_effort: float
    edge_cost: float


class NodeMetrics(BaseModel):
    node_id: str
    name: str
    description: str
    target_relevance: float
    downstream_utility: float
    learning_value: float
    is_hard_prerequisite: bool
    incoming_edge_ids: List[str] = Field(default_factory=list)
    skip_penalty: float = 0.0


class SolverMetrics(BaseModel):
    """Comparison metrics emitted identically by all three solvers."""

    solver: SolverAlgorithm
    display_name: str
    is_feasible: bool
    feasibility_reason: str
    path_nodes: List[str]
    path_edges: List[str]
    total_path_cost: float
    average_learning_value: float
    path_score: float
    total_time_minutes: int
    execution_time_ms: float
    net_utility: float = Field(
        default=0.0,
        description=(
            "Selection objective: Sum(LearningValue) - Sum(EdgeCost) - SkipPenalties. "
            "This is what the solvers actually maximise; Path Score is a "
            "reporting / ranking metric only."
        ),
    )
    solver_specific: Dict[str, Any] = Field(default_factory=dict)


class SolverComparison(BaseModel):
    target_node_id: str
    target_node_name: str
    # Mixed int/float: counts plus reduction_ratio, which is fractional.
    subgraph_size: Dict[str, float]
    shared_subgraph_node_ids: List[str]
    shared_subgraph_edge_ids: List[str]
    results: List[SolverMetrics]
    best_solver: Optional[SolverAlgorithm]
    best_path_score: float
    recommendation: str
    recommendation_rationale: List[str]
    constraints_applied: ConstraintConfig


class PathOptimizeResponse(BaseModel):
    validation: ValidationReport
    traversal: AutoTraversalDecision
    traversal_stats: Dict[str, Any]
    subgraph_nodes: List[NodeMetrics]
    subgraph_edges: List[EdgeMetrics]
    result: SolverMetrics
    learning_sequence: List[Dict[str, Any]]
    explanation: str


class PathCompareResponse(BaseModel):
    validation: ValidationReport
    traversal: AutoTraversalDecision
    subgraph_nodes: List[NodeMetrics]
    subgraph_edges: List[EdgeMetrics]
    comparison: SolverComparison
    learning_sequences: Dict[str, List[Dict[str, Any]]]
