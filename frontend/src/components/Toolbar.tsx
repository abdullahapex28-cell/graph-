/** Top toolbar: AUTO/BFS/DFS method, optimizer selection, compare + optimize. */

'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { api, SOLVER_LABELS, TRAVERSAL_LABELS } from '@/lib/api';
import { usePipelineStore } from '@/store/pipelineStore';
import { cn } from '@/lib/utils';
import {
  Play, GitCompare, Loader2, Settings, Trash2, RefreshCw, Database,
  AlertCircle, CheckCircle2, ChevronDown, Sparkles, Route, Sigma, X,
} from 'lucide-react';
import type { SolverAlgorithm, TraversalStrategy } from '@/lib/pipelineTypes';

export function Toolbar({ onOpenCompare }: { onOpenCompare: () => void }) {
  const {
    nodes, edges, targetNodeId, searchMethod, solver, constraints, traversal,
    isOptimizing, isComparing, error, optimizeResult, compareResult, solverCatalogue,
    setNodes, setEdges, setTargetNodeId, setSearchMethod, setSolver,
    setConstraint, setTraversalConfig,
    setOptimizeResult, setCompareResult, setValidation, setSolverCatalogue,
    setOptimizing, setComparing, setError, clearResults,
  } = usePipelineStore();

  const [showSettings, setShowSettings] = useState(false);
  const [showCatalogue, setShowCatalogue] = useState(false);
  const [budgetInput, setBudgetInput] = useState('');
  const [depthInput, setDepthInput] = useState('');

  // ---- Initial load ------------------------------------------------------
  const loadGraph = useCallback(async () => {
    try {
      const [nodesData, edgesData] = await Promise.all([
        api.getNodes(),
        api.getRelationships(),
      ]);
      setNodes(nodesData);
      setEdges(edgesData);
    } catch (err: any) {
      setError(err.message);
    }
  }, [setNodes, setEdges, setError]);

  useEffect(() => {
    loadGraph();
    api.listSolvers().then((c) => setSolverCatalogue(c.solvers)).catch(() => {});
  }, [loadGraph, setSolverCatalogue]);

  // ---- Optimize (single solver) -----------------------------------------
  const handleOptimize = useCallback(async () => {
    if (!targetNodeId) {
      setError('Select a target node first');
      return;
    }
    try {
      setOptimizing(true);
      setError(null);
      const result = await api.optimizePath({
        target_node_id: targetNodeId,
        search_method: searchMethod,
        solver,
        constraints,
        traversal,
      });
      setOptimizeResult(result);
      setValidation(result.validation);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setOptimizing(false);
    }
  }, [targetNodeId, searchMethod, solver, constraints, traversal,
      setOptimizing, setError, setOptimizeResult, setValidation]);

  // ---- Compare all solvers ----------------------------------------------
  const handleCompare = useCallback(async () => {
    if (!targetNodeId) {
      setError('Select a target node first');
      return;
    }
    try {
      setComparing(true);
      setError(null);
      const result = await api.compareSolvers(
        api.buildCompareRequest(targetNodeId, searchMethod, constraints, traversal)
      );
      setCompareResult(result);
      setValidation(result.validation);
      onOpenCompare();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setComparing(false);
    }
  }, [targetNodeId, searchMethod, constraints, traversal,
      setComparing, setError, setCompareResult, setValidation, onOpenCompare]);

  // ---- Sample data -------------------------------------------------------
  const handleLoadSample = useCallback(async () => {
    try {
      setOptimizing(true);
      setError(null);

      const sampleNodes = [
        { id: 'var', name: 'Variables', description: 'Binding, types, scope', target_relevance: 0.30, downstream_utility: 0.95 },
        { id: 'fn', name: 'Functions', description: 'Definition and calls', target_relevance: 0.50, downstream_utility: 0.90 },
        { id: 'loop', name: 'Loops', description: 'Iteration constructs', target_relevance: 0.60, downstream_utility: 0.85 },
        { id: 'rec', name: 'Recursion', description: 'Recursive patterns', target_relevance: 0.70, downstream_utility: 0.75 },
        { id: 'ds', name: 'Data Structures', description: 'Arrays, lists, trees', target_relevance: 0.65, downstream_utility: 0.92 },
        { id: 'algo', name: 'Algorithms', description: 'Core algorithm design', target_relevance: 0.85, downstream_utility: 0.70 },
        { id: 'graph', name: 'Graph Structures', description: 'Adjacency, traversal', target_relevance: 0.80, downstream_utility: 0.80 },
        { id: 'dyn', name: 'Dynamic Programming', description: 'Memoisation, optimal substructure', target_relevance: 0.95, downstream_utility: 0.40 },
        { id: 'num', name: 'Number Theory', description: 'Optional detour', target_relevance: 0.15, downstream_utility: 0.10 },
        { id: 'opt', name: 'Graph Optimization', description: 'Optimised search & planning', target_relevance: 1.0, downstream_utility: 0.20 },
      ];

      const sampleEdges = [
        { id: 'r1', source: 'var', target: 'fn', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 30, cognitive_effort: 2 },
        { id: 'r2', source: 'fn', target: 'loop', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 40, cognitive_effort: 3 },
        { id: 'r3', source: 'loop', target: 'rec', type: 'PREREQUISITE_OF', prerequisite_type: 'SOFT', time_required_minutes: 50, cognitive_effort: 4 },
        { id: 'r4', source: 'fn', target: 'ds', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 35, cognitive_effort: 2 },
        { id: 'r5', source: 'ds', target: 'algo', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 55, cognitive_effort: 4 },
        { id: 'r6', source: 'rec', target: 'algo', type: 'PREREQUISITE_OF', prerequisite_type: 'SOFT', time_required_minutes: 60, cognitive_effort: 5 },
        { id: 'r7', source: 'algo', target: 'dyn', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 70, cognitive_effort: 5 },
        { id: 'r8', source: 'ds', target: 'graph', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 45, cognitive_effort: 3 },
        { id: 'r9', source: 'graph', target: 'opt', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 65, cognitive_effort: 4 },
        { id: 'r10', source: 'dyn', target: 'opt', type: 'PREREQUISITE_OF', prerequisite_type: 'SOFT', time_required_minutes: 80, cognitive_effort: 5 },
        { id: 'r11', source: 'num', target: 'opt', type: 'PREREQUISITE_OF', prerequisite_type: 'OPTIONAL', time_required_minutes: 120, cognitive_effort: 5 },
        { id: 'r12', source: 'loop', target: 'ds', type: 'PREREQUISITE_OF', prerequisite_type: 'HARD', time_required_minutes: 25, cognitive_effort: 2 },
      ];

      await api.resetDatabase();
      for (const node of sampleNodes) await api.createNode(node as any);
      for (const edge of sampleEdges) await api.createRelationship(edge as any);

      setOptimizeResult(null);
      setCompareResult(null);
      clearResults();
      await loadGraph();
      setTargetNodeId('opt');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setOptimizing(false);
    }
  }, [setOptimizing, setError, setOptimizeResult, setCompareResult, clearResults, loadGraph, setTargetNodeId]);

  const handleReset = useCallback(async () => {
    if (!confirm('Reset database? This deletes ALL nodes and relationships.')) return;
    try {
      setOptimizing(true);
      await api.resetDatabase();
      clearResults();
      await loadGraph();
      setTargetNodeId('');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setOptimizing(false);
    }
  }, [clearResults, loadGraph, setTargetNodeId, setError, setOptimizing]);

  const busy = isOptimizing || isComparing;
  const canRun = Boolean(targetNodeId) && nodes.length > 0 && !busy;

  const commitBudget = () => {
    const parsed = budgetInput.trim() === '' ? undefined : parseInt(budgetInput, 10);
    setConstraint('max_time_budget_minutes', Number.isNaN(parsed as number) ? undefined : parsed);
  };

  const commitDepth = () => {
    const parsed = depthInput.trim() === '' ? undefined : parseInt(depthInput, 10);
    setTraversalConfig('max_depth', Number.isNaN(parsed as number) ? undefined : parsed);
  };

  return (
    <div className="h-16 bg-white border-b border-gray-200 flex items-center gap-3 px-4 overflow-x-auto relative">
      {/* Brand */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <Database className="w-6 h-6 text-primary-600" />
        <span className="font-bold text-gray-900 text-lg hidden lg:inline">
          Learning Path Engine
        </span>
      </div>

      <div className="h-6 w-px bg-gray-200 flex-shrink-0" />

      {/* Target */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <label className="text-sm font-medium text-gray-700 whitespace-nowrap">Target</label>
        <select
          value={targetNodeId}
          onChange={(e) => setTargetNodeId(e.target.value)}
          className="px-2.5 py-1.5 text-sm border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500 min-w-[150px] bg-white"
        >
          <option value="">Select target…</option>
          {nodes.map((n) => (
            <option key={n.id} value={n.id}>{n.name}</option>
          ))}
        </select>
      </div>

      {/* Method dropdown: AUTO / BFS / DFS */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <label className="text-sm font-medium text-gray-700 whitespace-nowrap">Method</label>
        <select
          value={searchMethod}
          onChange={(e) => setSearchMethod(e.target.value as TraversalStrategy)}
          className={cn(
            'px-2.5 py-1.5 text-sm border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
            searchMethod === 'AUTO'
              ? 'bg-primary-50 border-primary-300 text-primary-800 font-medium'
              : 'bg-white'
          )}
          title={
            searchMethod === 'AUTO'
              ? 'AUTO inspects graph shape and picks BFS or DFS'
              : `Force ${searchMethod} traversal`
          }
        >
          {(Object.keys(TRAVERSAL_LABELS) as TraversalStrategy[]).map((key) => (
            <option key={key} value={key}>{TRAVERSAL_LABELS[key]}</option>
          ))}
        </select>
        {searchMethod === 'AUTO' && (
          <Sparkles className="w-4 h-4 text-primary-500 flex-shrink-0" />
        )}
      </div>

      {/* Optimizer dropdown */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <label className="text-sm font-medium text-gray-700 whitespace-nowrap">Optimizer</label>
        <select
          value={solver}
          onChange={(e) => setSolver(e.target.value as SolverAlgorithm)}
          className="px-2.5 py-1.5 text-sm border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-white min-w-[190px]"
        >
          <option value="DP">Dynamic Programming (DP)</option>
          <option value="GREEDY">Greedy Frontier</option>
          <option value="ILP">ILP</option>
        </select>
      </div>

      {/* Primary actions */}
      <button
        onClick={handleOptimize}
        disabled={!canRun}
        className={cn(
          'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors flex-shrink-0',
          canRun
            ? 'bg-primary-600 text-white hover:bg-primary-700 shadow-sm'
            : 'bg-gray-100 text-gray-400 cursor-not-allowed'
        )}
      >
        {isOptimizing ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Play className="w-4 h-4" />
        )}
        {isOptimizing ? 'Optimizing…' : 'Optimize'}
      </button>

      {/* Compare All Solvers */}
      <button
        onClick={handleCompare}
        disabled={!canRun}
        className={cn(
          'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-colors flex-shrink-0',
          canRun
            ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white hover:from-emerald-700 hover:to-teal-700 shadow-sm'
            : 'bg-gray-100 text-gray-400 cursor-not-allowed'
        )}
        title="Run Greedy, DP and ILP over one shared subgraph and compare"
      >
        {isComparing ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <GitCompare className="w-4 h-4" />
        )}
        {isComparing ? 'Comparing…' : 'Compare All Solvers'}
      </button>

      {/* Settings + status */}
      <div className="flex items-center gap-2 ml-auto flex-shrink-0 relative">
        {/* Settings */}
        <button
          onClick={() => { setShowSettings((v) => !v); setShowCatalogue(false); }}
          className={cn(
            'flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
            showSettings
              ? 'bg-primary-100 text-primary-700'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          )}
        >
          <Settings className="w-4 h-4" />
          <span className="hidden xl:inline">Settings</span>
          <ChevronDown className={cn('w-4 h-4 transition-transform', showSettings && 'rotate-180')} />
        </button>

        {showSettings && (
          <div className="absolute top-full right-0 mt-2 w-80 bg-white rounded-xl border border-gray-200 shadow-xl p-4 space-y-4 z-50">
            <h3 className="font-semibold text-sm text-gray-900">Constraints & Traversal</h3>

            {/* Time budget */}
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Time budget (minutes)
              </label>
              <div className="flex gap-2">
                <input
                  type="number"
                  min={1}
                  value={budgetInput}
                  onChange={(e) => setBudgetInput(e.target.value)}
                  onBlur={commitBudget}
                  placeholder={constraints.max_time_budget_minutes?.toString() ?? 'unconstrained'}
                  className="flex-1 px-2.5 py-1.5 text-sm border rounded-md focus:ring-2 focus:ring-primary-500"
                />
                {constraints.max_time_budget_minutes !== undefined && (
                  <button
                    onClick={() => { setBudgetInput(''); setConstraint('max_time_budget_minutes', undefined); }}
                    className="px-2 py-1.5 rounded-md bg-gray-100 text-gray-600 hover:bg-gray-200"
                    title="Clear budget"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>

            {/* Traversal depth */}
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Max traversal depth
              </label>
              <input
                type="number"
                min={1}
                value={depthInput}
                onChange={(e) => setDepthInput(e.target.value)}
                onBlur={commitDepth}
                placeholder={traversal.max_depth?.toString() ?? 'no limit'}
                className="w-full px-2.5 py-1.5 text-sm border rounded-md focus:ring-2 focus:ring-primary-500"
              />
            </div>

            {/* SOFT / OPTIONAL */}
            <div className="space-y-2 pt-1 border-t">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={constraints.include_soft}
                  onChange={(e) => setConstraint('include_soft', e.target.checked)}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-gray-700">Include SOFT prerequisites</span>
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={constraints.include_optional}
                  onChange={(e) => setConstraint('include_optional', e.target.checked)}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-gray-700">Include OPTIONAL prerequisites</span>
              </label>
            </div>

            {/* Lookahead depth */}
            <div className="pt-1 border-t">
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Greedy lookahead depth:{' '}
                <span className="font-mono text-primary-700">{constraints.greedy_lookahead_depth}</span>
              </label>
              <input
                type="range"
                min={1}
                max={6}
                value={constraints.greedy_lookahead_depth}
                onChange={(e) => setConstraint('greedy_lookahead_depth', parseInt(e.target.value))}
                className="w-full"
              />
            </div>

            {/* Subgraph cap */}
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Max subgraph nodes:{' '}
                <span className="font-mono text-primary-700">{traversal.max_subgraph_nodes}</span>
              </label>
              <input
                type="range"
                min={10}
                max={200}
                step={5}
                value={traversal.max_subgraph_nodes}
                onChange={(e) => setTraversalConfig('max_subgraph_nodes', parseInt(e.target.value))}
                className="w-full"
              />
            </div>

            {/* Data actions */}
            <div className="pt-2 border-t space-y-2">
              <button
                onClick={handleLoadSample}
                disabled={busy}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100 text-sm font-medium disabled:opacity-50"
              >
                <RefreshCw className={cn('w-4 h-4', busy && 'animate-spin')} />
                Load Sample Data (10 nodes)
              </button>
              <button
                onClick={handleReset}
                disabled={busy}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-red-50 text-red-700 rounded-lg hover:bg-red-100 text-sm font-medium disabled:opacity-50"
              >
                <Trash2 className="w-4 h-4" />
                Reset Database
              </button>
            </div>
          </div>
        )}

        {/* Solver catalogue */}
        <button
          onClick={() => { setShowCatalogue((v) => !v); setShowSettings(false); }}
          className={cn(
            'flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
            showCatalogue ? 'bg-primary-100 text-primary-700' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          )}
          title="Solver catalogue"
        >
          <Sigma className="w-4 h-4" />
        </button>

        {showCatalogue && solverCatalogue.length > 0 && (
          <div className="absolute top-full right-0 mt-2 w-96 bg-white rounded-xl border border-gray-200 shadow-xl p-4 space-y-3 z-50">
            <h3 className="font-semibold text-sm text-gray-900">Solver Catalogue</h3>
            {solverCatalogue.map((entry) => (
              <div key={entry.id} className="p-3 rounded-lg border border-gray-200">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-sm text-gray-900">{entry.name}</span>
                  <span
                    className={cn(
                      'px-2 py-0.5 rounded-full text-[10px] font-medium',
                      entry.optimality.includes('exact')
                        ? 'bg-green-100 text-green-700'
                        : 'bg-yellow-100 text-yellow-700'
                    )}
                  >
                    {entry.optimality}
                  </span>
                </div>
                <p className="text-xs text-gray-600 mt-1">{entry.strategy}</p>
                <p className="text-[10px] font-mono text-gray-400 mt-1">backend: {entry.backend}</p>
              </div>
            ))}
            <div className="pt-2 border-t text-[11px] text-gray-500 space-y-1">
              <p><span className="font-medium">Selection objective:</span> NetUtility = ΣLearningValue − ΣEdgeCost − penalties</p>
              <p><span className="font-medium">Reported metric:</span> PathScore = AvgLearningValue / (TotalPathCost + 0.01)</p>
            </div>
          </div>
        )}

        {/* Status pills */}
        {optimizeResult && (
          <div className="flex items-center gap-1 px-2.5 py-1.5 bg-green-100 text-green-700 rounded-lg text-xs font-medium">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span className="hidden lg:inline">
              ROI {optimizeResult.result.path_score.toFixed(3)}
            </span>
          </div>
        )}
        {compareResult?.comparison.best_solver && (
          <div className="flex items-center gap-1 px-2.5 py-1.5 bg-emerald-100 text-emerald-700 rounded-lg text-xs font-medium">
            <GitCompare className="w-3.5 h-3.5" />
            <span className="hidden lg:inline">
              Best: {SOLVER_LABELS[compareResult.comparison.best_solver]}
            </span>
          </div>
        )}
        {error && (
          <div
            className="flex items-center gap-1 px-2.5 py-1.5 bg-red-100 text-red-700 rounded-lg text-xs max-w-[220px]"
            title={error}
          >
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            <span className="truncate">{error}</span>
            <button onClick={() => setError(null)} className="shrink-0 hover:text-red-900">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>

      {/* Click-away backdrop for dropdowns.
          Rendered BEFORE the panels in DOM order it would sit on top, so it is
          placed here with z-40 while the dropdown panels use z-50. */}
      {(showSettings || showCatalogue) && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => { setShowSettings(false); setShowCatalogue(false); }}
        />
      )}
    </div>
  );
}

export default Toolbar;
