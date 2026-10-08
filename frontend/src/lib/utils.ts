/** Utility functions */

import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(num: number, decimals = 2): string {
  return num.toFixed(decimals);
}

export function formatPercentage(num: number): string {
  return `${(num * 100).toFixed(1)}%`;
}

export function getPrerequisiteColor(type: string | null): string {
  switch (type) {
    case 'HARD':
      return 'text-red-600 bg-red-50 border-red-200';
    case 'SOFT':
      return 'text-yellow-600 bg-yellow-50 border-yellow-200';
    case 'OPTIONAL':
      return 'text-green-600 bg-green-50 border-green-200';
    default:
      return 'text-gray-600 bg-gray-50 border-gray-200';
  }
}

export function getPrerequisiteLabel(type: string | null): string {
  switch (type) {
    case 'HARD':
      return '🔴 HARD (Mandatory)';
    case 'SOFT':
      return '🟡 SOFT (Recommended)';
    case 'OPTIONAL':
      return '🟢 OPTIONAL';
    default:
      return '⚪ PART_OF';
  }
}

export function getRelationshipColor(type: string): string {
  switch (type) {
    case 'PREREQUISITE_OF':
      return 'text-blue-600 bg-blue-50 border-blue-200';
    case 'PART_OF':
      return 'text-purple-600 bg-purple-50 border-purple-200';
    default:
      return 'text-gray-600 bg-gray-50 border-gray-200';
  }
}

export function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

export function validateNodeId(id: string, existingIds: string[]): string | null {
  if (!id.trim()) return 'Node ID cannot be empty';
  if (existingIds.includes(id)) return 'Node ID already exists';
  if (!/^[a-zA-Z0-9_-]+$/.test(id)) return 'Node ID can only contain letters, numbers, underscores, and hyphens';
  return null;
}

export function validateRelationshipId(id: string, existingIds: string[]): string | null {
  if (!id.trim()) return 'Relationship ID cannot be empty';
  if (existingIds.includes(id)) return 'Relationship ID already exists';
  if (!/^[a-zA-Z0-9_-]+$/.test(id)) return 'Relationship ID can only contain letters, numbers, underscores, and hyphens';
  return null;
}

export const PREREQUISITE_TYPES = [
  { value: 'HARD', label: 'HARD (Mandatory)', description: 'Must be completed before target' },
  { value: 'SOFT', label: 'SOFT (Recommended)', description: 'Recommended but can be skipped if cost > value' },
  { value: 'OPTIONAL', label: 'OPTIONAL', description: 'Optional enhancement, included only if beneficial' },
] as const;

export const RELATIONSHIP_TYPES = [
  { value: 'PREREQUISITE_OF', label: 'PREREQUISITE_OF', description: 'Source is a prerequisite for target' },
  { value: 'PART_OF', label: 'PART_OF', description: 'Source is part of target (no prerequisite constraint)' },
] as const;

export const SEARCH_METHODS = [
  { value: 'DFS', label: 'DFS (Depth-First Search)', description: 'Explore deep prerequisite chains first' },
  { value: 'BFS', label: 'BFS (Breadth-First Search)', description: 'Explore all prerequisites at each level' },
] as const;