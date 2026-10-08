/** Right panel — graph traversal, validation, and algorithm explanation. */

'use client';

import React, { useState } from 'react';
import { usePipelineStore } from '@/store/pipelineStore';
import { SOLVER_LABELS, TRAVERSAL_LABELS } from '@/lib/api';
import { cn } from '@/lib/utils';
import {
  BookOpen, GitBranch, Layers, ListOrdered, ShieldCheck, Route,
  ChevronDown, ChevronUp, CheckCircle2, XCircle, AlertTriangle,
  Sparkles, Sigma, Target, Info, Cpu,
} from 'lucide-react';
import type { SolverAlgorithm } from '@/lib/pipelineTypes';

export function RightPanel() {
  const {
    optimizeResult, compareResult, activeSolver, setActiveSolver, validation,
  } = usePipelineStore();
  const [open, setOpen] = useState<Record<string, boolean>>({
    validation: true,
    traversal: true,
    sequence: true,
    explanation: false,
  });

  const toggle = (key: string) => setOpen((o) => ({ ...o, [key]: !o[key] }));

  const report = compareResult?.validation ?? optimizeResult?.validation ?? validation ?? null;
  const source = compareResult ?? optimizeResult;

  if (!source) {
    return (
      <aside className="w-80 shrink-0 h-full bg-white border-l border-gray-200 flex flex-col overflow-hidden">
        <Header />
        <div className="flex-1 flex items-center justify-center p-6 text-center text-gray-400">
          <div>
            <GitBranch className="w-12 h-12 mx-auto mb-3 opacity-40" />
            <p className="text-sm">Choose a target and run Optimize or Compare</p>
            <p className="text-xs mt-1 text-gray-400">
              Traversal details and the algorithm breakdown appear here.
            </p>
          </div>
        </div>
      </aside>
    );
  }

  const sequence =
    compareResult && activeSolver
      ? compareResult.learning_sequences[activeSolver] ?? []
      : optimizeResult?.learning_sequence ?? [];

  const activeMetrics =
    compareResult && activeSolver
      ? compareResult.comparison.results.find((r) => r.solver === activeSolver) ?? null
      : optimizeResult?.result ?? null;

  return (
    <aside className="w-80 shrink-0 h-full bg-white border-l border-gray-200 flex flex-col overflow-hidden">
      <Header />

      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {/* ============ VALIDATION ============ */}
        {report && (
          <Collapsible
            id="validation"
            title="Graph validation"
            open={open.validation}
            onToggle={toggle}
            icon={<ShieldCheck className="w-3.5 h-3.5" />}
          >
            <div
              className={cn(
                'flex items-center gap-2 p-2 rounded text-xs font-medium',
                report.is_valid
                  ? 'bg-green-50 text-green-800 border border-green-200'
                  : 'bg-red-50 text-red-800 border border-red-200'
              )}
            >
              {report.is_valid ? (
                <CheckCircle2 className="w-4 h-4 shrink-0" />
              ) : (
                <XCircle className="w-4 h-4 shrink-0" />
              )}
              {report.is_valid ? 'Passed' : 'Failed'} ·{' '}
              {report.total_nodes} nodes / {report.total_edges} edges
            </div>

            {report.errors.length > 0 && (
              <IssueList
                tone="error"
                title="Blocking errors"
                issues={report.errors.flatMap((e) => [
                  `${e.message}${e.entities.length ? ` — ${e.entities.slice(0, 4).join('; ')}` : ''}`,
                ])}
              />
            )}
            {report.cycle_details.length > 0 && (
              <IssueList
                tone="error"
                title={`Prerequisite cycles (${report.cycle_details.length})`}
                issues={report.cycle_details.map((c) => c.join(' → '))}
              />
            )}
            {report.warnings.length > 0 && (
              <IssueList
                tone="warn"
                title={`Warnings (${report.warnings.length})`}
                issues={report.warnings.map((w) => w.message)}
              />
            )}
            {report.is_valid && report.warnings.length === 0 && (
              <p className="text-[11px] text-green-700 mt-2">
                No duplicate ids, self-loops or prerequisite cycles.
              </p>
            )}
          </Collapsible>
        )}

        {/* ============ TRAVERSAL ============ */}
        <Collapsible
          id="traversal"
          title={`Reverse traversal — ${source.traversal.selected}`}
          open={open.traversal}
          onToggle={toggle}
          icon={<Route className="w-3.5 h-3.5" />}
        >
          <div className="flex items-center gap-2 mb-2">
            <span
              className={cn(
                'px-2 py-0.5 rounded-full text-[10px] font-semibold',
                source.traversal.requested === 'AUTO'
                  ? 'bg-primary-600 text-white'
                  : 'bg-gray-200 text-gray-700'
              )}
            >
              {TRAVERSAL_LABELS[source.traversal.requested]}
            </span>
            <span className="text-gray-400 text-xs">→</span>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-green-100 text-green-700">
              {source.traversal.selected}
            </span>
            {source.traversal.requested === 'AUTO' && (
              <Sparkles className="w-3.5 h-3.5 text-primary-500" />
            )}
          </div>

          <p className="text-[11px] text-gray-700 leading-relaxed">
            {source.traversal.reason}
          </p>

          {Object.keys(source.traversal.metrics).length > 0 && (
            <div className="grid grid-cols-2 gap-1 mt-2">
              {Object.entries(source.traversal.metrics).map(([k, v]) => (
                <div
                  key={k}
                  className="px-1.5 py-1 rounded bg-gray-50 border border-gray-100"
                >
                  <div className="text-[9px] text-gray-500 capitalize">
                    {k.replace(/_/g, ' ')}
                  </div>
                  <div className="font-mono text-[11px] font-semibold text-gray-800">
                    {v}
                  </div>
                </div>
              ))}
            </div>
          )}

          {'traversal_stats' in source && source.traversal_stats && (
            <div className="mt-2 pt-2 border-t border-gray-200 space-y-0.5 text-[11px]">
              <Stat
                label="Full graph"
                value={`${source.traversal_stats.full_graph_nodes} nodes / ${source.traversal_stats.full_graph_edges} edges`}
              />
              <Stat
                label="Retrieved subgraph"
                value={`${source.traversal_stats.retrieved_nodes} nodes / ${source.traversal_stats.retrieved_edges} edges`}
              />
              <Stat
                label="Search-space reduction"
                value={`${Math.round((source.traversal_stats.reduction_ratio ?? 0) * 100)}%`}
                highlight
              />
            </div>
          )}
        </Collapsible>

        {/* ============ SOLVER TABS (comparison only) ============ */}
        {compareResult && (
          <Collapsible
            id="solvers"
            title="Solver metrics"
            open={open.solvers}
            onToggle={toggle}
            icon={<Sigma className="w-3.5 h-3.5" />}
          >
            <div className="space-y-1.5">
              {compareResult.comparison.results.map((r) => (
                <button
                  key={r.solver}
                  onClick={() => setActiveSolver(r.solver)}
                  className={cn(
                    'w-full text-left p-2 rounded border transition-colors',
                    activeSolver === r.solver
                      ? 'border-green-400 bg-green-50'
                      : 'border-gray-200 hover:bg-gray-50'
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-gray-900">
                      {SOLVER_LABELS[r.solver]}
                    </span>
                    {r.solver === compareResult.comparison.best_solver && (
                      <span className="px-1.5 py-0.5 rounded bg-green-600 text-white text-[9px] font-medium">
                        BEST
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-x-2 mt-1 font-mono text-[10px] text-gray-600">
                    <span>ROI {r.path_score.toFixed(4)}</span>
                    <span>util {r.net_utility.toFixed(3)}</span>
                    <span>{r.total_time_minutes} min</span>
                    <span>{r.execution_time_ms.toFixed(1)} ms</span>
                    <span className="col-span-2">
                      {r.path_nodes.length} nodes ·{' '}
                      <span className={r.is_feasible ? 'text-green-600' : 'text-red-600'}>
                        {r.is_feasible ? 'valid' : 'invalid'}
                      </span>
                    </span>
                  </div>
                </button>
              ))}
            </div>

            {activeMetrics && !activeMetrics.is_feasible && (
              <p className="text-[11px] text-red-700 mt-2 p-2 bg-red-50 rounded border border-red-200">
                {activeMetrics.feasibility_reason}
              </p>
            )}

            {activeMetrics?.solver_specific?.backend && (
              <p className="text-[10px] text-gray-500 mt-2 font-mono">
                ILP backend: {String(activeMetrics.solver_specific.backend)}
              </p>
            )}
          </Collapsible>
        )}

        {/* ============ LEARNING SEQUENCE ============ */}
        <Collapsible
          id="sequence"
          title={`Learning sequence (${sequence.length})`}
          open={open.sequence}
          onToggle={toggle}
          icon={<ListOrdered className="w-3.5 h-3.5" />}
        >
          <ol className="space-y-1">
            {sequence.map((step) => (
              <li
                key={step.node_id}
                className="flex items-start gap-2 p-2 rounded bg-gray-50 border border-gray-100"
              >
                <span className="w-5 h-5 shrink-0 rounded-full bg-primary-600 text-white text-[10px] font-bold flex items-center justify-center">
                  {step.step}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium text-gray-900 truncate">
                      {step.name}
                    </span>
                    {step.is_hard_prerequisite && (
                      <span className="px-1 py-0.5 rounded bg-red-100 text-red-700 text-[9px] font-medium shrink-0">
                        HARD
                      </span>
                    )}
                  </div>
                  {step.description && (
                    <p className="text-[10px] text-gray-500 mt-0.5 line-clamp-2">
                      {step.description}
                    </p>
                  )}
                  {step.prerequisites.length > 0 && (
                    <p className="text-[10px] text-gray-500 mt-0.5 truncate">
                      ← {step.prerequisites.map((p) => p.source_name).join(', ')}
                    </p>
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
          {sequence.length === 0 && (
            <p className="text-[11px] text-gray-400">No sequence available.</p>
          )}
          <p className="text-[10px] text-gray-500 mt-2 pt-2 border-t border-gray-200">
            Ordered by NetworkX Kahn topological sort, so every prerequisite
            precedes its dependents.
          </p>
        </Collapsible>

        {/* ============ FULL EXPLANATION ============ */}
        {optimizeResult && (
          <Collapsible
            id="explanation"
            title="Full explanation"
            open={open.explanation}
            onToggle={toggle}
            icon={<BookOpen className="w-3.5 h-3.5" />}
          >
            <pre className="text-[10px] text-gray-700 whitespace-pre-wrap font-mono leading-relaxed">
              {optimizeResult.explanation}
            </pre>
          </Collapsible>
        )}

        {/* ============ RECOMMENDATION ============ */}
        {compareResult?.comparison.recommendation && (
          <Collapsible
            id="rec"
            title="Recommendation"
            open={open.rec ?? true}
            onToggle={toggle}
            icon={<Target className="w-3.5 h-3.5" />}
          >
            <p className="text-[11px] text-gray-700 leading-relaxed">
              {compareResult.comparison.recommendation}
            </p>
          </Collapsible>
        )}
      </div>
    </aside>
  );
}

// ============================================================================

function Header() {
  return (
    <div className="p-3 border-b border-gray-200 shrink-0 flex items-center gap-2">
      <BookOpen className="w-4 h-4 text-primary-600" />
      <h2 className="font-semibold text-sm text-gray-900">Algorithm Explanation</h2>
    </div>
  );
}

function Collapsible({
  id, title, open, onToggle, icon, children,
}: {
  id: string;
  title: string;
  open: boolean;
  onToggle: (id: string) => void;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => onToggle(id)}
        className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 hover:bg-gray-100 text-xs font-semibold text-gray-800"
      >
        <span className="flex items-center gap-1.5">
          {icon}
          {title}
        </span>
        {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
      </button>
      {open && <div className="p-2.5">{children}</div>}
    </div>
  );
}

function Stat({
  label, value, highlight,
}: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-gray-500">{label}</span>
      <span
        className={cn(
          'font-mono font-medium',
          highlight ? 'text-green-700' : 'text-gray-800'
        )}
      >
        {value}
      </span>
    </div>
  );
}

function IssueList({
  tone, title, issues,
}: { tone: 'error' | 'warn'; title: string; issues: string[] }) {
  return (
    <div className="mt-2">
      <div
        className={cn(
          'text-[10px] font-semibold mb-1',
          tone === 'error' ? 'text-red-700' : 'text-yellow-700'
        )}
      >
        {title}
      </div>
      <ul className="space-y-0.5">
        {issues.map((issue, i) => (
          <li
            key={i}
            className={cn(
              'text-[10px] leading-relaxed flex gap-1.5 p-1.5 rounded',
              tone === 'error'
                ? 'bg-red-50 text-red-700'
                : 'bg-yellow-50 text-yellow-700'
            )}
          >
            {tone === 'error' ? (
              <XCircle className="w-3 h-3 mt-0.5 shrink-0" />
            ) : (
              <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
            )}
            <span>{issue}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default RightPanel;
