/**
 * React Flow canvas.
 *
 * Clean visuals per spec: nodes show only the name, edges only the relationship
 * type. All remaining metadata (time, effort, cost, relevance, learning value)
 * lives in the side panels / click drawer.
 *
 * When an optimisation or comparison result is present, the selected solver's
 * path is highlighted in green on both nodes and edges.
 */

'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  NodeTypes,
  EdgeTypes,
  Connection,
  Edge,
  Node,
  useReactFlow,
  Panel,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { ConceptNode } from './ConceptNode';
import ConceptEdge from './ConceptEdge';
import { usePipelineStore } from '@/store/pipelineStore';
import { cn } from '@/lib/utils';
import { Maximize2, Search, Settings, Info, Loader2 } from 'lucide-react';
import type { SolverMetrics } from '@/lib/pipelineTypes';

const nodeTypes: NodeTypes = { conceptNode: ConceptNode };
const edgeTypes: EdgeTypes = { conceptEdge: ConceptEdge };

// Layered layout: longest-path layering, then barycentre ordering inside layers
// so prerequisite chains read left-to-right without needing an edge-router.
function layoutGraph(
  nodeIds: string[],
  edges: Array<{ source: string; target: string; prerequisite: boolean }>
): Record<string, { x: number; y: number }> {
  const HORIZONTAL_GAP = 300;
  const VERTICAL_GAP = 190;

  const prereqEdges = edges.filter((e) => e.prerequisite);
  const indegree = new Map<string, number>(nodeIds.map((id) => [id, 0]));
  const successors = new Map<string, string[]>(nodeIds.map((id) => [id, []]));

  for (const e of prereqEdges) {
    if (!indegree.has(e.source) || !indegree.has(e.target)) continue;
    indegree.set(e.target, (indegree.get(e.target) ?? 0) + 1);
    successors.get(e.source)!.push(e.target);
  }

  // Kahn layering -> prerequisite depth.
  const layer = new Map<string, number>(nodeIds.map((id) => [id, 0]));
  const queue = nodeIds.filter((id) => (indegree.get(id) ?? 0) === 0);
  const order: string[] = [];
  const remaining = new Map(indegree);

  while (queue.length) {
    const id = queue.shift()!;
    order.push(id);
    for (const next of successors.get(id) ?? []) {
      layer.set(next, Math.max(layer.get(next) ?? 0, (layer.get(id) ?? 0) + 1));
      const left = (remaining.get(next) ?? 0) - 1;
      remaining.set(next, left);
      if (left === 0) queue.push(next);
    }
  }

  // Nodes left with a non-zero indegree sit in a cycle; park them in column 0.
  for (const id of nodeIds) if (!order.includes(id)) order.push(id);

  const layers = new Map<number, string[]>();
  for (const id of order) {
    const depth = layer.get(id) ?? 0;
    if (!layers.has(depth)) layers.set(depth, []);
    layers.get(depth)!.push(id);
  }

  const positions: Record<string, { x: number; y: number }> = {};
  for (const [depth, ids] of [...layers.entries()].sort((a, b) => a[0] - b[0])) {
    const height = ids.length * VERTICAL_GAP;
    ids.forEach((id, index) => {
      positions[id] = {
        x: depth * HORIZONTAL_GAP,
        y: index * VERTICAL_GAP - height / 2 + VERTICAL_GAP / 2,
      };
    });
  }
  return positions;
}

