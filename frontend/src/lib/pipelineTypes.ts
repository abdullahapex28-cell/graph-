/** Enhanced pipeline types — mirrors backend/app/schemas.py */

export type TraversalStrategy = 'AUTO' | 'BFS' | 'DFS';
export type SolverAlgorithm = 'GREEDY' | 'DP' | 'ILP';
export type PrerequisiteType = 'HARD' | 'SOFT' | 'OPTIONAL';
export type RelationshipType = 'PART_OF' | 'PREREQUISITE_OF';

export interface ConstraintConfig {
  max_time_budget_minutes?: number;
  include_soft: boolean;
  include_optional: boolean;
  soft_skip_penalty: number;
  greedy_lookahead_depth: number;
}

export interface TraversalConfig {
  max_depth?: number;
  max_subgraph_nodes: number;
}

export interface ValidationIssue {
  code: string;
  message: string;
  severity: 'ERROR' | 'WARNING';
  entities: string[];
}

export interface ValidationReport {
  is_valid: boolean;
  total_nodes: number;
  total_edges: number;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
  cycle_details: string[][];
}

export interface AutoTraversalDecision {
  requested: TraversalStrategy;
  selected: TraversalStrategy;
  reason: string;
  metrics: Record<string, number>;
}

export interface EdgeMetrics {
  edge_id: string;
  source: string;
  target: string;
  relationship_type: RelationshipType;
  prerequisite_type: PrerequisiteType | null;
  raw_time_minutes: number;
  raw_cognitive_effort: number;
  normalized_time: number;
  normalized_cognitive_effort: number;
  edge_cost: number;
}

export interface NodeMetrics {
  node_id: string;
  name: string;
  description: string;
  target_relevance: number;
  downstream_utility: number;
  learning_value: number;
  is_hard_prerequisite: boolean;
  incoming_edge_ids: string[];
  skip_penalty: number;
}

export interface SolverMetrics {
  solver: SolverAlgorithm;
  display_name: string;
  is_feasible: boolean;
  feasibility_reason: string;
  path_nodes: string[];
  path_edges: string[];
  total_path_cost: number;
  average_learning_value: number;
  path_score: number;
  total_time_minutes: number;
  execution_time_ms: number;
  net_utility: number;
  solver_specific: Record<string, any>;
}

export interface PrereqInfo {
  edge_id: string;
  source: string;
  source_name: string;
  prerequisite_type: PrerequisiteType | null;
  time_required_minutes: number;
  cognitive_effort: number;
  edge_cost: number;
}

export interface LearningStep {
  step: number;
  node_id: string;
  name: string;
  description: string;
  learning_value: number;
  is_hard_prerequisite: boolean;
  estimated_time_minutes: number;
  prerequisites: PrereqInfo[];
}

export interface PathOptimizeRequest {
  target_node_id: string;
  search_method: TraversalStrategy;
  solver: SolverAlgorithm;
  constraints: ConstraintConfig;
  traversal: TraversalConfig;
}

export interface PathOptimizeResponse {
  validation: ValidationReport;
  traversal: AutoTraversalDecision;
  traversal_stats: Record<string, any>;
  subgraph_nodes: NodeMetrics[];
  subgraph_edges: EdgeMetrics[];
  result: SolverMetrics;
  learning_sequence: LearningStep[];
  explanation: string;
}

export interface PathCompareRequest {
  target_node_id: string;
  search_method: TraversalStrategy;
  constraints: ConstraintConfig;
  traversal: TraversalConfig;
  solvers?: SolverAlgorithm[];
}

export interface SolverComparison {
  target_node_id: string;
  target_node_name: string;
  subgraph_size: Record<string, number>;
  shared_subgraph_node_ids: string[];
  shared_subgraph_edge_ids: string[];
  results: SolverMetrics[];
  best_solver: SolverAlgorithm | null;
  best_path_score: number;
  recommendation: string;
  recommendation_rationale: string[];
  constraints_applied: ConstraintConfig;
}

export interface PathCompareResponse {
  validation: ValidationReport;
  traversal: AutoTraversalDecision;
  subgraph_nodes: NodeMetrics[];
  subgraph_edges: EdgeMetrics[];
  comparison: SolverComparison;
  learning_sequences: Record<string, LearningStep[]>;
}

export interface SolverCatalogueEntry {
  id: SolverAlgorithm;
  name: string;
  strategy: string;
  optimality: string;
  backend: string;
}
