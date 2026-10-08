/** Zustand store for the enhanced pipeline state. */

import { create } from 'zustand';
import type { NodeResponse, RelationshipResponse } from '@/types';
import type {
  AutoTraversalDecision, ConstraintConfig, PathCompareResponse,
  PathOptimizeResponse, SolverAlgorithm, SolverCatalogueEntry,
  TraversalConfig, TraversalStrategy, ValidationReport,
} from '@/lib/pipelineTypes';

interface PipelineState {
  // --- Graph ---
  nodes: NodeResponse[];
  edges: RelationshipResponse[];

  // --- Controls ---
  targetNodeId: string;
  searchMethod: TraversalStrategy;
  solver: SolverAlgorithm;
  constraints: ConstraintConfig;
  traversal: TraversalConfig;

  // --- Results ---
  optimizeResult: PathOptimizeResponse | null;
  compareResult: PathCompareResponse | null;
  validation: ValidationReport | null;
  solverCatalogue: SolverCatalogueEntry[];

  // --- Selection / highlighting ---
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  /** Which solver's path is currently painted on the canvas. */
  activeSolver: SolverAlgorithm | null;

  // --- UI ---
  isOptimizing: boolean;
  isComparing: boolean;
  error: string | null;

  // --- Actions ---
  setNodes: (nodes: NodeResponse[]) => void;
  setEdges: (edges: RelationshipResponse[]) => void;
  addNode: (node: NodeResponse) => void;
  removeNode: (id: string) => void;
  addEdge: (edge: RelationshipResponse) => void;
  removeEdge: (id: string) => void;

  setTargetNodeId: (id: string) => void;
  setSearchMethod: (m: TraversalStrategy) => void;
  setSolver: (s: SolverAlgorithm) => void;
  setConstraint: <K extends keyof ConstraintConfig>(key: K, value: ConstraintConfig[K]) => void;
  setTraversalConfig: <K extends keyof TraversalConfig>(key: K, value: TraversalConfig[K]) => void;

  setOptimizeResult: (r: PathOptimizeResponse | null) => void;
  setCompareResult: (r: PathCompareResponse | null) => void;
  setValidation: (v: ValidationReport | null) => void;
  setSolverCatalogue: (c: SolverCatalogueEntry[]) => void;

  setSelectedNode: (id: string | null) => void;
  setSelectedEdge: (id: string | null) => void;
  setActiveSolver: (s: SolverAlgorithm | null) => void;

  setOptimizing: (v: boolean) => void;
  setComparing: (v: boolean) => void;
  setError: (e: string | null) => void;

  clearResults: () => void;
}

const DEFAULT_CONSTRAINTS: ConstraintConfig = {
  max_time_budget_minutes: undefined,
  include_soft: true,
  include_optional: true,
  soft_skip_penalty: 0.15,
  greedy_lookahead_depth: 3,
};

const DEFAULT_TRAVERSAL: TraversalConfig = {
  max_depth: undefined,
  max_subgraph_nodes: 60,
};

export const usePipelineStore = create<PipelineState>((set) => ({
  nodes: [],
  edges: [],

  targetNodeId: '',
  searchMethod: 'AUTO',
  solver: 'DP',
  constraints: { ...DEFAULT_CONSTRAINTS },
  traversal: { ...DEFAULT_TRAVERSAL },

  optimizeResult: null,
  compareResult: null,
  validation: null,
  solverCatalogue: [],

  selectedNodeId: null,
  selectedEdgeId: null,
  activeSolver: null,

  isOptimizing: false,
  isComparing: false,
  error: null,

  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  addNode: (node) => set((s) => ({ nodes: [...s.nodes, node] })),
  removeNode: (id) =>
    set((s) => ({
      nodes: s.nodes.filter((n) => n.id !== id),
      edges: s.edges.filter((e) => e.source !== id && e.target !== id),
    })),
  addEdge: (edge) => set((s) => ({ edges: [...s.edges, edge] })),
  removeEdge: (id) => set((s) => ({ edges: s.edges.filter((e) => e.id !== id) })),

  setTargetNodeId: (id) => set({ targetNodeId: id }),
  setSearchMethod: (m) => set({ searchMethod: m }),
  setSolver: (s) => set({ solver: s }),
  setConstraint: (key, value) =>
    set((s) => ({ constraints: { ...s.constraints, [key]: value } })),
  setTraversalConfig: (key, value) =>
    set((s) => ({ traversal: { ...s.traversal, [key]: value } })),

  setOptimizeResult: (r) => set({ optimizeResult: r }),
  setCompareResult: (r) =>
    set((s) => ({
      compareResult: r,
      activeSolver: r?.comparison.best_solver ?? s.activeSolver,
    })),
  setValidation: (v) => set({ validation: v }),
  setSolverCatalogue: (c) => set({ solverCatalogue: c }),

  setSelectedNode: (id) => set({ selectedNodeId: id }),
  setSelectedEdge: (id) => set({ selectedEdgeId: id }),
  setActiveSolver: (s) => set({ activeSolver: s }),

  setOptimizing: (v) => set({ isOptimizing: v }),
  setComparing: (v) => set({ isComparing: v }),
  setError: (e) => set({ error: e }),

  clearResults: () => set({ optimizeResult: null, compareResult: null, activeSolver: null }),
}));
