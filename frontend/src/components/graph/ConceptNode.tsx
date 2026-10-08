/** Custom React Flow node for concepts */

'use client';

import { Handle, Position, NodeProps } from 'reactflow';
import { BookOpen, Target, TrendingUp, Lock } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { NodeResponse } from '@/types';

interface ConceptNodeProps extends NodeProps {
  data: {
    label: string;
    fullData: NodeResponse;
    isOptimized?: boolean;
    isHardPrereq?: boolean;
  };
}

export function ConceptNode({ data, selected, isConnectable }: ConceptNodeProps) {
  const { fullData, isOptimized, isHardPrereq } = data;

  return (
    <div
      className={cn(
        'relative min-w-[180px] max-w-[240px] rounded-xl border-2 p-3 transition-all duration-200',
        'bg-white shadow-sm',
        selected && 'border-primary-500 shadow-lg ring-2 ring-primary-500/20',
        !selected && isHardPrereq && 'border-red-400 bg-red-50',
        !selected && isOptimized && !isHardPrereq && 'border-green-400 bg-green-50',
        !selected && !isHardPrereq && !isOptimized && 'border-gray-200 hover:border-gray-300 hover:shadow-md'
      )}
    >
      {/* Node header */}
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-primary-600 flex-shrink-0" />
          <h3 className="font-semibold text-gray-900 text-sm truncate">{data.label}</h3>
        </div>
        {isHardPrereq && (
          <Lock className="w-4 h-4 text-red-500 flex-shrink-0" />
        )}
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 gap-2 mb-2 p-2 bg-gray-50 rounded-lg">
        <div>
          <div className="flex items-center gap-1 text-xs text-gray-500">
            <Target className="w-3 h-3" />
            <span>Relevance</span>
          </div>
          <div className="font-mono text-sm font-medium text-gray-900">
            {(fullData.target_relevance * 100).toFixed(0)}%
          </div>
        </div>
        <div>
          <div className="flex items-center gap-1 text-xs text-gray-500">
            <TrendingUp className="w-3 h-3" />
            <span>Utility</span>
          </div>
          <div className="font-mono text-sm font-medium text-gray-900">
            {(fullData.downstream_utility * 100).toFixed(0)}%
          </div>
        </div>
      </div>

      {/* Description */}
      {fullData.description && (
        <p className="text-xs text-gray-600 line-clamp-2">{fullData.description}</p>
      )}

      {/* Optimization status */}
      {isOptimized && (
        <div className={cn(
          'mt-2 text-xs font-medium px-2 py-1 rounded text-center',
          isHardPrereq
            ? 'bg-red-100 text-red-700'
            : 'bg-green-100 text-green-700'
        )}>
          {isHardPrereq ? '🔒 Hard Prerequisite' : '✅ In Optimal Path'}
        </div>
      )}

      {/* Connection handles */}
      <div className="flex justify-between -mx-3 mt-2">
        <Handle
          type="target"
          position={Position.Left}
          className="w-3 h-3 bg-primary-500 border-2 border-white"
          id="input"
        />
        <Handle
          type="source"
          position={Position.Right}
          className="w-3 h-3 bg-primary-500 border-2 border-white"
          id="output"
        />
      </div>
    </div>
  );
}