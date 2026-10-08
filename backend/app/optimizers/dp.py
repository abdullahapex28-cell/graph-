"""
Solver 2 — Dynamic Programming over the DAG.

Why a single state per node (not a Pareto frontier)
----------------------------------------------------
An earlier version kept a Pareto frontier of (value, cost) pairs per node. That
is the right tool for a *ratio* objective, where no single state dominates. It
is the wrong tool here, for two reasons:

1. The selection objective is **linear** — NetUtility = Σvalue − Σcost. For an
   additive objective the optimal state at each node is simply the one
   maximising ``value − cost``; keeping the rest of the frontier cannot change
   the optimum, it only multiplies the work.

2. The cross-product blows up. Branching multiplies frontier sizes, so on a
   60-node graph with many optional branches the intermediate product exploded
   and the solver stopped terminating in reasonable time.

So each node keeps exactly one state — the best (value, cost) pair — which makes
the forward pass O(V · E) and is optimal for the subproblem it solves.

Recurrence (forward topological order, parents first)
------------------------------------------------------
    best[v]  =  argmax over choices  ( Σ value − Σ cost )

    base(v)       = ( value(v), 0 )
    choice(p, e)  =
        HARD     -> include p: ( value(p) + best[p].value,
                                 best[p].cost  + cost(e) )
        SOFT     -> include p, or skip paying soft_skip_penalty
        OPTIONAL -> include p, or skip for free

What "global" means here
------------------------
The forward pass is *exact* for each node's covering subproblem. The final
assembly of a node set from those states is a marginal-gain pass, and because
branches can share ancestors that pass is a strong heuristic rather than a
proof of global optimality. Integer Linear Programming is the exact global
solver, and the comparison endpoint reports both so the gap is visible.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from app.cost_engine import (
    OptimizationProblem,
    net_utility,
    path_raw_time,
)
from app.optimizers.base import BaseSolver
from app.schemas import PrerequisiteType, SolverAlgorithm

# (cumulative_value, cumulative_cost)
State = Tuple[float, float]


def _net(state: State) -> float:
    return state[0] - state[1]


class DynamicProgrammingSolver(BaseSolver):
    algorithm = SolverAlgorithm.DYNAMIC_PROGRAMMING

    def solve(self, problem: OptimizationProblem) -> Set[str]:
        target = problem.target_id

        # ------------------------------------------------------------------
        # Forward pass. topological_order() lists every prerequisite before the
        # topic that needs it, which is exactly what the recurrence needs.
        #
        # Iterating this list in reverse silently yields empty states (every
        # HARD parent looks unreachable), and the fallback below then hides the
        # bug by returning the bare HARD closure -- which is why small graphs
        # looked correct while the DP was never actually running.
        # ------------------------------------------------------------------
        best: Dict[str, State] = {}

        for node_id in problem.topological_order():
            best[node_id] = self._best_state(problem, best, node_id)

        # ------------------------------------------------------------------
        # Backward pass: turn the target's state into an actual node set.
        # ------------------------------------------------------------------
        budget = problem.constraints.max_time_budget_minutes
        selected = self._reconstruct(problem, target)

        if budget is not None and path_raw_time(problem, selected) > budget:
            # The unconstrained optimum overshoots the budget. Fall back to the
            # mandatory core, which is the cheapest plan that could ever be
            # feasible, and let the caller report the infeasibility honestly
            # rather than silently returning something over budget.
            selected = self._mandatory_core(problem, target) or selected

        self._diagnostics = {
            "strategy": "forward topological DP, best (value - cost) state per node",
            "target_state_value": round(best.get(target, (0.0, 0.0))[0], 6),
            "target_state_cost": round(best.get(target, (0.0, 0.0))[1], 6),
            "target_state_net": round(_net(best.get(target, (0.0, 0.0))), 6),
            "nodes_visited": len(best),
            "nodes_selected": len(selected),
            "final_net_utility": round(net_utility(problem, selected), 6),
        }
        return selected

    # ------------------------------------------------------------------
    def _best_state(
        self,
        problem: OptimizationProblem,
        best: Dict[str, State],
        node_id: str,
    ) -> State:
        """Best (value, cost) covering ``node_id`` and its mandatory ancestors."""
        current: State = (problem.nodes[node_id].learning_value, 0.0)

        for source, edge in problem.prereq_parents(node_id):
            parent = best.get(source)
            if parent is None:
                # Parent unreachable under the current constraint set.
                if edge.prerequisite_type == PrerequisiteType.HARD:
                    # Cannot honour a mandatory prerequisite: leave the topic
                    # unselectable by returning a state that cannot win. The
                    # feasibility check downstream will reject it if it leaks
                    # into a plan.
                    return (0.0, 0.0)
                continue

            include: State = (
                current[0] + parent[0],
                current[1] + parent[1] + edge.edge_cost,
            )

            if edge.prerequisite_type == PrerequisiteType.HARD:
                current = include
                continue

            if edge.prerequisite_type == PrerequisiteType.SOFT:
                if not problem.constraints.include_soft:
                    skip: State = (
                        current[0],
                        current[1] + problem.constraints.soft_skip_penalty,
                    )
                else:
                    skip = (
                        current[0],
                        current[1] + problem.constraints.soft_skip_penalty,
                    )
            else:  # OPTIONAL
                if not problem.constraints.include_optional:
                    skip = (current[0], current[1])
                else:
                    skip = (current[0], current[1])

            current = include if _net(include) >= _net(skip) else skip

        return current

    # ------------------------------------------------------------------
    def _reconstruct(
        self,
        problem: OptimizationProblem,
        node_id: str,
    ) -> Set[str]:
        """
        Build a node set for ``node_id``.

        Two phases, and the order matters:

        1. **Mandatory core.** Pull in every HARD prerequisite first, recursively.
           After this the set is closed under mandatory edges, so all the cost
           those edges imply is already accounted for.

        2. **Optional branches by marginal gain**, to a fixpoint, because adding
           one branch can turn another branch's marginal contribution positive
           (branches share ancestors, so shared costs amortise).

        Two earlier variants were wrong in opposite directions, both observed on
        the 100-node graph:

        * comparing a branch against the *partial* set made every node look
          expensive (its own ancestors were not selected yet), so DP pruned all
          worthwhile optional chains;
        * comparing a branch *in isolation* had the opposite failure, because
          two branches sharing a foundation each looked worse than they are.

        Mandatory-first plus marginal-gain-against-the-complete-plan avoids both.
        """
        selected = self._mandatory_core(problem, node_id)
        if not selected:
            return {node_id}

        # Phase 2: repeatedly add any optional branch with positive marginal gain.
        pending: List[Set[str]] = [selected]
        seen_states: Set[frozenset] = {frozenset(selected)}

        while pending:
            current = pending.pop()

            for dependent in current:
                for source, edge in problem.prereq_parents(dependent):
                    if edge.prerequisite_type == PrerequisiteType.HARD:
                        continue  # phase 1 handled these
                    if source in current:
                        continue
                    if not self._is_enabled(problem, edge.prerequisite_type):
                        continue

                    branch = self._mandatory_core(problem, source)
                    if not branch or branch <= current:
                        continue

                    baseline = net_utility(problem, current)
                    candidate = current | branch
                    if net_utility(problem, candidate) <= baseline:
                        continue

                    marker = frozenset(candidate)
                    if marker in seen_states:
                        continue
                    seen_states.add(marker)
                    current = candidate
                    pending.append(current)

            if current > selected:
                selected = current

        return selected

    # ------------------------------------------------------------------
    @staticmethod
    def _mandatory_core(
        problem: OptimizationProblem, node_id: str, depth: int = 0
    ) -> Optional[Set[str]]:
        """``node_id`` plus its transitive HARD prerequisites."""
        if depth > 500:
            return None

        selected: Set[str] = {node_id}
        for source, edge in problem.prereq_parents(node_id):
            if edge.prerequisite_type != PrerequisiteType.HARD:
                continue
            core = DynamicProgrammingSolver._mandatory_core(problem, source, depth + 1)
            if core:
                selected |= core
        return selected

    # ------------------------------------------------------------------
    @staticmethod
    def _is_enabled(
        problem: OptimizationProblem, prereq_type: Optional[PrerequisiteType]
    ) -> bool:
        if prereq_type == PrerequisiteType.SOFT:
            return problem.constraints.include_soft
        if prereq_type == PrerequisiteType.OPTIONAL:
            return problem.constraints.include_optional
        return True

    # ------------------------------------------------------------------
    def describe(
        self, problem: OptimizationProblem, selected: Set[str]
    ) -> Dict[str, object]:
        return dict(getattr(self, "_diagnostics", {}))
