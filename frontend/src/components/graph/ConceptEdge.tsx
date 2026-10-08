/** Custom React Flow edge for relationships */

'use client';

import { BaseEdge, EdgeLabelRenderer, EdgeProps, getBezierPath } from 'reactflow';
import { ArrowRight, GitBranch } from 'lucide-react';
import { cn, getPrerequisiteColor, getRelationshipColor } from '@/lib/utils';
import type { RelationshipResponse } from '@/types';

export default function ConceptEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const fullData: RelationshipResponse | undefined = data?.fullData;
  const isPrerequisite = fullData?.type === 'PREREQUISITE_OF';
  const prereqType = fullData?.prerequisite_type;

  const strokeColor = selected
    ? '#0ea5e9'
    : isPrerequisite
      ? '#38bdf8'
      : '#a855f7';

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: strokeColor,
          strokeWidth: selected ? 3 : 2,
          strokeDasharray: isPrerequisite ? undefined : '5,5',
        }}
      />
      <EdgeLabelRenderer>
        <div
          className={cn(
            'absolute whitespace-nowrap pointer-events-none',
            'bg-white/90 backdrop-blur-sm px-1.5 py-0.5 rounded border text-xs font-medium',
            selected ? 'border-primary-300 shadow-md' : 'border-gray-200'
          )}
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
          }}
        >
          <span
            className={cn(
              'flex items-center gap-1',
              isPrerequisite
                ? getPrerequisiteColor(prereqType ?? null)
                : getRelationshipColor(fullData?.type || '')
            )}
          >
            {isPrerequisite ? (
              <>
                <ArrowRight className="w-3 h-3" />
                <span>{prereqType || 'PREREQ'}</span>
              </>
            ) : (
              <>
                <GitBranch className="w-3 h-3" />
                <span>PART_OF</span>
              </>
            )}
          </span>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}