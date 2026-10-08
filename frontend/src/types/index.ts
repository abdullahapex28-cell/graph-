/** Type definitions matching the backend models */

export type RelationshipType = 'PART_OF' | 'PREREQUISITE_OF';
export type PrerequisiteType = 'HARD' | 'SOFT' | 'OPTIONAL';
export type SearchMethod = 'DFS' | 'BFS';

export interface NodeBase {
  id: string;
  name: string;
  description: string;
  target_relevance: number;
  downstream_utility: number;
}

export interface NodeCreate extends NodeBase {}
export interface NodeUpdate {
  name?: string;
  description?: string;
  target_relevance?: number;
  downstream_utility?: number;
}
export interface NodeResponse extends NodeBase {}

export interface RelationshipBase {
  id: string;
  source: string;
  target: string;
  type: RelationshipType;
  prerequisite_type: PrerequisiteType | null;
  time_required_minutes: number;
  cognitive_effort: number;
}

export interface RelationshipCreate extends RelationshipBase {}
export interface RelationshipUpdate {
  type?: RelationshipType;
  prerequisite_type?: PrerequisiteType | null;
  time_required_minutes?: number;
  cognitive_effort?: number;
}
export interface RelationshipResponse extends RelationshipBase {}

export interface OptimizationRequest {
  target_node_id: string;
  search_method: SearchMethod;
  max_depth?: number;
  include_optional: boolean;
  include_soft: boolean;
}

export interface EdgeCostCalculation {
  edge_id: string;
  source: string;
  target: string;
  time_required_minutes: number;
  cognitive_effort: number;
  normalized_time: number;
  normalized_cognitive_effort: number;
  edge_cost: number;
  learning_value: number;
}

export interface NodeMetrics {
  node_id: string;
  name: string;
  target_relevance: number;
  downstream_utility: number;
  learning_value: number;
  total_incoming_cost: number;
  is_hard_prerequisite: boolean;
  is_selected: boolean;
}

export interface DPResult {
  selected_nodes: string[];
  total_cost: number;
  total_value: number;
  net_score: number;
  optimization_steps: OptimizationStep[];
}

export interface OptimizationStep {
  node: string;
  name: string;
  decision: string;
  reason: string;
  prerequisite_type?: string;
  net_benefit?: number;
}

export interface TraversalExplanation {
  method: SearchMethod;
  visited_nodes: string[];
  visited_edges: string[];
  traversal_order: string[];
  max_depth_reached: number;
  nodes_pruned: number;
}

export interface ValidationResult {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface OptimizationResponse {
  validation: ValidationResult;
  traversal: TraversalExplanation;
  subgraph_nodes: NodeResponse[];
  subgraph_edges: RelationshipResponse[];
  edge_costs: EdgeCostCalculation[];
  node_metrics: NodeMetrics[];
  dp_result: DPResult;
  topological_order: string[];
  final_path: FinalPathStep[];
  explanation: string;
}

export interface FinalPathStep {
  step: number;
  node_id: string;
  name: string;
  description: string;
  target_relevance: number;
  downstream_utility: number;
  learning_value: number;
  total_incoming_cost: number;
  is_hard_prerequisite: boolean;
  is_selected: boolean;
  prerequisites: PrerequisiteInfo[];
  estimated_time_minutes: number;
}

export interface PrerequisiteInfo {
  edge_id: string;
  source: string;
  source_name: string;
  relationship_type: string;
  prerequisite_type: PrerequisiteType | null;
  time_required_minutes: number;
  cognitive_effort: number;
  normalized_time: number;
  normalized_cognitive_effort: number;
  edge_cost: number;
}

export interface GraphStats {
  nodes: number;
  edges: number;
  hard_prerequisites: number;
  soft_prerequisites: number;
  optional_prerequisites: number;
  part_of_relationships: number;
}

// React Flow types
export interface RFNodeData {
  label: string;
  fullData: NodeResponse;
}

export interface RFEdgeData {
  label: string;
  fullData: RelationshipResponse;
}