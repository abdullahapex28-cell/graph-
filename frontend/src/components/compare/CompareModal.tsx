/** Side-by-side comparison modal for Greedy vs DP vs ILP. */

'use client';

import React, { useState } from 'react';
import { cn } from '@/lib/utils';
import { SOLVER_LABELS, SOLVER_ORDER } from '@/lib/api';
import type {
  PathCompareResponse, SolverAlgorithm, SolverMetrics,
} from '@/lib/pipelineTypes';
import {
  X, Trophy, Clock, Coins, TrendingUp, Gauge, CheckCircle2,
  AlertTriangle, ChevronDown, ChevronRight, Route, Loader2, Cpu, Sigma,
} from 'lucide-react';

interface CompareModalProps {
  open: boolean;
  result: PathCompareResponse | null;
  isLoading: boolean;
  activeSolver: SolverAlgorithm | null;
  onClose: () => void;
  onSelectSolver: (solver: SolverAlgorithm) => void;
  onPreviewTraversal: () => void;
}

export function CompareModal({
  open, result, isLoading, activeSolver,
  onClose, onSelectSolver, onPreviewTraversal,
}: CompareModalProps) {
  const [showRationale, setShowRationale] = useState(true);
  const [expandedRow, setExpandedRow] = useState<SolverAlgorithm | null>(null);

  if (!open) return null;

  const comparison = result?.comparison;
  const results = comparison?.results ?? [];
  const best = comparison?.best_solver ?? null;

  // Highest Path Score among FEASIBLE solvers drives the green highlight.
  const feasible = results.filter((r) => r.is_feasible);
  const bestScore = feasible.length
    ? Math.max(...feasible.map((r) => r.path_score))
    : -Infinity;
  const fastest = feasible.length
    ? Math.min(...feasible.map((r) => r.execution_time_ms))
    : Infinity;

  const ordered = [...results].sort(
    (a, b) => SOLVER_ORDER.indexOf(a.solver) - SOLVER_ORDER.indexOf(b.solver)
  );

  // Per-metric best values, restricted to FEASIBLE solvers.
  const bestOf = (
    pick: (r: SolverMetrics) => number,
    better: 'max' | 'min'
  ): number | undefined => {
    if (!feasible.length) return undefined;
    const values = feasible.map(pick);
    return better === 'max' ? Math.max(...values) : Math.min(...values);
  };

  const bestNetUtility = bestOf((r) => r.net_utility, 'max');
  const minCost = bestOf((r) => r.total_path_cost, 'min');
  const maxValue = bestOf((r) => r.average_learning_value, 'max');
  const minTime = bestOf((r) => r.total_time_minutes, 'min');

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Solver comparison"
    >
      <div
        className="w-full max-w-6xl max-h-[90vh] bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div>
            <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              <Sigma className="w-6 h-6 text-primary-600" />
              Solver Comparison
            </h2>
            {comparison && (
              <p className="text-sm text-gray-600 mt-0.5">
                Target: <span className="font-semibold">{comparison.target_node_name}</span>
                {' · '}
                Same subgraph: {comparison.subgraph_size.retrieved_nodes} nodes /{' '}
                {comparison.subgraph_size.retrieved_edges} edges
                {' · '}reduced from {comparison.subgraph_size.full_graph_nodes} nodes
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"
            aria-label="Close comparison"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {isLoading && (
            <div className="flex flex-col items-center justify-center py-20 gap-4">
              <Loader2 className="w-10 h-10 text-primary-600 animate-spin" />
              <p className="text-gray-700 font-medium">Running all three solvers…</p>
              <p className="text-sm text-gray-500">
                Traversing once, then solving the identical subgraph
              </p>
            </div>
          )}

          {/* AUTO traversal explanation */}
          {result?.traversal && !isLoading && (
            <div className="p-4 rounded-xl border border-primary-200 bg-primary-50/60">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                    <Route className="w-4 h-4 text-primary-600" />
                    Search Strategy — {result.traversal.selected}
                    {result.traversal.requested === 'AUTO' && (
                      <span className="px-2 py-0.5 rounded-full bg-primary-600 text-white text-[10px] font-medium">
                        AUTO
                      </span>
                    )}
                  </h3>
                  <p className="text-xs text-gray-700 mt-1.5 leading-relaxed">
                    {result.traversal.reason}
                  </p>
                  {Object.keys(result.traversal.metrics).length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-2.5">
                      {Object.entries(result.traversal.metrics).map(([key, value]) => (
                        <span
                          key={key}
                          className="px-2 py-0.5 rounded bg-white/80 border border-primary-100 text-[11px] font-mono text-gray-700"
                        >
                          {key.replace(/_/g, ' ')}: {value}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  onClick={onPreviewTraversal}
                  className="shrink-0 text-xs px-3 py-1.5 rounded-lg border border-primary-300 text-primary-700 hover:bg-primary-100 transition-colors"
                >
                  Details
                </button>
              </div>
            </div>
          )}

          {/* Recommendation */}
          {comparison && !isLoading && (
            <div
              className={cn(
                'p-4 rounded-xl border',
                best
                  ? 'border-green-200 bg-green-50'
                  : 'border-red-200 bg-red-50'
              )}
            >
              <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                {best ? (
                  <Trophy className="w-4 h-4 text-green-600" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-red-600" />
                )}
                Recommendation
              </h3>
              <p className="text-sm text-gray-800 mt-1.5 leading-relaxed">
                {comparison.recommendation}
              </p>

              {showRationale && comparison.recommendation_rationale.length > 0 && (
                <ul className="mt-3 space-y-1.5">
                  {comparison.recommendation_rationale.map((line, i) => (
                    <li key={i} className="text-xs text-gray-700 flex gap-2">
                      <span className="text-green-600 shrink-0">•</span>
                      <span className="leading-relaxed">{line}</span>
                    </li>
                  ))}
                </ul>
              )}

              <button
                onClick={() => setShowRationale((v) => !v)}
                className="mt-2.5 text-xs text-gray-600 hover:text-gray-800 flex items-center gap-1"
              >
                {showRationale ? (
                  <ChevronDown className="w-3 h-3" />
                ) : (
                  <ChevronRight className="w-3 h-3" />
                )}
                {showRationale ? 'Hide' : 'Show'} detailed reasoning
              </button>
            </div>
          )}

          {/* Comparison table */}
          {ordered.length > 0 && !isLoading && (
            <div className="overflow-x-auto rounded-xl border border-gray-200">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="text-left px-4 py-3 font-semibold text-gray-700">
                      Metric
                    </th>
                    {ordered.map((r) => (
                      <th
                        key={r.solver}
                        className={cn(
                          'text-left px-4 py-3 font-semibold',
                          r.solver === best ? 'text-green-700' : 'text-gray-700'
                        )}
                      >
                        <div className="flex items-center gap-1.5">
                          {r.solver === best && <Trophy className="w-3.5 h-3.5" />}
                          {SOLVER_LABELS[r.solver]}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>

                <tbody className="divide-y divide-gray-100">
                  <Row
                    label="Path Score (ROI)"
                    icon={<TrendingUp className="w-4 h-4" />}
                    results={ordered}
                    render={(r) => r.path_score.toFixed(4)}
                    metric={(r) => r.path_score}
                    best={bestScore === -Infinity ? undefined : bestScore}
                    better="max"
                    isFeasible={(r) => r.is_feasible}
                    emphasis
                  />
                  <Row
                    label="Net Utility"
                    icon={<Sigma className="w-4 h-4" />}
                    results={ordered}
                    render={(r) => r.net_utility.toFixed(4)}
                    metric={(r) => r.net_utility}
                    best={bestNetUtility}
                    better="max"
                    isFeasible={(r) => r.is_feasible}
                  />
                  <Row
                    label="Total Path Cost"
                    icon={<Coins className="w-4 h-4" />}
                    results={ordered}
                    render={(r) => r.total_path_cost.toFixed(4)}
                    metric={(r) => r.total_path_cost}
                    best={minCost}
                    better="min"
                    isFeasible={(r) => r.is_feasible}
                  />
                  <Row
                    label="Avg Learning Value"
                    icon={<Gauge className="w-4 h-4" />}
                    results={ordered}
                    render={(r) => r.average_learning_value.toFixed(4)}
                    metric={(r) => r.average_learning_value}
                    best={maxValue}
                    better="max"
                    isFeasible={(r) => r.is_feasible}
                  />
                  <Row
                    label="Total Time"
                    icon={<Clock className="w-4 h-4" />}
                    results={ordered}
                    render={(r) => `${r.total_time_minutes} min`}
                    metric={(r) => r.total_time_minutes}
                    best={minTime}
                    better="min"
                    isFeasible={(r) => r.is_feasible}
                  />
                  <Row
                    label="Execution Time"
                    icon={<Cpu className="w-4 h-4" />}
                    results={ordered}
                    render={(r) => `${r.execution_time_ms.toFixed(1)} ms`}
                    metric={(r) => r.execution_time_ms}
                    best={fastest === Infinity ? undefined : fastest}
                    better="min"
                    isFeasible={(r) => r.is_feasible}
                  />
                  <Row
                    label="Nodes Selected"
                    icon={<Route className="w-4 h-4" />}
                    results={ordered}
                    render={(r) => `${r.path_nodes.length}`}
                    isFeasible={(r) => r.is_feasible}
                  />
                  <Row
                    label="Feasibility"
                    icon={<CheckCircle2 className="w-4 h-4" />}
                    results={ordered}
                    render={(r) =>
                      r.is_feasible ? (
                        <span className="inline-flex items-center gap-1 text-green-700 font-medium">
                          <CheckCircle2 className="w-3.5 h-3.5" /> Valid
                        </span>
                      ) : (
                        <span
                          className="inline-flex items-center gap-1 text-red-700 font-medium"
                          title={r.feasibility_reason}
                        >
                          <AlertTriangle className="w-3.5 h-3.5" /> Invalid
                        </span>
                      )
                    }
                    isFeasible={(r) => r.is_feasible}
                  />
                </tbody>
              </table>
            </div>
          )}

          {/* Per-solver path detail */}
          {result?.learning_sequences && !isLoading && (
            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-gray-900">
                Learning sequences
              </h3>
              {SOLVER_ORDER.filter((s) => result.learning_sequences[s]).map((solver) => {
                const sequence = result.learning_sequences[solver];
                const expanded = expandedRow === solver;
                return (
                  <div
                    key={solver}
                    className={cn(
                      'rounded-xl border overflow-hidden',
                      solver === activeSolver
                        ? 'border-green-300 bg-green-50/40'
                        : 'border-gray-200'
                    )}
                  >
                    <button
                      onClick={() => setExpandedRow(expanded ? null : solver)}
                      className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors"
                    >
                      <span className="flex items-center gap-2 font-medium text-gray-900">
                        {expanded ? (
                          <ChevronDown className="w-4 h-4 text-gray-500" />
                        ) : (
                          <ChevronRight className="w-4 h-4 text-gray-500" />
                        )}
                        {SOLVER_LABELS[solver]}
                        {solver === best && (
                          <Trophy className="w-3.5 h-3.5 text-green-600" />
                        )}
                        {solver === activeSolver && (
                          <span className="px-2 py-0.5 rounded-full bg-green-600 text-white text-[10px] font-medium">
                            ON CANVAS
                          </span>
                        )}
                      </span>
                      <span className="text-xs text-gray-500">
                        {sequence.length} steps
                      </span>
                    </button>

                    {expanded && (
                      <div className="px-4 pb-4 space-y-1.5">
                        {sequence.map((step) => (
                          <div
                            key={step.node_id}
                            className="flex items-center gap-3 p-2 rounded-lg bg-white border border-gray-100"
                          >
                            <span className="w-6 h-6 rounded-full bg-primary-600 text-white text-xs font-bold flex items-center justify-center shrink-0">
                              {step.step}
                            </span>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5">
                                <span className="font-medium text-gray-900 text-sm truncate">
                                  {step.name}
                                </span>
                                {step.is_hard_prerequisite && (
                                  <span className="px-1.5 py-0.5 rounded bg-red-100 text-red-700 text-[10px] font-medium shrink-0">
                                    HARD
                                  </span>
                                )}
                              </div>
                              {step.prerequisites.length > 0 && (
                                <div className="text-xs text-gray-500 mt-0.5 truncate">
                                  requires:{' '}
                                  {step.prerequisites.map((p) => p.source_name).join(', ')}
                                </div>
                              )}
                            </div>
                            <div className="text-right shrink-0">
                              <div className="text-xs font-mono text-gray-700">
                                v{step.learning_value.toFixed(2)}
                              </div>
                              <div className="text-[10px] text-gray-500">
                                ~{step.estimated_time_minutes}m
                              </div>
                            </div>
                          </div>
                        ))}

                        <button
                          onClick={() => onSelectSolver(solver)}
                          className="w-full mt-2 px-3 py-2 rounded-lg bg-primary-600 text-white text-sm font-medium hover:bg-primary-700 transition-colors"
                        >
                          {solver === activeSolver
                            ? 'Highlighted on canvas'
                            : `Show ${SOLVER_LABELS[solver]} path on canvas`}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-gray-200 bg-gray-50 flex items-center justify-between">
          <p className="text-xs text-gray-500">
            All solvers ran on the <span className="font-medium">same</span> retrieved
            subgraph, so differences reflect algorithm behaviour only.
          </p>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-gray-200 text-gray-800 text-sm font-medium hover:bg-gray-300 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// TABLE ROW
// ============================================================================

interface RowProps {
  label: string;
  icon: React.ReactNode;
  results: SolverMetrics[];
  render: (r: SolverMetrics) => React.ReactNode;
  /**
   * Numeric metric this row ranks on, used to decide which cell gets the
   * green "best" highlight. Omit (or use 'none') for rows with no ordering.
   */
  metric?: (r: SolverMetrics) => number;
  best?: number;
  /** Which direction counts as "better". */
  better?: 'max' | 'min';
  isFeasible: (r: SolverMetrics) => boolean;
  emphasis?: boolean;
}

function Row({
  label, icon, results, render, metric, best,
  better = 'max', isFeasible, emphasis,
}: RowProps) {
  const shouldHighlight = (r: SolverMetrics) => {
    if (!isFeasible(r)) return false;
    if (!metric || best === undefined) return false;
    return Math.abs(metric(r) - best) < 1e-9;
  };

  return (
    <tr className={emphasis ? 'bg-green-50/40' : ''}>
      <td className="px-4 py-2.5 text-gray-700 font-medium whitespace-nowrap">
        <span className="flex items-center gap-2">
          <span className="text-gray-400">{icon}</span>
          {label}
        </span>
      </td>
      {results.map((r) => {
        const win = shouldHighlight(r);
        return (
          <td
            key={r.solver}
            className={cn(
              'px-4 py-2.5 font-mono',
              win ? 'bg-green-100 text-green-800 font-semibold' : 'text-gray-800'
            )}
          >
            {render(r)}
          </td>
        );
      })}
    </tr>
  );
}

export default CompareModal;
