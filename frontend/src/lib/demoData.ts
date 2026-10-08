/** Demo / seed data: 10-node sample Knowledge Graph (math learning path). */

import { api } from '@/lib/api';
import { useGraphStore } from '@/store/graphStore';
import type { NodeCreate, RelationshipCreate } from '@/types';

/** Suggested learning goal after the demo graph is loaded. */
export const DEMO_TARGET_ID = 'fraction-division';

/** 10 concept nodes: Number Sense -> Addition -> ... -> Fraction Division */
export const DEMO_NODES: NodeCreate[] = [
  { id: 'number-sense', name: 'Number Sense', description: 'Counting, place value and number relationships', target_relevance: 0.2, downstream_utility: 0.95 },
  { id: 'addition', name: 'Addition', description: 'Adding whole numbers with regrouping', target_relevance: 0.35, downstream_utility: 0.9 },
  { id: 'subtraction', name: 'Subtraction', description: 'Subtracting whole numbers and difference concepts', target_relevance: 0.35, downstream_utility: 0.85 },
  { id: 'multiplication', name: 'Multiplication', description: 'Repeated addition, times tables and properties', target_relevance: 0.55, downstream_utility: 0.85 },
  { id: 'division', name: 'Division', description: 'Sharing, grouping and the inverse of multiplication', target_relevance: 0.6, downstream_utility: 0.8 },
  { id: 'fractions', name: 'Fractions', description: 'Understanding parts of a whole', target_relevance: 0.7, downstream_utility: 0.8 },
  { id: 'equivalent-fractions', name: 'Equivalent Fractions', description: 'Comparing, simplifying and generating equivalent fractions', target_relevance: 0.75, downstream_utility: 0.7 },
  { id: 'fraction-addition', name: 'Fraction Addition', description: 'Adding fractions with like and unlike denominators', target_relevance: 0.8, downstream_utility: 0.65 },
  { id: 'fraction-multiplication', name: 'Fraction Multiplication', description: 'Multiplying numerators and denominators', target_relevance: 0.85, downstream_utility: 0.6 },
  { id: 'fraction-division', name: 'Fraction Division', description: 'Dividing fractions by multiplying with the reciprocal', target_relevance: 1, downstream_utility: 0.5 },
];

/** Prerequisite edges with realistic time (minutes) and cognitive effort (1-5). */
export const DEMO_EDGES: RelationshipCreate[] = [
  { id: 'de1', source: 'number-sense', target: 'addition', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 15, cognitive_effort: 1 },
  { id: 'de2', source: 'number-sense', target: 'subtraction', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 15, cognitive_effort: 1 },
  { id: 'de3', source: 'addition', target: 'multiplication', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 25, cognitive_effort: 2 },
  { id: 'de4', source: 'subtraction', target: 'multiplication', type: 'PREREQUISITE_OF', prerequisite_type: 'SOFT', time_required_minutes: 20, cognitive_effort: 2 },
  { id: 'de5', source: 'multiplication', target: 'division', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 30, cognitive_effort: 2 },
  { id: 'de6', source: 'subtraction', target: 'division', type: 'PREREQUISITE_OF', prerequisite_type: 'SOFT', time_required_minutes: 25, cognitive_effort: 2 },
  { id: 'de7', source: 'division', target: 'fractions', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 35, cognitive_effort: 3 },
  { id: 'de8', source: 'addition', target: 'fractions', type: 'PREREQUISITE_OF', prerequisite_type: 'OPTIONAL', time_required_minutes: 20, cognitive_effort: 2 },
  { id: 'de9', source: 'fractions', target: 'equivalent-fractions', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 25, cognitive_effort: 3 },
  { id: 'de10', source: 'equivalent-fractions', target: 'fraction-addition', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 30, cognitive_effort: 3 },
  { id: 'de11', source: 'fractions', target: 'fraction-multiplication', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 30, cognitive_effort: 3 },
  { id: 'de12', source: 'division', target: 'fraction-division', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 40, cognitive_effort: 4 },
  { id: 'de13', source: 'fraction-multiplication', target: 'fraction-division', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 35, cognitive_effort: 4 },
  { id: 'de14', source: 'equivalent-fractions', target: 'fraction-division', type: 'PREREQUISITE_OF', prerequisite_type: 'SOFT', time_required_minutes: 30, cognitive_effort: 3 },
  { id: 'de15', source: 'fraction-addition', target: 'fraction-division', type: 'PREREQUISITE_OF', prerequisite_type: 'OPTIONAL', time_required_minutes: 25, cognitive_effort: 3 },
];

/**
 * Load the demo knowledge graph via the backend API and refresh the store.
 * Returns true when the graph was loaded successfully.
 */
export async function loadDemoData(): Promise<boolean> {
  const store = useGraphStore.getState();

  if (store.nodes.length > 0) {
    const confirmed = window.confirm(
      'Loading demo data will replace the current graph (the database will be reset). Continue?'
    );
    if (!confirmed) return false;
  }

  store.setLoading(true);
  store.setError(null);

  try {
    if (store.nodes.length > 0) {
      await api.resetDatabase();
    }

    // Clear the canvas immediately so the UI reflects the incoming graph
    const clearing = useGraphStore.getState();
    clearing.clearGraph();
    clearing.clearOptimization();

    for (const node of DEMO_NODES) {
      await api.createNode(node);
    }
    for (const edge of DEMO_EDGES) {
      await api.createRelationship(edge);
    }

    const [nodesData, edgesData, statsData] = await Promise.all([
      api.getNodes(),
      api.getRelationships(),
      api.getStats(),
    ]);

    const state = useGraphStore.getState();
    state.setNodes(nodesData);
    state.setEdges(edgesData);
    state.setStats(statsData);
    state.setTargetNodeId(DEMO_TARGET_ID);
    return true;
  } catch (err: any) {
    useGraphStore.getState().setError(err?.message || 'Failed to load demo data');
    return false;
  } finally {
    useGraphStore.getState().setLoading(false);
  }
}