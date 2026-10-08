/** Left panel — CRUD forms plus the runtime Calculations & Metrics inspector. */

'use client';

import React, { useMemo, useState } from 'react';
import { usePipelineStore } from '@/store/pipelineStore';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import {
  Plus, Trash2, Save, X, ChevronDown, ChevronUp,
  Circle, Link2, Calculator, Sigma, Route, Clock, Coins, Gauge, Layers,
  Sparkles, Lock,
} from 'lucide-react';
import type { NodeResponse, RelationshipResponse } from '@/types';
import type { NodeMetrics, EdgeMetrics } from '@/lib/pipelineTypes';

type Tab = 'nodes' | 'edges' | 'metrics';

export function LeftPanel() {
  const [tab, setTab] = useState<Tab>('nodes');
  const [nodeFormOpen, setNodeFormOpen] = useState(false);
  const [edgeFormOpen, setEdgeFormOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const {
    nodes, edges, selectedNodeId, selectedEdgeId,
    addNode, removeNode, addEdge, removeEdge,
    setSelectedNode, setSelectedEdge,
    setError, clearResults,
  } = usePipelineStore();

  const [nodeForm, setNodeForm] = useState({
    id: '', name: '', description: '', target_relevance: 0.5, downstream_utility: 0.5,
  });
  const [edgeForm, setEdgeForm] = useState<{
    id: string;
    source: string;
    target: string;
    type: string;
    prerequisite_type: string | null;
    time_required_minutes: number;
    cognitive_effort: number;
  }>({
    id: '', source: '', target: '', type: 'PREREQUISITE_OF',
    prerequisite_type: 'HARD', time_required_minutes: 20, cognitive_effort: 3,
  });

  const selectedNode = nodes.find((n) => n.id === selectedNodeId) ?? null;
  const selectedEdge = edges.find((e) => e.id === selectedEdgeId) ?? null;

  // ---- Node CRUD ---------------------------------------------------------
  const handleAddNode = async () => {
    setFormError(null);
    if (!nodeForm.id.trim()) return setFormError('Node ID is required');
    if (!nodeForm.name.trim()) return setFormError('Node name is required');
    if (nodes.some((n) => n.id === nodeForm.id)) return setFormError('Node ID already exists');
    if (!/^[a-zA-Z0-9_-]+$/.test(nodeForm.id)) {
      return setFormError('ID may only contain letters, numbers, _ and -');
    }

    try {
      setBusy(true);
      const created = await api.createNode(nodeForm as any);
      addNode(created);
      clearResults();
      setNodeForm({ id: '', name: '', description: '', target_relevance: 0.5, downstream_utility: 0.5 });
      setNodeFormOpen(false);
    } catch (err: any) {
      setFormError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteNode = async (nodeId: string) => {
    if (!confirm(`Delete "${nodeId}" and all its relationships?`)) return;
    try {
      setBusy(true);
      await api.deleteNode(nodeId);
      removeNode(nodeId);
      clearResults();
      if (selectedNodeId === nodeId) setSelectedNode(null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  // ---- Relationship CRUD -------------------------------------------------
  const handleAddEdge = async () => {
    setFormError(null);
    if (!edgeForm.id.trim()) return setFormError('Relationship ID is required');
    if (!edgeForm.source) return setFormError('Source is required');
    if (!edgeForm.target) return setFormError('Target is required');
    if (edgeForm.source === edgeForm.target) return setFormError('Self-loops are not allowed');
    if (edges.some((e) => e.id === edgeForm.id)) return setFormError('Relationship ID already exists');
    if (edgeForm.type === 'PREREQUISITE_OF' && !edgeForm.prerequisite_type) {
      return setFormError('Prerequisite type is required for PREREQUISITE_OF');
    }

    try {
      setBusy(true);
      const payload = {
        ...edgeForm,
        prerequisite_type:
          edgeForm.type === 'PREREQUISITE_OF' ? edgeForm.prerequisite_type : null,
      };
      const created = await api.createRelationship(payload as any);
      addEdge(created);
      clearResults();
      setEdgeForm({
        id: '', source: '', target: '', type: 'PREREQUISITE_OF',
        prerequisite_type: 'HARD', time_required_minutes: 20, cognitive_effort: 3,
      });
      setEdgeFormOpen(false);
    } catch (err: any) {
      setFormError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteEdge = async (edgeId: string) => {
    if (!confirm(`Delete relationship "${edgeId}"?`)) return;
    try {
      setBusy(true);
      await api.deleteRelationship(edgeId);
      removeEdge(edgeId);
      clearResults();
      if (selectedEdgeId === edgeId) setSelectedEdge(null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="w-80 shrink-0 h-full bg-white border-r border-gray-200 flex flex-col overflow-hidden">
      {/* Tabs */}
      <div className="flex border-b border-gray-200 shrink-0">
        {(
          [
            { id: 'nodes' as Tab, label: 'Nodes', Icon: Circle },
            { id: 'edges' as Tab, label: 'Edges', Icon: Link2 },
            { id: 'metrics' as Tab, label: 'Metrics', Icon: Calculator },
          ]
        ).map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn(
              'flex-1 px-2 py-2.5 text-xs font-medium transition-colors flex items-center justify-center gap-1',
              tab === id
                ? 'text-primary-600 border-b-2 border-primary-600 bg-primary-50/50'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
            )}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {formError && (
          <div className="flex items-start gap-2 text-xs text-red-700 bg-red-50 border border-red-200 p-2 rounded">
            <X className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            <span>{formError}</span>
            <button onClick={() => setFormError(null)} className="ml-auto shrink-0">
              <X className="w-3 h-3" />
            </button>
          </div>
        )}

        {/* ============================ NODES ============================ */}
        {tab === 'nodes' && (
          <>
            <button
              onClick={() => setNodeFormOpen((v) => !v)}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 text-sm font-medium"
            >
              <Plus className="w-4 h-4" /> Add Node
            </button>

            {nodeFormOpen && (
              <div className="space-y-2.5 p-3 bg-gray-50 rounded-lg border">
                <h3 className="font-semibold text-sm text-gray-900">New Node</h3>
                <Field label="ID *">
                  <input
                    value={nodeForm.id}
                    onChange={(e) => setNodeForm({ ...nodeForm, id: e.target.value })}
                    placeholder="e.g. matrices"
                    className={INPUT}
                  />
                </Field>
                <Field label="Name *">
                  <input
                    value={nodeForm.name}
                    onChange={(e) => setNodeForm({ ...nodeForm, name: e.target.value })}
                    placeholder="e.g. Linear Algebra"
                    className={INPUT}
                  />
                </Field>
                <Field label="Description">
                  <textarea
                    value={nodeForm.description}
                    onChange={(e) => setNodeForm({ ...nodeForm, description: e.target.value })}
                    rows={2}
                    className={INPUT}
                  />
                </Field>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Target relevance">
                    <input
                      type="number" min={0} max={1} step={0.05}
                      value={nodeForm.target_relevance}
                      onChange={(e) =>
                        setNodeForm({ ...nodeForm, target_relevance: parseFloat(e.target.value) })
                      }
                      className={INPUT}
                    />
                  </Field>
                  <Field label="Downstream utility">
                    <input
                      type="number" min={0} max={1} step={0.05}
                      value={nodeForm.downstream_utility}
                      onChange={(e) =>
                        setNodeForm({ ...nodeForm, downstream_utility: parseFloat(e.target.value) })
                      }
                      className={INPUT}
                    />
                  </Field>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleAddNode}
                    disabled={busy}
                    className="flex-1 flex items-center justify-center gap-1 px-3 py-1.5 bg-green-600 text-white rounded-md hover:bg-green-700 text-sm disabled:opacity-50"
                  >
                    <Save className="w-4 h-4" /> Create
                  </button>
                  <button
                    onClick={() => setNodeFormOpen(false)}
                    className="flex-1 px-3 py-1.5 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300 text-sm"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            <SectionTitle count={nodes.length} noun="node" />
            <div className="space-y-1.5">
              {nodes.map((node) => (
                <NodeRow
                  key={node.id}
                  node={node}
                  selected={selectedNodeId === node.id}
                  onSelect={() => setSelectedNode(node.id)}
                  onDelete={() => handleDeleteNode(node.id)}
                />
              ))}
              {nodes.length === 0 && (
                <p className="text-sm text-gray-400 text-center py-6">
                  No nodes yet — add one above.
                </p>
              )}
            </div>

            {selectedNode && <NodeDetail node={selectedNode} />}
          </>
        )}

        {/* ============================ EDGES ============================ */}
        {tab === 'edges' && (
          <>
            <button
              onClick={() => setEdgeFormOpen((v) => !v)}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 text-sm font-medium"
            >
              <Plus className="w-4 h-4" /> Add Relationship
            </button>

            {edgeFormOpen && (
              <div className="space-y-2.5 p-3 bg-gray-50 rounded-lg border">
                <h3 className="font-semibold text-sm text-gray-900">New Relationship</h3>
                <Field label="ID *">
                  <input
                    value={edgeForm.id}
                    onChange={(e) => setEdgeForm({ ...edgeForm, id: e.target.value })}
                    placeholder="e.g. r1"
                    className={INPUT}
                  />
                </Field>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Source *">
                    <select
                      value={edgeForm.source}
                      onChange={(e) => setEdgeForm({ ...edgeForm, source: e.target.value })}
                      className={INPUT}
                    >
                      <option value="">Select…</option>
                      {nodes.map((n) => (
                        <option key={n.id} value={n.id}>{n.name}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Target *">
                    <select
                      value={edgeForm.target}
                      onChange={(e) => setEdgeForm({ ...edgeForm, target: e.target.value })}
                      className={INPUT}
                    >
                      <option value="">Select…</option>
                      {nodes.map((n) => (
                        <option key={n.id} value={n.id}>{n.name}</option>
                      ))}
                    </select>
                  </Field>
                </div>
                <Field label="Relationship type *">
                  <select
                    value={edgeForm.type}
                    onChange={(e) => {
                      const type = e.target.value;
                      setEdgeForm({
                        ...edgeForm,
                        type,
                        prerequisite_type: type === 'PREREQUISITE_OF' ? 'HARD' : null,
                      });
                    }}
                    className={INPUT}
                  >
                    <option value="PREREQUISITE_OF">PREREQUISITE_OF</option>
                    <option value="PART_OF">PART_OF</option>
                  </select>
                </Field>
                {edgeForm.type === 'PREREQUISITE_OF' && (
                  <Field label="Prerequisite type *">
                    <select
                      value={edgeForm.prerequisite_type ?? ''}
                      onChange={(e) => setEdgeForm({ ...edgeForm, prerequisite_type: e.target.value })}
                      className={INPUT}
                    >
                      <option value="HARD">HARD — mandatory</option>
                      <option value="SOFT">SOFT — skippable w/ penalty</option>
                      <option value="OPTIONAL">OPTIONAL — free to skip</option>
                    </select>
                  </Field>
                )}
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Time (min)">
                    <input
                      type="number" min={1}
                      value={edgeForm.time_required_minutes}
                      onChange={(e) =>
                        setEdgeForm({ ...edgeForm, time_required_minutes: parseInt(e.target.value) })
                      }
                      className={INPUT}
                    />
                  </Field>
                  <Field label="Effort (1-5)">
                    <input
                      type="number" min={1} max={5}
                      value={edgeForm.cognitive_effort}
                      onChange={(e) =>
                        setEdgeForm({ ...edgeForm, cognitive_effort: parseInt(e.target.value) })
                      }
                      className={INPUT}
                    />
                  </Field>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleAddEdge}
                    disabled={busy}
                    className="flex-1 flex items-center justify-center gap-1 px-3 py-1.5 bg-green-600 text-white rounded-md hover:bg-green-700 text-sm disabled:opacity-50"
                  >
                    <Save className="w-4 h-4" /> Create
                  </button>
                  <button
                    onClick={() => setEdgeFormOpen(false)}
                    className="flex-1 px-3 py-1.5 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300 text-sm"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            <SectionTitle count={edges.length} noun="relationship" />
            <div className="space-y-1.5">
              {edges.map((edge) => (
                <EdgeRow
                  key={edge.id}
                  edge={edge}
                  nodeName={(id) => nodes.find((n) => n.id === id)?.name ?? id}
                  selected={selectedEdgeId === edge.id}
                  onSelect={() => setSelectedEdge(edge.id)}
                  onDelete={() => handleDeleteEdge(edge.id)}
                />
              ))}
              {edges.length === 0 && (
                <p className="text-sm text-gray-400 text-center py-6">
                  No relationships yet — connect the nodes above.
                </p>
              )}
            </div>

            {selectedEdge && (
              <div className="p-3 bg-primary-50 rounded-lg border border-primary-200">
                <h3 className="font-semibold text-xs text-primary-900 mb-2">Selected Relationship</h3>
                <dl className="space-y-0.5 text-xs text-primary-800">
                  <Row k="ID" v={selectedEdge.id} />
                  <Row k="Source" v={selectedEdge.source} />
                  <Row k="Target" v={selectedEdge.target} />
                  <Row k="Type" v={selectedEdge.type} />
                  <Row k="Prereq type" v={selectedEdge.prerequisite_type ?? '—'} />
                  <Row k="Time" v={`${selectedEdge.time_required_minutes} min`} />
                  <Row k="Effort" v={`${selectedEdge.cognitive_effort} / 5`} />
                </dl>
              </div>
            )}
          </>
        )}

        {/* =========================== METRICS =========================== */}
        {tab === 'metrics' && <MetricsTab />}
      </div>
    </aside>
  );
}

const INPUT =
  'w-full px-2 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-white';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-700 mb-1">{label}</label>
      {children}
    </div>
  );
}

function SectionTitle({ count, noun }: { count: number; noun: string }) {
  return (
    <h3 className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider pt-1">
      {noun}s ({count})
    </h3>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex gap-2">
      <dt className="font-medium shrink-0">{k}:</dt>
      <dd className="truncate">{v}</dd>
    </div>
  );
}

// ============================================================================
// ROWS
// ============================================================================

function NodeRow({
  node, selected, onSelect, onDelete,
}: {
  node: NodeResponse;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const learningValue = (node.target_relevance + node.downstream_utility) / 2;
  return (
    <div
      onClick={onSelect}
      className={cn(
        'p-2 rounded-lg border cursor-pointer transition-all',
        selected
          ? 'border-primary-500 bg-primary-50 shadow-sm'
          : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-sm text-gray-900 truncate">{node.name}</span>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="p-1 text-red-500 hover:bg-red-50 rounded shrink-0"
          title="Delete node"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
      <div className="text-[11px] text-gray-500 mt-0.5 font-mono">{node.id}</div>
      <div className="flex items-center gap-2 mt-1 text-[11px] text-gray-600">
        <span>rel {node.target_relevance.toFixed(2)}</span>
        <span className="text-gray-300">·</span>
        <span>util {node.downstream_utility.toFixed(2)}</span>
        <span className="text-gray-300">·</span>
        <span className="font-medium text-primary-700">
          LV {learningValue.toFixed(3)}
        </span>
      </div>
    </div>
  );
}

function EdgeRow({
  edge, nodeName, selected, onSelect, onDelete,
}: {
  edge: RelationshipResponse;
  nodeName: (id: string) => string;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const isPrereq = edge.type === 'PREREQUISITE_OF';
  return (
    <div
      onClick={onSelect}
      className={cn(
        'p-2 rounded-lg border cursor-pointer transition-all',
        selected
          ? 'border-primary-500 bg-primary-50 shadow-sm'
          : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm text-gray-900 truncate">
          <span className="font-medium">{nodeName(edge.source)}</span>
          <span className="text-gray-400 mx-1">→</span>
          <span className="font-medium">{nodeName(edge.target)}</span>
        </span>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="p-1 text-red-500 hover:bg-red-50 rounded shrink-0"
          title="Delete relationship"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
        <span
          className={cn(
            'px-1.5 py-0.5 rounded text-[10px] font-medium',
            isPrereq ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700'
          )}
        >
          {edge.type}
        </span>
        {edge.prerequisite_type && (
          <span
            className={cn(
              'px-1.5 py-0.5 rounded text-[10px] font-medium',
              edge.prerequisite_type === 'HARD' && 'bg-red-100 text-red-700',
              edge.prerequisite_type === 'SOFT' && 'bg-yellow-100 text-yellow-700',
              edge.prerequisite_type === 'OPTIONAL' && 'bg-green-100 text-green-700'
            )}
          >
            {edge.prerequisite_type}
          </span>
        )}
        <span className="text-[11px] text-gray-500 ml-auto flex items-center gap-1.5">
          <span className="flex items-center gap-0.5">
            <Clock className="w-3 h-3" />
            {edge.time_required_minutes}m
          </span>
          <span>eff {edge.cognitive_effort}/5</span>
        </span>
      </div>
    </div>
  );
}

function NodeDetail({ node }: { node: NodeResponse }) {
  const learningValue = (node.target_relevance + node.downstream_utility) / 2;
  return (
    <div className="p-3 bg-primary-50 rounded-lg border border-primary-200">
      <h3 className="font-semibold text-xs text-primary-900 mb-2">Selected Node</h3>
      <dl className="space-y-0.5 text-xs text-primary-800">
        <Row k="ID" v={<span className="font-mono">{node.id}</span>} />
        <Row k="Name" v={node.name} />
        {node.description && <Row k="Description" v={node.description} />}
        <Row k="Target relevance" v={node.target_relevance.toFixed(3)} />
        <Row k="Downstream utility" v={node.downstream_utility.toFixed(3)} />
        <Row
          k="Learning value"
          v={<span className="font-semibold">{learningValue.toFixed(4)}</span>}
        />
      </dl>
      <p className="text-[10px] text-primary-600 mt-2 pt-2 border-t border-primary-200">
        LearningValue = (target_relevance + downstream_utility) / 2
      </p>
    </div>
  );
}

// ============================================================================
// METRICS TAB
// ============================================================================

function MetricsTab() {
  const { optimizeResult, compareResult, activeSolver, nodes, edges } = usePipelineStore();
  const [open, setOpen] = useState<Record<string, boolean>>({ summary: true });

  const source = compareResult ?? optimizeResult;
  const nodeMetrics: NodeMetrics[] = useMemo(
    () => (source ? source.subgraph_nodes : []),
    [source]
  );
  const edgeMetrics: EdgeMetrics[] = useMemo(
    () => (source ? source.subgraph_edges : []),
    [source]
  );

  const metrics = useMemo(() => {
    if (compareResult && activeSolver) {
      return (
        compareResult.comparison.results.find((r) => r.solver === activeSolver) ?? null
      );
    }
    return optimizeResult?.result ?? null;
  }, [compareResult, activeSolver, optimizeResult]);

  if (!source || !metrics) {
    return (
      <div className="text-center py-10 text-gray-400">
        <Calculator className="w-12 h-12 mx-auto mb-3 opacity-40" />
        <p className="text-sm">Run Optimize or Compare to see calculations</p>
      </div>
    );
  }

  const toggle = (key: string) => setOpen((o) => ({ ...o, [key]: !o[key] }));

  const selectedNodes = new Set(metrics.path_nodes);
  const selectedEdges = new Set(metrics.path_edges);
  const maxEdgeTime = Math.max(...edgeMetrics.map((e) => e.raw_time_minutes), 1);

  return (
    <div className="space-y-2.5">
      {/* Solver result summary */}
      <div
        className={cn(
          'p-3 rounded-lg border',
          metrics.is_feasible
            ? 'bg-green-50 border-green-200'
            : 'bg-red-50 border-red-200'
        )}
      >
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-semibold text-sm text-gray-900">{metrics.display_name}</h3>
          <span
            className={cn(
              'px-2 py-0.5 rounded-full text-[10px] font-medium',
              metrics.is_feasible
                ? 'bg-green-600 text-white'
                : 'bg-red-600 text-white'
            )}
          >
            {metrics.is_feasible ? 'VALID' : 'INVALID'}
          </span>
        </div>
        {!metrics.is_feasible && (
          <p className="text-xs text-red-700 mt-1">{metrics.feasibility_reason}</p>
        )}
        <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 mt-2.5 text-xs">
          <Metric
            label="Path Score"
            value={metrics.path_score.toFixed(4)}
            highlight
          />
          <Metric label="Net Utility" value={metrics.net_utility.toFixed(4)} />
          <Metric label="Path Cost" value={metrics.total_path_cost.toFixed(4)} />
          <Metric label="Avg Value" value={metrics.average_learning_value.toFixed(4)} />
          <Metric label="Time" value={`${metrics.total_time_minutes} min`} />
          <Metric label="Runtime" value={`${metrics.execution_time_ms.toFixed(1)} ms`} />
        </div>
      </div>

      {/* Formulas */}
      <Collapsible id="formulas" title="Runtime formulas" open={open.formulas} onToggle={toggle}>
        <div className="space-y-1.5 text-[11px] font-mono text-gray-700">
          <Formula>n_time = t / {maxEdgeTime}</Formula>
          <Formula>n_effort = e / 5</Formula>
          <Formula>cost = (n_time + n_effort) / 2</Formula>
          <Formula>value = (rel + util) / 2</Formula>
          <Formula className="pt-1 border-t border-gray-200">
            PathScore = avgValue / (cost + 0.01)
          </Formula>
          <Formula>
            NetUtility = Σvalue − Σcost − penalties
          </Formula>
        </div>
        <p className="text-[10px] text-gray-500 mt-2 leading-relaxed">
          Normalisation uses <span className="font-medium">max time in the retrieved
          subgraph</span> ({maxEdgeTime} min), so costs are relative to the current
          target. Nothing here is written to Neo4j.
        </p>
      </Collapsible>

      {/* Edge cost table */}
      <Collapsible
        id="edges"
        title={`Edge costs (${edgeMetrics.length})`}
        open={open.edges}
        onToggle={toggle}
      >
        <div className="space-y-1 max-h-64 overflow-y-auto">
          {edgeMetrics.map((e) => (
            <div
              key={e.edge_id}
              className={cn(
                'p-2 rounded text-[11px] border',
                selectedEdges.has(e.edge_id)
                  ? 'bg-green-50 border-green-200'
                  : 'bg-gray-50 border-gray-100'
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-gray-900 truncate">
                  {e.source} → {e.target}
                </span>
                {selectedEdges.has(e.edge_id) && (
                  <span className="text-green-600 text-[10px] shrink-0">on path</span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-x-2 mt-1 font-mono text-gray-600">
                <span>raw {e.raw_time_minutes}m / e{e.raw_cognitive_effort}</span>
                <span>n_t {e.normalized_time.toFixed(3)}</span>
                <span>n_e {e.normalized_cognitive_effort.toFixed(3)}</span>
                <span className="font-semibold text-primary-700">
                  cost {e.edge_cost.toFixed(4)}
                </span>
              </div>
              <div className="mt-1 flex items-center gap-1.5">
                {e.relationship_type === 'PREREQUISITE_OF' ? (
                  <span
                    className={cn(
                      'px-1.5 py-0.5 rounded text-[9px] font-medium',
                      e.prerequisite_type === 'HARD' && 'bg-red-100 text-red-700',
                      e.prerequisite_type === 'SOFT' && 'bg-yellow-100 text-yellow-700',
                      e.prerequisite_type === 'OPTIONAL' && 'bg-green-100 text-green-700'
                    )}
                  >
                    {e.prerequisite_type}
                  </span>
                ) : (
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-purple-100 text-purple-700">
                    PART_OF
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </Collapsible>

      {/* Node metrics */}
      <Collapsible
        id="nodes"
        title={`Node metrics (${nodeMetrics.length})`}
        open={open.nodes}
        onToggle={toggle}
      >
        <div className="space-y-1 max-h-64 overflow-y-auto">
          {nodeMetrics.map((n) => (
            <div
              key={n.node_id}
              className={cn(
                'p-2 rounded text-[11px] border',
                selectedNodes.has(n.node_id)
                  ? 'bg-green-50 border-green-200'
                  : 'bg-gray-50 border-gray-100'
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-gray-900 truncate">{n.name}</span>
                <div className="flex items-center gap-1 shrink-0">
                  {n.is_hard_prerequisite && (
                    <Lock className="w-3 h-3 text-red-500" />
                  )}
                  <span
                    className={cn(
                      'text-[10px] font-medium',
                      selectedNodes.has(n.node_id) ? 'text-green-700' : 'text-gray-400'
                    )}
                  >
                    {selectedNodes.has(n.node_id) ? 'SELECTED' : 'skipped'}
                  </span>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-x-2 mt-1 font-mono text-gray-600">
                <span>rel {n.target_relevance.toFixed(2)}</span>
                <span>util {n.downstream_utility.toFixed(2)}</span>
                <span className="font-semibold text-primary-700">
                  value {n.learning_value.toFixed(4)}
                </span>
                <span>skip pen {n.skip_penalty.toFixed(2)}</span>
              </div>
            </div>
          ))}
        </div>
      </Collapsible>

      {/* Learning sequence */}
      <Collapsible
        id="sequence"
        title={`Learning sequence (${metrics.path_nodes.length} steps)`}
        open={open.sequence}
        onToggle={toggle}
      >
        <SequenceView />
      </Collapsible>

      {/* Traversal explanation */}
      <Collapsible
        id="traversal"
        title={`Traversal (${source.traversal.selected})`}
        open={open.traversal}
        onToggle={toggle}
      >
        <p className="text-[11px] text-gray-700 leading-relaxed">
          {source.traversal.reason}
        </p>
        {Object.keys(source.traversal.metrics).length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {Object.entries(source.traversal.metrics).map(([k, v]) => (
              <span
                key={k}
                className="px-1.5 py-0.5 rounded bg-gray-100 font-mono text-[10px] text-gray-700"
              >
                {k.replace(/_/g, ' ')}: {v}
              </span>
            ))}
          </div>
        )}
        {'traversal_stats' in source && source.traversal_stats && (
          <div className="mt-2 pt-2 border-t border-gray-200 space-y-0.5 text-[11px] font-mono text-gray-600">
            <div>
              graph {String(source.traversal_stats.full_graph_nodes)} nodes →{' '}
              {String(source.traversal_stats.retrieved_nodes)} retrieved (
              {String(source.traversal_stats.reduction_ratio)} reduction)
            </div>
          </div>
        )}
      </Collapsible>
    </div>
  );
}

function SequenceView() {
  const { optimizeResult, compareResult, activeSolver, setActiveSolver } = usePipelineStore();
  const sequence = useMemo(() => {
    if (compareResult && activeSolver) {
      return compareResult.learning_sequences[activeSolver] ?? [];
    }
    return optimizeResult?.learning_sequence ?? [];
  }, [compareResult, activeSolver, optimizeResult]);

  if (sequence.length === 0) {
    return <p className="text-[11px] text-gray-400 py-2">No sequence available.</p>;
  }

  return (
    <ol className="space-y-1">
      {sequence.map((step) => (
        <li
          key={step.node_id}
          className="flex items-start gap-2 p-2 rounded bg-white border border-gray-200"
        >
          <span className="w-5 h-5 shrink-0 rounded-full bg-primary-600 text-white text-[10px] font-bold flex items-center justify-center">
            {step.step}
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="font-medium text-xs text-gray-900 truncate">
                {step.name}
              </span>
              {step.is_hard_prerequisite && (
                <Lock className="w-3 h-3 text-red-500 shrink-0" />
              )}
            </div>
            {step.prerequisites.length > 0 && (
              <div className="text-[10px] text-gray-500 mt-0.5 truncate">
                ← {step.prerequisites.map((p) => p.source_name).join(', ')}
              </div>
            )}
          </div>
          <div className="text-right shrink-0">
            <div className="text-[10px] font-mono text-gray-700">
              v{step.learning_value.toFixed(2)}
            </div>
            <div className="text-[10px] text-gray-400">
              {step.estimated_time_minutes}m
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

// ============================================================================
// SMALL PRESENTATIONAL PIECES
// ============================================================================

function Metric({
  label, value, highlight,
}: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <div className="text-[10px] text-gray-500">{label}</div>
      <div
        className={cn(
          'font-mono font-semibold',
          highlight ? 'text-green-700' : 'text-gray-800'
        )}
      >
        {value}
      </div>
    </div>
  );
}

function Collapsible({
  id, title, open, onToggle, children,
}: {
  id: string;
  title: string;
  open: boolean;
  onToggle: (id: string) => void;
  children: React.ReactNode;
}) {
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => onToggle(id)}
        className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 hover:bg-gray-100 text-xs font-semibold text-gray-800"
      >
        <span>{title}</span>
        {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
      </button>
      {open && <div className="p-2.5">{children}</div>}
    </div>
  );
}

function Formula({
  children, className,
}: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('p-1.5 rounded bg-gray-50 border border-gray-100', className)}>
      {children}
    </div>
  );
}

export default LeftPanel;
