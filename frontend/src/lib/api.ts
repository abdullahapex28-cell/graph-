/**
 * API client — legacy CRUD endpoints + the enhanced AUTO/multi-solver pipeline.
 */

import axios, { AxiosInstance, AxiosError } from 'axios';
import type {
  NodeCreate, NodeUpdate, NodeResponse,
  RelationshipCreate, RelationshipUpdate, RelationshipResponse,
  ValidationResult, GraphStats,
} from '@/types';
import type {
  ConstraintConfig, PathCompareRequest, PathCompareResponse,
  PathOptimizeRequest, PathOptimizeResponse, SolverAlgorithm,
  SolverMetrics, TraversalStrategy, TraversalConfig,
} from '@/lib/pipelineTypes';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      headers: { 'Content-Type': 'application/json' },
      timeout: 120000, // ILP solving can take a moment
    });

    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        const data = error.response?.data as any;
        const message = data?.detail || error.message;
        return Promise.reject(
          new Error(typeof message === 'string' ? message : JSON.stringify(message))
        );
      }
    );
  }

  // ==========================================================================
  // NODES
  // ==========================================================================

  async createNode(node: NodeCreate): Promise<NodeResponse> {
    const { data } = await this.client.post<NodeResponse>('/nodes', node);
    return data;
  }

  async getNodes(): Promise<NodeResponse[]> {
    const { data } = await this.client.get<NodeResponse[]>('/nodes');
    return data;
  }

  async updateNode(id: string, node: NodeUpdate): Promise<NodeResponse> {
    const { data } = await this.client.patch<NodeResponse>(`/nodes/${id}`, node);
    return data;
  }

  async deleteNode(id: string): Promise<void> {
    await this.client.delete(`/nodes/${id}`);
  }

  // ==========================================================================
  // RELATIONSHIPS
  // ==========================================================================

  async createRelationship(rel: RelationshipCreate): Promise<RelationshipResponse> {
    const { data } = await this.client.post<RelationshipResponse>('/relationships', rel);
    return data;
  }

  async getRelationships(): Promise<RelationshipResponse[]> {
    const { data } = await this.client.get<RelationshipResponse[]>('/relationships');
    return data;
  }

  async updateRelationship(id: string, rel: RelationshipUpdate): Promise<RelationshipResponse> {
    const { data } = await this.client.patch<RelationshipResponse>(`/relationships/${id}`, rel);
    return data;
  }

  async deleteRelationship(id: string): Promise<void> {
    await this.client.delete(`/relationships/${id}`);
  }

  // ==========================================================================
  // GRAPH / VALIDATION / STATS
  // ==========================================================================

  async getGraph(): Promise<{ nodes: any[]; edges: any[] }> {
    const { data } = await this.client.get('/graph');
    return data;
  }

  async validateGraph(): Promise<ValidationResult> {
    const { data } = await this.client.get<ValidationResult>('/validate');
    return data;
  }

  async getStats(): Promise<GraphStats> {
    const { data } = await this.client.get<GraphStats>('/stats');
    return data;
  }

  // ==========================================================================
  // ENHANCED PIPELINE
  // ==========================================================================

  /** Single-solver run through the full pipeline. */
  async optimizePath(request: PathOptimizeRequest): Promise<PathOptimizeResponse> {
    const { data } = await this.client.post<PathOptimizeResponse>('/api/path/optimize', request);
    return data;
  }

  /** Runs every solver over one shared subgraph and returns the comparison. */
  async compareSolvers(request: PathCompareRequest): Promise<PathCompareResponse> {
    const { data } = await this.client.post<PathCompareResponse>('/api/path/compare', request);
    return data;
  }

  async listSolvers(): Promise<{
    solvers: Array<{
      id: SolverAlgorithm; name: string; strategy: string;
      optimality: string; backend: string;
    }>;
    metrics: Record<string, string>;
  }> {
    const { data } = await this.client.get('/api/solvers');
    return data;
  }

  /** Dry-run the AUTO heuristic: shows the chosen strategy and its rationale. */
  async previewTraversal(targetNodeId: string, searchMethod: TraversalStrategy = 'AUTO') {
    const { data } = await this.client.get('/api/traversal/preview', {
      params: { target_node_id: targetNodeId, search_method: searchMethod },
    });
    return data as {
      traversal: {
        requested: TraversalStrategy;
        selected: TraversalStrategy;
        reason: string;
        metrics: Record<string, number>;
      };
      stats: Record<string, any>;
    };
  }

  // ==========================================================================
  // UTILITIES
  // ==========================================================================

  async resetDatabase(): Promise<{ message: string }> {
    const { data } = await this.client.post('/reset');
    return data;
  }

  async healthCheck(): Promise<{ status: string; neo4j_connected: boolean }> {
    const { data } = await this.client.get('/health');
    return data;
  }

  /** Convenience builder so the Toolbar/CompareModal stay in sync. */
  buildCompareRequest(
    targetNodeId: string,
    searchMethod: TraversalStrategy,
    constraints: Partial<ConstraintConfig> = {},
    traversal: Partial<TraversalConfig> = {}
  ): PathCompareRequest {
    return {
      target_node_id: targetNodeId,
      search_method: searchMethod,
      constraints: {
        max_time_budget_minutes: undefined,
        include_soft: true,
        include_optional: true,
        soft_skip_penalty: 0.15,
        greedy_lookahead_depth: 3,
        ...constraints,
      },
      traversal: {
        max_depth: undefined,
        max_subgraph_nodes: 60,
        ...traversal,
      },
    };
  }
}

export const api = new ApiClient();

/** Solvers in display order, matching the backend registry. */
export const SOLVER_ORDER: SolverAlgorithm[] = ['GREEDY', 'DP', 'ILP'];

export const SOLVER_LABELS: Record<SolverAlgorithm, string> = {
  GREEDY: 'Greedy Frontier',
  DP: 'Dynamic Programming',
  ILP: 'Integer Linear Programming',
};

export const TRAVERSAL_LABELS: Record<TraversalStrategy, string> = {
  AUTO: 'AUTO (Recommended)',
  BFS: 'BFS',
  DFS: 'DFS',
};

export type { SolverMetrics };
