/** Main page: Toolbar + Left panel + React Flow canvas + Right panel + Compare modal. */

'use client';

import React, { useCallback, useState } from 'react';
import { ReactFlowProvider } from 'reactflow';
import Toolbar from '@/components/Toolbar';
import LeftPanel from '@/components/panels/LeftPanel';
import RightPanel from '@/components/panels/RightPanel';
import GraphView from '@/components/graph/GraphView';
import CompareModal from '@/components/compare/CompareModal';
import { usePipelineStore } from '@/store/pipelineStore';

export default function Home() {
  const [compareOpen, setCompareOpen] = useState(false);
  const {
    compareResult, isComparing, activeSolver, setActiveSolver,
    setSelectedNode, setSelectedEdge,
  } = usePipelineStore();

  const openCompare = useCallback(() => setCompareOpen(true), []);
  const closeCompare = useCallback(() => setCompareOpen(false), []);

  const handleNodeClick = useCallback(
    (nodeId: string) => {
      setSelectedNode(nodeId);
      setSelectedEdge(null);
    },
    [setSelectedNode, setSelectedEdge]
  );

  const handleEdgeClick = useCallback(
    (edgeId: string) => {
      setSelectedEdge(edgeId);
      setSelectedNode(null);
    },
    [setSelectedEdge, setSelectedNode]
  );

  return (
    <ReactFlowProvider>
      <div className="h-screen w-screen flex flex-col overflow-hidden bg-gray-50">
        <Toolbar onOpenCompare={openCompare} />

        <div className="flex-1 flex overflow-hidden min-h-0">
          <LeftPanel />

          <main className="flex-1 relative min-w-0">
            <GraphView
              onNodeClick={handleNodeClick}
              onEdgeClick={handleEdgeClick}
            />
          </main>

          <RightPanel />
        </div>

        <CompareModal
          open={compareOpen}
          result={compareResult}
          isLoading={isComparing}
          activeSolver={activeSolver}
          onClose={closeCompare}
          onSelectSolver={setActiveSolver}
          onPreviewTraversal={() => {}}
        />
      </div>
    </ReactFlowProvider>
  );
}
