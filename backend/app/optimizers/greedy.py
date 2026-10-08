"""
Solver 1 — Greedy Frontier with N-step lookahead.

Strategy
--------
Walk the DAG in topological order maintaining a *frontier* of nodes that are
eligible for inclusion (their ancestors are already decided). At each step the
solver scores every frontier candidate with a local utility

    utility(n) = LearningValue(n) - EdgeCost(n, best dependent already chosen)

and, to avoid the classic myopic trap of grabbing a cheap-but-boring node, it
discounts that utility by the best value reachable within an N-step lookahead
window. The chosen node is committed, its parents become the new frontier, and
the loop continues.

Complexity is O(V * E) per horizon expansion, i.e. effectively linear, which is
what makes it the fast baseline in the comparison.

Guarantees
----------
HARD prerequisites are force-included whenever they enter the frontier, so the
emitted solution is always at least HARD-feasible.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

import networkx as nx

from app.cost_engine import OptimizationProblem, path_score
from app.optimizers.base import BaseSolver
from app.schemas import PrerequisiteType, SolverAlgorithm


class GreedyFrontierSolver(BaseSolver):
    algorithm = SolverAlgorithm.GREEDY_FRONTIER

    def solve(self, problem: OptimizationProblem) -> Set[str]:
        horizon = max(1, problem.constraints.greedy_lookahead_depth)

        # Mandatory seed: target + its transitive HARD closure.
        selected: Set[str] = {problem.target_id} | set(problem.hard_prerequisites)

        # Remaining candidates = TRANSITIVE ancestor closure of the target in the
        # prerequisite subgraph, minus what is already chosen. Direct
        # predecessors alone are not enough: a node two hops away is still
        # relevant if the route through the middle node is walked.
        candidate_pool: Set[str] = (
            set(nx.ancestors(problem.prerequisite_only, problem.target_id))
            | {problem.target_id}
        ) - selected

        # Process in topological order so parents are decided before dependents.
        topo_order = problem.topological_order()
        ordered = [n for n in topo_order if n in candidate_pool]

        trace: List[Dict[str, object]] = []

        for node_id in ordered:
            if node_id in selected:
                continue

            parents = [
                (source, edge)
                for source, edge in problem.prereq_parents(node_id)
            ]
            if not parents:
                # No prerequisite support -> unreachable/unnecessary.
                continue

            # Every parent that is already selected contributes a sunk edge cost.
            already_covered = [
                edge for source, edge in parents if source in selected
            ]
            edge_cost = sum(edge.edge_cost for edge in already_covered)

            # Parents still outstanding must themselves be pulled in.
            outstanding = [source for source, _ in parents if source not in selected]
            outstanding_cost = sum(
                problem.edge_between(source, node_id).edge_cost  # type: ignore[union-attr]
                for source in outstanding
                if problem.edge_between(source, node_id)
            )

            # Lookahead: best marginal value reachable within `horizon` steps.
            lookahead_value, lookahead_depth = self._lookahead(
                problem, outstanding, selected, horizon
            )

            node = problem.nodes[node_id]
            utility = node.learning_value - edge_cost - outstanding_cost
            # Discount by lookahead: if a much richer branch is nearby, the
            # cheap local node is less attractive than its raw utility suggests.
            score = utility - (lookahead_value / (lookahead_depth + 1.0)) * 0.35

            # Constraint gating.
            skip_penalty = node.skip_penalty
            include_optional = problem.constraints.include_optional
            all_optional = all(
                edge.prerequisite_type == PrerequisiteType.OPTIONAL for _s, edge in parents
            )
            if all_optional and not include_optional:
                score -= 10.0  # effectively veto

            budget = problem.constraints.max_time_budget_minutes
            time_cost = sum(edge.raw_time_minutes for edge in already_covered)

            # A node is only worth taking if it ENABLES something already in the
            # plan. Learning a concept that nothing downstream needs would add
            # value while paying no prerequisite-edge cost, which is not a real
            # learning path.
            supports_something = any(
                target_node in selected for target_node in problem.prerequisite_only.successors(node_id)
            )
            if not supports_something:
                trace.append(
                    {
                        "node_id": node_id,
                        "name": node.name,
                        "utility": 0.0,
                        "lookahead_value": 0.0,
                        "lookahead_depth": 0,
                        "score": 0.0,
                        "skip_penalty": skip_penalty,
                        "decision": "skipped",
                        "reason": "supports no selected topic (would be free value)",
                    }
                )
                continue

            decision = score > 0.0
            if decision and budget is not None:
                # Cheap greedy budget guard; the DP/ILP solvers do this properly.
                if self._projected_time(problem, selected, node_id) > budget:
                    decision = False

            if decision:
                selected.add(node_id)
                # Pulling a node in may pull its own parents in (chain repair).
                selected |= self._pull_required_parents(problem, node_id, selected)

            trace.append(
                {
                    "node_id": node_id,
                    "name": node.name,
                    "utility": round(utility, 6),
                    "lookahead_value": round(lookahead_value, 6),
                    "lookahead_depth": lookahead_depth,
                    "score": round(score, 6),
                    "skip_penalty": skip_penalty,
                    "decision": "included" if decision else "skipped",
                }
            )

        # Re-close: HARD chain repair after all decisions.
        selected |= self._hard_closure(problem, selected)

        self._trace = trace
        return selected

    # ------------------------------------------------------------------
    def _pull_required_parents(
        self, problem: OptimizationProblem, node_id: str, selected: Set[str]
    ) -> Set[str]:
        """HARD parents (transitively) required to justify including ``node_id``."""
        required: Set[str] = set()
        stack = [
            source
            for source, edge in problem.prereq_parents(node_id)
            if edge.prerequisite_type == PrerequisiteType.HARD
        ]
        while stack:
            current = stack.pop()
            if current in required or current in selected:
                continue
            required.add(current)
            for parent, edge in problem.prereq_parents(current):
                if edge.prerequisite_type == PrerequisiteType.HARD:
                    stack.append(parent)
        return required

    def _hard_closure(
        self, problem: OptimizationProblem, selected: Set[str]
    ) -> Set[str]:
        """Force-include any HARD prerequisite of anything selected."""
        closure: Set[str] = set()
        for node_id in list(selected):
            if node_id not in problem.nodes:
                continue
            for source, edge in problem.prereq_parents(node_id):
                if edge.prerequisite_type == PrerequisiteType.HARD:
                    if source in problem.hard_prerequisites and source not in selected:
                        closure.add(source)
        return closure

    def _projected_time(
        self, problem: OptimizationProblem, selected: Set[str], candidate: str
    ) -> int:
        total = 0
        probe = selected | {candidate}
        for source, target in problem.prerequisite_only.edges():
            if source in probe and target in probe:
                edge = problem.edge_between(source, target)
                if edge:
                    total += edge.raw_time_minutes
        return total

    def _lookahead(
        self,
        problem: OptimizationProblem,
        frontier: List[str],
        selected: Set[str],
        horizon: int,
    ) -> Tuple[float, int]:
        """
        Best cumulative learning value reachable within ``horizon`` levels below
        the frontier, ignoring cost. Returns (value, depth_reached).
        """
        best_value = 0.0
        best_depth = 0

        level: Set[str] = set(frontier)
        for depth in range(1, horizon + 1):
            if not level:
                break
            best_value = max(
                best_value, max(problem.nodes[n].learning_value for n in level)
            )
            best_depth = depth
            next_level: Set[str] = set()
            for node_id in level:
                for source, _edge in problem.prereq_parents(node_id):
                    if source not in selected:
                        next_level.add(source)
            level = next_level

        return best_value, best_depth

    # ------------------------------------------------------------------
    def describe(
        self, problem: OptimizationProblem, selected: Set[str]
    ) -> Dict[str, object]:
        trace = getattr(self, "_trace", [])
        included = sum(1 for t in trace if t["decision"] == "included")
        return {
            "lookahead_horizon": problem.constraints.greedy_lookahead_depth,
            "candidates_evaluated": len(trace),
            "candidates_included": included,
            "final_path_score": round(path_score(problem, selected), 6),
            "decision_trace": trace[:60],
        }
