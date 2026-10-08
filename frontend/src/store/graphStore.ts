/** Zustand store for graph state management */

import { create } from 'zustand';
import type {
  NodeResponse, RelationshipResponse,
  OptimizationResponse, ValidationResult,
  GraphStats, SearchMethod
} from '@/types';

interface GraphState {
  // Graph data
  nodes: NodeResponse[];
  edges: RelationshipResponse[];
  stats: GraphStats | null;
  
  // Optimization results
  optimizationResult: OptimizationResponse | null;
  validationResult: ValidationResult | null;
  
  // UI state
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  isLoading: boolean;
  error: string | null;
  
  // Optimization target
  targetNodeId: string;
  setTargetNodeId: (id: string) => void;

  // Optimization parameters
  searchMethod: SearchMethod;
  maxDepth: number | undefined;
  includeSoft: boolean;
  includeOptional: boolean;
  
  // Viewport for React Flow
  viewport: { x: number; y: number; zoom: number } | null;
  
  // Actions
  setNodes: (nodes: NodeResponse[]) => void;
  setEdges: (edges: RelationshipResponse[]) => void;
  setStats: (stats: GraphStats | null) => void;
  addNode: (node: NodeResponse) => void;
  updateNode: (node: NodeResponse) => void;
  removeNode: (id: string) => void;
  addEdge: (edge: RelationshipResponse) => void;
  updateEdge: (edge: RelationshipResponse) => void;
  removeEdge: (id: string) => void;
  
  setOptimizationResult: (result: OptimizationResponse | null) => void;
  setValidationResult: (result: ValidationResult | null) => void;
  
  setSelectedNode: (id: string | null) => void;
  setSelectedEdge: (id: string | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  
  setSearchMethod: (method: SearchMethod) => void;
  setMaxDepth: (depth: number | undefined) => void;
  setIncludeSoft: (include: boolean) => void;
  setIncludeOptional: (include: boolean) => void;
  
  setViewport: (viewport: { x: number; y: number; zoom: number } | null) => void;
  
  clearGraph: () => void;
  clearOptimization: () => void;
}

export const useGraphStore = create<GraphState>((set) => ({
  // Initial state
  nodes: [],
  edges: [],
  stats: null,
  optimizationResult: null,
  validationResult: null,
  selectedNodeId: null,
  selectedEdgeId: null,
  isLoading: false,
  error: null,
  targetNodeId: '',
  searchMethod: 'DFS',
  maxDepth: undefined,
  includeSoft: true,
  includeOptional: true,
  viewport: null,
  
  // Actions
  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  setStats: (stats) => set({ stats }),
  addNode: (node) => set((state) => ({ nodes: [...state.nodes, node] })),
  updateNode: (node) => set((state) => ({
    nodes: state.nodes.map((n) => (n.id === node.id ? node : n)),
  })),
  removeNode: (id) => set((state) => ({
    nodes: state.nodes.filter((n) => n.id !== id),
    edges: state.edges.filter((e) => e.source !== id && e.target !== id),
  })),
  addEdge: (edge) => set((state) => ({ edges: [...state.edges, edge] })),
  updateEdge: (edge) => set((state) => ({
    edges: state.edges.map((e) => (e.id === edge.id ? edge : e)),
  })),
  removeEdge: (id) => set((state) => ({
    edges: state.edges.filter((e) => e.id !== id),
  })),
  
  setOptimizationResult: (result) => set({ optimizationResult: result }),
  setValidationResult: (result) => set({ validationResult: result }),
  
  setSelectedNode: (id) => set({ selectedNodeId: id }),
  setSelectedEdge: (id) => set({ selectedEdgeId: id }),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
  
  setTargetNodeId: (id) => set({ targetNodeId: id }),
  setSearchMethod: (method) => set({ searchMethod: method }),
  setMaxDepth: (depth) => set({ maxDepth: depth }),
  setIncludeSoft: (include) => set({ includeSoft: include }),
  setIncludeOptional: (include) => set({ includeOptional: include }),
  
  setViewport: (viewport) => set({ viewport }),
  
  clearGraph: () => set({
    nodes: [],
    edges: [],
    stats: null,
    selectedNodeId: null,
    selectedEdgeId: null,
  }),
  
  clearOptimization: () => set({
    optimizationResult: null,
    validationResult: null,
  }),
}));