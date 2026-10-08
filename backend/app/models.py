"""Pydantic models for the Learning Path Engine."""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class RelationshipType(str, Enum):
    PART_OF = "PART_OF"
    PREREQUISITE_OF = "PREREQUISITE_OF"


class PrerequisiteType(str, Enum):
    HARD = "HARD"
    SOFT = "SOFT"
    OPTIONAL = "OPTIONAL"


class SearchMethod(str, Enum):
    DFS = "DFS"
    BFS = "BFS"


class NodeBase(BaseModel):
    id: str = Field(..., min_length=1, description="Unique identifier for the node")
    name: str = Field(..., min_length=1, description="Display name of the node")
    description: str = Field(default="", description="Detailed description")
    target_relevance: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Relevance to target (0-1)"
    )
    downstream_utility: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Utility for downstream topics (0-1)"
    )

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Node ID cannot be empty")
        return v.strip()


class NodeCreate(NodeBase):
    pass


class NodeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    target_relevance: Optional[float] = Field(None, ge=0.0, le=1.0)
    downstream_utility: Optional[float] = Field(None, ge=0.0, le=1.0)


class NodeResponse(NodeBase):
    pass


class RelationshipBase(BaseModel):
    id: str = Field(..., min_length=1, description="Unique identifier for the relationship")
    source: str = Field(..., min_length=1, description="Source node ID")
    target: str = Field(..., min_length=1, description="Target node ID")
    type: RelationshipType = Field(..., description="Type of relationship")
    prerequisite_type: Optional[PrerequisiteType] = Field(
        default=None, description="Applies only if type == PREREQUISITE_OF"
    )
    time_required_minutes: int = Field(
        default=20, ge=1, description="Time required in minutes"
    )
    cognitive_effort: int = Field(
        default=3, ge=1, le=5, description="Cognitive effort (1-5)"
    )

    @field_validator("prerequisite_type")
    @classmethod
    def validate_prerequisite_type(cls, v: Optional[PrerequisiteType], info) -> Optional[PrerequisiteType]:
        if info.data.get("type") == RelationshipType.PREREQUISITE_OF and v is None:
            raise ValueError("prerequisite_type is required for PREREQUISITE_OF relationships")
        if info.data.get("type") == RelationshipType.PART_OF and v is not None:
            raise ValueError("prerequisite_type must be null for PART_OF relationships")
        return v

    @model_validator(mode="after")
    def validate_no_self_loop(self) -> "RelationshipBase":
        if self.source == self.target:
            raise ValueError("Self-loops are not allowed (source cannot equal target)")
        return self


class RelationshipCreate(RelationshipBase):
    pass


class RelationshipUpdate(BaseModel):
    type: Optional[RelationshipType] = None
    prerequisite_type: Optional[PrerequisiteType] = None
    time_required_minutes: Optional[int] = Field(None, ge=1)
    cognitive_effort: Optional[int] = Field(None, ge=1, le=5)


class RelationshipResponse(RelationshipBase):
    pass


class OptimizationRequest(BaseModel):
    target_node_id: str = Field(..., min_length=1, description="Target node to optimize path for")
    search_method: SearchMethod = Field(default=SearchMethod.DFS, description="Graph traversal method")
    max_depth: Optional[int] = Field(default=None, ge=1, description="Maximum traversal depth")
    include_optional: bool = Field(default=True, description="Include OPTIONAL prerequisites in optimization")
    include_soft: bool = Field(default=True, description="Include SOFT prerequisites in optimization")


class EdgeCostCalculation(BaseModel):
    edge_id: str
    source: str
    target: str
    time_required_minutes: int
    cognitive_effort: int
    normalized_time: float
    normalized_cognitive_effort: float
    edge_cost: float
    learning_value: float


class NodeMetrics(BaseModel):
    node_id: str
    name: str
    target_relevance: float
    downstream_utility: float
    learning_value: float
    total_incoming_cost: float
    is_hard_prerequisite: bool
    is_selected: bool


class DPResult(BaseModel):
    selected_nodes: List[str]
    total_cost: float
    total_value: float
    net_score: float
    optimization_steps: List[Dict[str, Any]]


class TraversalExplanation(BaseModel):
    method: SearchMethod
    visited_nodes: List[str]
    visited_edges: List[str]
    traversal_order: List[str]
    max_depth_reached: int
    nodes_pruned: int


class ValidationResult(BaseModel):
    is_valid: bool
    errors: List[str]
    warnings: List[str]


class OptimizationResponse(BaseModel):
    validation: ValidationResult
    traversal: TraversalExplanation
    subgraph_nodes: List[NodeResponse]
    subgraph_edges: List[RelationshipResponse]
    edge_costs: List[EdgeCostCalculation]
    node_metrics: List[NodeMetrics]
    dp_result: DPResult
    topological_order: List[str]
    final_path: List[Dict[str, Any]]
    explanation: str