export default function GraphView({
  onNodeClick,
  onEdgeClick,
}: {
  onNodeClick?: (nodeId: string) => void;
  onEdgeClick?: (edgeId: string) => void;
}) {
  const {
    nodes, edges, selectedNodeId, selectedEdgeId,
    optimizeResult, compareResult, activeSolver,
    isOptimizing, isComparing,
    setSelectedNode, setSelectedEdge,
  } = usePipelineStore();

  const [showMinimap, setShowMinimap] = useState(true);
  const [showControls, setShowControls] = useState(true);
  const [didFit, setDidFit] = useState(false);

  const { fitView } = useReactFlow();

  // ---- Which solver's path is currently painted? --------------------------
  const activeMetrics: SolverMetrics | null = useMemo(() => {
    if (compareResult && activeSolver) {
      return (
        compareResult.comparison.results.find((r) => r.solver === activeSolver) ?? null
      );
    }
    if (optimizeResult && !compareResult) return optimizeResult.result;
    return null;
  }, [compareResult, optimizeResult, activeSolver]);

  const pathNodes = useMemo(
    () => new Set(activeMetrics?.is_feasible ? activeMetrics.path_nodes : []),
    [activeMetrics]
  );
  const pathEdges = useMemo(
    () => new Set(activeMetrics?.is_feasible ? activeMetrics.path_edges : []),
    [activeMetrics]
  );
  const hardNodes = useMemo(
    () =>
      new Set(
        compareResult?.subgraph_nodes
          .filter((n) => n.is_hard_prerequisite)
          .map((n) => n.node_id) ??
          optimizeResult?.subgraph_nodes
            .filter((n) => n.is_hard_prerequisite)
            .map((n) => n.node_id) ??
          []
      ),
    [compareResult, optimizeResult]
  );

  const positions = useMemo(
    () =>
      layoutGraph(
        nodes.map((n) => n.id),
        edges.map((e) => ({
          source: e.source,
          target: e.target,
          prerequisite: e.type === 'PREREQUISITE_OF',
        }))
      ),
    [nodes, edges]
  );

  const rfNodes: Node[] = useMemo(
    () =>
      nodes.map((node) => {
        const inPath = pathNodes.has(node.id);
        const isHard = inPath && hardNodes.has(node.id);
        return {
          id: node.id,
          type: 'conceptNode',
          position: positions[node.id] ?? { x: 0, y: 0 },
          selected: node.id === selectedNodeId,
          draggable: !isOptimizing,
          data: {
            label: node.name,
            fullData: node,
            isOptimized: inPath,
            isHardPrereq: isHard,
          },
          style: inPath
            ? {
                borderColor: isHard ? '#ef4444' : '#22c55e',
                boxShadow: isHard ? '0 0 0 3px #fecaca' : '0 0 0 3px #bbf7d0',
              }
            : undefined,
        };
      }),
    [nodes, positions, pathNodes, hardNodes, selectedNodeId, isOptimizing]
  );

  const rfEdges: Edge[] = useMemo(
    () =>
      edges.map((edge) => {
        const inPath = pathEdges.has(edge.id);
        const isPrerequisite = edge.type === 'PREREQUISITE_OF';
        return {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          type: 'conceptEdge',
          selected: edge.id === selectedEdgeId,
          animated: inPath,
          data: {
            label: edge.type,
            fullData: edge,
            isOptimized: inPath,
          },
          style: {
            stroke: inPath ? '#22c55e' : isPrerequisite ? '#38bdf8' : '#a855f7',
            strokeWidth: inPath ? 3 : 2,
          },
        };
      }),
    [edges, pathEdges, selectedEdgeId]
  );

  // Re-fit when the path changes so the highlighted route is visible.
  useEffect(() => {
    if (nodes.length === 0) return;
    const timer = setTimeout(() => {
      fitView({ duration: 400, padding: 0.18 });
      setDidFit(true);
    }, 120);
    return () => clearTimeout(timer);
  }, [nodes.length, pathNodes.size, fitView]);

  const handleNodeClick = useCallback(
    (_e: React.MouseEvent, node: Node) => {
      setSelectedNode(node.id);
      setSelectedEdge(null);
      onNodeClick?.(node.id);
    },
    [onNodeClick, setSelectedNode, setSelectedEdge]
  );

  const handleEdgeClick = useCallback(
    (_e: React.MouseEvent, edge: Edge) => {
      setSelectedEdge(edge.id);
      setSelectedNode(null);
      onEdgeClick?.(edge.id);
    },
    [onEdgeClick, setSelectedEdge, setSelectedNode]
  );

  const handlePaneClick = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
  }, [setSelectedNode, setSelectedEdge]);

  const onConnect = useCallback((c: Connection) => {
    console.log('New connection:', c);
  }, []);

  const busy = isOptimizing || isComparing;

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        onPaneClick={handlePaneClick}
        onConnect={onConnect}
        fitView={false}
        minZoom={0.05}
        maxZoom={2.5}
        nodesDraggable={!busy}
        nodesConnectable={!busy}
        elementsSelectable
        selectNodesOnDrag={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#e5e7eb" gap={18} size={1} style={{ opacity: 0.5 }} />
        <Controls
          className="top-right"
          showZoom={showControls}
          showFitView={showControls}
          showInteractive={showControls}
        />
        {showMinimap && (
          <MiniMap
            pannable
            zoomable
            nodeColor={(node) => {
              const data = node.data as any;
              if (data?.isHardPrereq) return '#ef4444';
              if (data?.isOptimized) return '#22c55e';
              return '#94a3b8';
            }}
            maskColor="rgba(148, 163, 184, 0.25)"
          />
        )}
        <Panel position="bottom-left" className="!m-3">
          <div className="flex items-center gap-2 text-xs text-gray-600 bg-white/90 backdrop-blur-sm px-2.5 py-1 rounded border">
            <span>{nodes.length} nodes</span>
            <span className="text-gray-300">|</span>
            <span>{edges.length} edges</span>
            {activeMetrics && (
              <>
                <span className="text-gray-300">|</span>
                <span className="font-medium text-green-700">
                  {pathNodes.size} on optimal path
                </span>
              </>
            )}
          </div>
        </Panel>
      </ReactFlow>

      {/* Toolbar overlay */}
      <div className="absolute top-4 left-4 flex flex-col gap-2 z-10 pointer-events-none">
        <div className="flex gap-1 bg-white/90 backdrop-blur-sm rounded-lg border p-1 shadow-lg pointer-events-auto">
          <button
            onClick={() => fitView({ duration: 300, padding: 0.18 })}
            className="p-2 rounded hover:bg-gray-100 transition-colors"
            title="Fit view"
          >
            <Maximize2 className="w-5 h-5 text-gray-600" />
          </button>
          <button
            onClick={() => setShowMinimap((v) => !v)}
            className={cn(
              'p-2 rounded transition-colors',
              showMinimap ? 'bg-primary-100 text-primary-600' : 'hover:bg-gray-100 text-gray-600'
            )}
            title="Toggle minimap"
          >
            <Search className="w-5 h-5" />
          </button>
          <button
            onClick={() => setShowControls((v) => !v)}
            className={cn(
              'p-2 rounded transition-colors',
              showControls ? 'bg-primary-100 text-primary-600' : 'hover:bg-gray-100 text-gray-600'
            )}
            title="Toggle controls"
          >
            <Settings className="w-5 h-5" />
          </button>
        </div>

        {/* Legend */}
        <div className="bg-white/95 backdrop-blur-sm rounded-lg border shadow-lg p-3 min-w-[210px] pointer-events-auto">
          <div className="font-semibold text-gray-900 mb-2 flex items-center gap-1">
            <Info className="w-4 h-4 text-primary-600" />
            Legend
          </div>
          <div className="space-y-1.5 text-xs text-gray-700">
            <LegendRow
              swatch={<span className="w-5 h-0.5 bg-blue-400 rounded" />}
              label="PREREQUISITE_OF"
            />
            <LegendRow
              swatch={
                <span
                  className="w-5 h-0.5 rounded"
                  style={{ borderTop: '2px dashed #a855f7' }}
                />
              }
              label="PART_OF"
            />
            <LegendRow
              swatch={<span className="w-4 h-4 rounded border-2 border-red-400 bg-red-50" />}
              label="Hard prerequisite"
            />
            <LegendRow
              swatch={<span className="w-4 h-4 rounded border-2 border-green-400 bg-green-50" />}
              label="On optimal path"
            />
          </div>
        </div>
      </div>

      {/* Busy overlay */}
      {busy && (
        <div className="absolute inset-0 bg-white/70 backdrop-blur-sm flex items-center justify-center z-20 pointer-events-none">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-10 h-10 text-primary-600 animate-spin" />
            <p className="text-gray-700 font-medium text-sm">
              {isComparing ? 'Comparing solvers…' : 'Optimizing path…'}
            </p>
          </div>
        </div>
      )}

      {/* Empty state */}
      {nodes.length === 0 && !busy && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="text-center text-gray-500 p-8 max-w-sm">
            <svg
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              className="w-16 h-16 mx-auto mb-4 text-gray-300"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
              />
            </svg>
            <h3 className="text-lg font-medium text-gray-900 mb-1">No concepts yet</h3>
            <p className="text-sm">
              Add nodes via the left panel, or open{' '}
              <span className="font-medium">Settings → Load Sample Data</span> in the
              toolbar.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function LegendRow({ swatch, label }: { swatch: React.ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-5 flex justify-center shrink-0">{swatch}</span>
      <span>{label}</span>
    </div>
  );
}
