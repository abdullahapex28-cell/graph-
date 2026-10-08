"""
Solver 3 — Integer Linear Programming.

Formulation
-----------
Decision variables (binary)
    x_v ∈ {0,1}   node v is included in the learning path
    y_e ∈ {0,1}   prerequisite edge e is traversed

Objective — maximise Net Utility (well-posed, additive, linear)
---------------------------------------------------------------
    maximise   Σ_v x_v·LearningValue(v)
             − Σ_e y_e·EdgeCost(e)
             − soft_skip_penalty · Σ_{soft e} (1 − y_e)

This rewards pulling in a prerequisite whose learning value exceeds its cost
and penalises one whose cost exceeds its value, so it cannot be gamed by
returning the empty set.

NOTE ON THE Path Score RATIO
----------------------------
The specified reporting metric

    Path Score = Average Learning Value / (Total Path Cost + 0.01)

is strictly *decreasing* in cost for a fixed learning value. Maximising it as
an optimisation objective is therefore degenerate — the optimum is always
"select nothing" (zero cost, zero average ⇒ maximal ratio). It is consequently
used as a **reporting / ranking metric** across solver outputs, never as the
selection objective. All three solvers optimise the same Net Utility, which is
what makes their Path Scores directly comparable.

Constraints
-----------
1. **Flow conservation** — a node may only be selected once every prerequisite
   edge feeding it is traversed:  Σ_{e ∈ in(v)} y_e == x_v.
   Nodes with no incoming prerequisite edges (other than the target) are
   pinned to 0 so they cannot leak into the solution for free.
2. **HARD prerequisite satisfaction** — the transitive HARD closure of the
   target is forced on (x_v == 1) and HARD edges require their source node
   (y_e == x_target(e)).
3. **SOFT skip penalty** — encoded directly in the objective above.
4. **Time budget** — Σ_e y_e·Time(e) ≤ budget, when configured.
5. **PART_OF edges** are structural: excluded from the cost model entirely.

Backends
--------
The model is declared **once** as backend-neutral linear data, then dispatched
to whichever MILP backend is installed:

    PuLP  (``pulp`` + an available CBC/HiGHS binary)   — preferred
    scipy.optimize.milp (HiGHS, in-process)            — always available

A single formulation therefore serves both backends, so the two can never drift.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from app.cost_engine import OptimizationProblem
from app.optimizers.base import BaseSolver
from app.schemas import PrerequisiteType, SolverAlgorithm

logger = logging.getLogger(__name__)


# ============================================================================
# BACKEND-NEUTRAL MODEL
# ============================================================================

@dataclass
class LinearModel:
    """A backend-neutral MILP description (maximisation)."""

    names: List[str]
    lower: List[float]
    upper: List[float]
    integrality: List[int]                      # 1 = integer
    objective: List[float]                      # coefficients to MAXIMISE
    row_names: List[str]
    row_coeffs: List[Dict[int, float]]
    row_sense: List[str]                        # "<=", ">=", "=="
    row_rhs: List[float]
    # Internal lookup keys, positionally aligned with ``names``.
    # ``names`` is sanitised for the solver backend; these are the keys that
    # _read_solution queries ("x::<node_id>" / "y::<edge_id>").
    keys: List[str] = field(default_factory=list)


@dataclass
class LinearSolution:
    status: str
    values: Dict[str, float]
    objective: float
    backend: str
    notes: List[str] = field(default_factory=list)


# ============================================================================
# SOLVER
# ============================================================================

class ILPSolver(BaseSolver):
    algorithm = SolverAlgorithm.INTEGER_LINEAR_PROGRAMMING

    def solve(self, problem: OptimizationProblem) -> Set[str]:
        if problem.prerequisite_only.number_of_edges() == 0:
            self._diagnostics = {
                "status": "TRIVIAL",
                "notes": ["Target has no prerequisite edges; path is the target alone."],
            }
            return {problem.target_id}

        model = self._build_model(problem)
        solution = _solve_model(model)
        selected, used_edges = self._read_solution(problem, solution)

        sum_value = sum(problem.nodes[v].learning_value for v in selected)
        sum_cost = 0.0
        for source, target in problem.prerequisite_only.edges():
            if source in selected and target in selected:
                edge = problem.edge_between(source, target)
                if edge:
                    sum_cost += edge.edge_cost

        self._diagnostics = {
            "status": solution.status,
            "backend": solution.backend,
            "objective": "NetUtility = Sum(LearningValue) - Sum(EdgeCost) - SkipPenalties",
            "objective_value": round(sum_value - sum_cost, 6),
            "sum_learning_value": round(sum_value, 6),
            "sum_edge_cost": round(sum_cost, 6),
            "edges_traversed": len(used_edges),
            "notes": solution.notes,
            "variables": {
                "binary_node_selection": len(problem.nodes),
                "binary_edge_traversal": problem.prerequisite_only.number_of_edges(),
                "constraint_rows": len(model.row_names),
            },
        }
        return selected

    # ------------------------------------------------------------------
    @staticmethod
    def preferred_backend() -> str:
        """
        Name the backend that would be used, without solving.

        Lets the UI show "ILP (scipy/highs)" up front instead of after the fact.
        """
        try:
            solver = _detect_pulp_solver()
        except Exception:
            solver = None
        if solver is not None:
            return f"pulp/{type(solver).__name__}"
        try:
            import scipy  # noqa: F401

            return "scipy/highs"
        except Exception:
            return "unavailable"

    # ------------------------------------------------------------------
    # MODEL CONSTRUCTION
    # ------------------------------------------------------------------
    def _build_model(self, problem: OptimizationProblem) -> LinearModel:
        node_ids = sorted(problem.nodes)
        prereq_edges = [
            problem.edge_between(u, v) for u, v in problem.prerequisite_only.edges()
        ]
        prereq_edges = [e for e in prereq_edges if e is not None]

        names: List[str] = []
        lower: List[float] = []
        upper: List[float] = []
        integrality: List[int] = []
        objective: List[float] = []
        keys: List[str] = []
        index: Dict[str, int] = {}

        soft_edges = [
            e for e in prereq_edges if e.prerequisite_type == PrerequisiteType.SOFT
        ]
        soft_edge_ids = {e.edge_id for e in soft_edges}
        # Topics that have at least one SOFT parent edge.
        soft_targets = {e.target for e in soft_edges}
        penalty = problem.constraints.soft_skip_penalty

        # ---- Variables: node selection --------------------------------
        for node_id in node_ids:
            key = f"x::{node_id}"
            index[key] = len(names)
            keys.append(key)
            names.append(f"x_{_safe(node_id)}")
            lower.append(0.0)
            upper.append(1.0)
            integrality.append(1)
            # The SOFT skip penalty enters as `-penalty * (x_target - y_e)`
            # rather than `-penalty * (1 - y_e)`. The distinction is
            # load-bearing: a SOFT edge whose target is NOT in the plan must not
            # be charged at all, because net_utility only penalises skipping a
            # SOFT prerequisite of something already selected. `x_target - y_e`
            # is both exact and linear, since C2 guarantees y_e <= x_target.
            objective.append(
                problem.nodes[node_id].learning_value
                - (penalty if node_id in soft_targets else 0.0)
            )

        # ---- Variables: edge traversal --------------------------------
        for edge in prereq_edges:
            key = f"y::{edge.edge_id}"
            index[key] = len(names)
            keys.append(key)
            names.append(f"y_{_safe(edge.edge_id)}")
            lower.append(0.0)
            upper.append(1.0)
            integrality.append(1)
            coefficient = -edge.edge_cost
            if edge.edge_id in soft_edge_ids:
                coefficient += penalty
            objective.append(coefficient)

        # Prerequisite edges grouped by the node they feed.
        incoming: Dict[str, List[str]] = {v: [] for v in node_ids}
        for edge in prereq_edges:
            incoming[edge.target].append(edge.edge_id)

        # An edge is DISABLEABLE when its type can be skipped: SOFT (allowed by
        # default, charged a penalty) or OPTIONAL. HARD edges are always live.
        skippable_types = {PrerequisiteType.SOFT, PrerequisiteType.OPTIONAL}
        live_edges = [
            e
            for e in prereq_edges
            if (
                e.prerequisite_type not in skippable_types
                or (
                    e.prerequisite_type == PrerequisiteType.SOFT
                    and problem.constraints.include_soft
                )
                or (
                    e.prerequisite_type == PrerequisiteType.OPTIONAL
                    and problem.constraints.include_optional
                )
            )
        ]

        row_names: List[str] = []
        row_coeffs: List[Dict[int, float]] = []
        row_sense: List[str] = []
        row_rhs: List[float] = []

        def add_row(name: str, coeffs: Dict[int, float], sense: str, rhs: float) -> None:
            row_names.append(name)
            row_coeffs.append(coeffs)
            row_sense.append(sense)
            row_rhs.append(rhs)

        # --- C2a: target must be selected ------------------------------
        add_row("target_selected", {index[f"x::{problem.target_id}"]: 1.0}, "==", 1.0)

        # --- C2b: HARD closure is mandatory ---------------------------
        for mandatory in sorted(problem.hard_prerequisites):
            key = f"x::{mandatory}"
            if key in index:
                add_row(f"hard_required_{_safe(mandatory)}", {index[key]: 1.0}, "==", 1.0)

        # ------------------------------------------------------------------
        # Selection semantics
        #
        # C1  HARD edge into v   :  y_e == x_v        mandatory once v is chosen
        # C2  any live edge into v:  y_e <= x_v        optional edge needs v
        # C3  any live edge out of v : y_e <= x_source  cannot walk an edge
        #                                            without its source
        # C5  node support      :  x_v <= Sum(y_out)  a selected node must
        #                                            enable something
        #
        # There is deliberately NO separate "incoming reachability" constraint.
        # Two tempting formulations are both wrong:
        #
        #   Sum(y_in) == x_v   forces a node to traverse EVERY parent edge,
        #                      including SOFT/OPTIONAL detours, which
        #                      over-constrains the model and can make it
        #                      infeasible.
        #
        #   x_v <= Sum(y_in)   rejects legitimate leaf prerequisites. A root
        #                      concept (e.g. "Variables") has no prerequisites of
        #                      its own yet must be selectable, so it would be
        #                      pinned to 0 and HARD closure could never be met.
        #
        # C5 alone is sufficient: the subgraph is already restricted to the
        # target's ancestor closure, and C5 forces every selected node to have a
        # traversed outgoing edge, which is exactly the "attached to the path"
        # condition we need.
        # ------------------------------------------------------------------
        for edge in prereq_edges:
            if edge.prerequisite_type == PrerequisiteType.HARD:
                # C1 - HARD parents are mandatory. With AND semantics below this
                # is implied (x_target == 1 forces y_e == x_source == 1); stating
                # it explicitly keeps the model readable and tightens the LP.
                add_row(
                    f"hard_edge_{_safe(edge.edge_id)}",
                    {
                        index[f"y::{edge.edge_id}"]: 1.0,
                        index[f"x::{edge.target}"]: -1.0,
                    },
                    "==",
                    0.0,
                )

        # ------------------------------------------------------------------
        # Edge semantics: an edge belongs to the plan iff BOTH endpoints are
        # selected. Encoded exactly with the standard AND linearisation:
        #
        #     y_e <= x_source
        #     y_e <= x_target
        #     y_e >= x_source + x_target - 1
        #
        # This matters more than it looks. An earlier formulation left the
        # traversal variable free for SOFT/OPTIONAL edges, so the model could
        # select both endpoints yet pay no cost for the edge joining them --
        # while net_utility charges that edge in full. The ILP was therefore
        # optimising a strictly cheaper problem than the metric it was scored
        # against, and on some targets it returned a plan that scored *worse*
        # than the DP's. AND semantics removes the discrepancy entirely.
        #
        # Two useful consequences fall out for free:
        #   * a HARD parent is forced on: x_target == 1 forces
        #     y_e >= x_source, and y_e <= x_source, so y_e == x_source == 1;
        #   * an edge is "skipped" exactly when its target is selected and its
        #     source is not, which is precisely net_utility's skip rule, so the
        #     penalty term penalty * (x_target - y_e) is exact and linear.
        # ------------------------------------------------------------------
        for edge in live_edges:
            src = index[f"x::{edge.source}"]
            dst = index[f"x::{edge.target}"]
            y = index[f"y::{edge.edge_id}"]

            add_row(
                f"and_ub_source_{_safe(edge.edge_id)}",
                {y: 1.0, src: -1.0},
                "<=",
                0.0,
            )
            add_row(
                f"and_ub_target_{_safe(edge.edge_id)}",
                {y: 1.0, dst: -1.0},
                "<=",
                0.0,
            )
            add_row(
                f"and_lb_{_safe(edge.edge_id)}",
                {y: 1.0, src: -1.0, dst: -1.0},
                ">=",
                -1.0,
            )

        # (No incoming-reachability row: see the C5 note above. Live edges are
        # still grouped by target below purely for the constraint docstring.)

        # --- C1c: a node must SUPPORT something -------------------------
        #   x_v <= Sum(y_e for live e out of v)     for v != target
        #
        # Without this, a node whose dependents are all skipped still has
        # x_v == 1 and collects its full learning value while paying no
        # prerequisite-edge cost (edge cost only accrues when BOTH endpoints are
        # selected). The model would then attach unrelated ancestor chains purely
        # to harvest that free value. Requiring an outgoing traversal means every
        # selected concept is learned because something else in the plan needs it.
        outgoing: Dict[str, List[str]] = {v: [] for v in node_ids}
        for edge in live_edges:
            outgoing[edge.source].append(edge.edge_id)

        for node_id in node_ids:
            if node_id == problem.target_id:
                continue
            out_edges = outgoing.get(node_id, [])
            if not out_edges:
                # Nothing live depends on it, so it can never be justified.
                add_row(
                    f"unsupported_{_safe(node_id)}",
                    {index[f"x::{node_id}"]: 1.0},
                    "<=",
                    0.0,
                )
                continue
            coeffs: Dict[int, float] = {index[f"x::{node_id}"]: 1.0}
            for eid in out_edges:
                coeffs[index[f"y::{eid}"]] = coeffs.get(index[f"y::{eid}"], 0.0) - 1.0
            add_row(f"must_support_{_safe(node_id)}", coeffs, "<=", 0.0)

        # --- C5: explicitly disabled SOFT / OPTIONAL edges --------------
        # Belt-and-braces with `live_edges`: force the variable to zero so the
        # solver cannot even consider walking a disabled detour.
        if not problem.constraints.include_optional:
            for edge in prereq_edges:
                if edge.prerequisite_type == PrerequisiteType.OPTIONAL:
                    add_row(
                        f"optional_off_{_safe(edge.edge_id)}",
                        {index[f"y::{edge.edge_id}"]: 1.0},
                        "<=",
                        0.0,
                    )
        if not problem.constraints.include_soft:
            for edge in prereq_edges:
                if edge.prerequisite_type == PrerequisiteType.SOFT:
                    add_row(
                        f"soft_off_{_safe(edge.edge_id)}",
                        {index[f"y::{edge.edge_id}"]: 1.0},
                        "<=",
                        0.0,
                    )

        # --- C6: time budget --------------------------------------------
        budget = problem.constraints.max_time_budget_minutes
        if budget is not None:
            coeffs = {
                index[f"y::{e.edge_id}"]: float(e.raw_time_minutes)
                for e in live_edges
            }
            if coeffs:
                add_row("time_budget", coeffs, "<=", float(budget))

        # The objective is now fully linear in the variables (the SOFT skip
        # penalty lives in the x/y coefficients via `penalty * (x_t - y_e)`),
        # so there is no constant term to track.
        model = LinearModel(
            names=names,
            lower=lower,
            upper=upper,
            integrality=integrality,
            objective=objective,
            row_names=row_names,
            row_coeffs=row_coeffs,
            row_sense=row_sense,
            row_rhs=row_rhs,
            keys=keys,
        )
        return model

    # ------------------------------------------------------------------
    def _read_solution(
        self, problem: OptimizationProblem, solution: LinearSolution
    ) -> Tuple[Set[str], List[str]]:
        if not solution.values:
            return {problem.target_id}, []

        selected: Set[str] = {problem.target_id}
        for node_id in problem.nodes:
            if solution.values.get(f"x::{node_id}", 0.0) > 0.5:
                selected.add(node_id)

        # Drop anything the model selected but never actually walked to. x_v is
        # only meaningful alongside a traversed edge; a stray 1 would add
        # learning value without contributing to the path.
        connected: Set[str] = set()
        for edge in problem.edges.values():
            if solution.values.get(f"y::{edge.edge_id}", 0.0) <= 0.5:
                continue
            if edge.source in selected and edge.target in selected:
                connected.add(edge.source)
                connected.add(edge.target)

        selected &= connected | {problem.target_id}

        used: List[str] = [
            edge.edge_id
            for edge in problem.edges.values()
            if solution.values.get(f"y::{edge.edge_id}", 0.0) > 0.5
        ]
        return selected, used

    # ------------------------------------------------------------------
    def describe(
        self, problem: OptimizationProblem, selected: Set[str]
    ) -> Dict[str, object]:
        diagnostics = dict(getattr(self, "_diagnostics", {}))
        diagnostics["formulation"] = (
            "Flow-conservation MILP over binary node/edge variables"
        )
        diagnostics["reporting_metric"] = (
            "PathScore = AvgLearningValue / (TotalPathCost + 0.01)"
        )
        return diagnostics


# ============================================================================
# BACKEND DISPATCH
# ============================================================================

def _solve_model(model: LinearModel) -> LinearSolution:
    """
    Dispatch to the first working MILP backend.

    PuLP is preferred (it is the declared modelling dependency). When no
    command-line solver binary is installed we fall back to
    ``scipy.optimize.milp``, which bundles HiGHS in-process.
    """
    notes: List[str] = []

    try:
        return _solve_with_pulp(model)
    except Exception as exc:
        notes.append(f"pulp backend unavailable: {type(exc).__name__}: {exc}")
        logger.debug("ILP pulp backend unavailable: %s", exc)

    try:
        return _solve_with_scipy(model)
    except Exception as exc:
        notes.append(f"scipy backend unavailable: {type(exc).__name__}: {exc}")
        logger.debug("ILP scipy backend unavailable: %s", exc)

    return LinearSolution(
        status="NoBackend",
        values={},
        objective=0.0,
        backend="none",
        notes=notes,
    )


def _solve_with_pulp(model: LinearModel) -> LinearSolution:
    import pulp

    solver = _detect_pulp_solver()
    if solver is None:
        raise RuntimeError(
            "no PuLP solver binary found (searched PATH and the pulp package dir)"
        )

    prob = pulp.LpProblem("learning_path_ilp", pulp.LpMaximize)

    # PuLP >= 4 requires variables to be created through the problem object.
    variables = {}
    for name, lo, hi, is_int in zip(
        model.names, model.lower, model.upper, model.integrality
    ):
        if is_int:
            cat = (
                pulp.LpBinary
                if (lo == 0.0 and hi == 1.0)
                else pulp.LpInteger
            )
        else:
            cat = pulp.LpContinuous
        variables[name] = prob.add_variable(name, lo, hi, cat)

    prob += pulp.lpSum(
        coef * variables[name] for name, coef in zip(model.names, model.objective)
    )

    sense_map = {"<=": "L", ">=": "G", "==": "E"}
    for row_name, coeffs, sense, rhs in zip(
        model.row_names, model.row_coeffs, model.row_sense, model.row_rhs
    ):
        expr = pulp.lpSum(
            coef * variables[model.names[i]] for i, coef in coeffs.items()
        )
        attribute = sense_map.get(sense, "E")
        if attribute == "L":
            constraint = expr <= rhs
        elif attribute == "G":
            constraint = expr >= rhs
        else:
            constraint = expr == rhs
        prob += constraint, _safe(row_name)

    prob.solve(solver)

    status_name = pulp.LpStatus.get(prob.status, "Unknown")
    # Key by the INTERNAL key so _read_solution can query "x::<node_id>".
    values = {
        model.keys[i]: _num(variables[name].value())
        for i, name in enumerate(model.names)
    }

    return LinearSolution(
        status=status_name,
        values=values,
        objective=_num(pulp.value(prob.objective)),
        backend=f"pulp/{type(solver).__name__}",
    )


def _detect_pulp_solver():
    """Locate an installed PuLP MILP binary (CBC first, then HiGHS)."""
    import pulp

    for factory in (lambda: pulp.CBC_CMD(msg=0), lambda: pulp.HiGHS_CMD(msg=0)):
        try:
            solver = factory()
            if solver.available():
                return solver
        except Exception:  # pragma: no cover - defensive
            continue

    # Some distributions ship the binary inside the package directory.
    try:
        import pulp.apis

        apis_dir = next(iter(pulp.apis.__path__), None)
        if apis_dir:
            for sub in ("", "bin"):
                for binary in ("cbc.exe", "highs.exe", "cbc", "highs"):
                    candidate = os.path.join(apis_dir, sub, binary)
                    if os.path.exists(candidate):
                        try:
                            return pulp.HiGHS_CMD(path=candidate, msg=0)
                        except Exception:  # pragma: no cover
                            continue
    except Exception:  # pragma: no cover
        pass

    return None


def _solve_with_scipy(model: LinearModel) -> LinearSolution:
    """In-process HiGHS MILP via ``scipy.optimize.milp``."""
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp

    n = len(model.names)
    cost = -np.asarray(model.objective, dtype=float)  # milp minimises
    lower = np.asarray(model.lower, dtype=float)
    upper = np.asarray(model.upper, dtype=float)
    integrality = np.asarray(model.integrality, dtype=int)

    if model.row_coeffs:
        matrix = np.zeros((len(model.row_coeffs), n), dtype=float)
        row_low = np.empty(len(model.row_coeffs), dtype=float)
        row_up = np.empty(len(model.row_coeffs), dtype=float)
        for i, (coeffs, sense, rhs) in enumerate(
            zip(model.row_coeffs, model.row_sense, model.row_rhs)
        ):
            for col, coef in coeffs.items():
                matrix[i, col] = coef
            if sense == "<=":
                row_low[i], row_up[i] = -np.inf, rhs
            elif sense == ">=":
                row_low[i], row_up[i] = rhs, np.inf
            else:
                row_low[i], row_up[i] = rhs, rhs
        constraints = LinearConstraint(matrix, row_low, row_up)
    else:
        constraints = []

    result = milp(
        c=cost,
        constraints=constraints,
        integrality=integrality,
        bounds=Bounds(lower, upper),
    )

    if result.x is None:
        return LinearSolution(
            status=f"NoSolution(status={result.status})",
            values={},
            objective=0.0,
            backend="scipy/highs",
            notes=[str(getattr(result, "message", ""))],
        )

    # Key by the INTERNAL key so _read_solution can query "x::<node_id>".
    values = {
        model.keys[i]: float(result.x[i]) for i in range(n)
    }
    return LinearSolution(
        status="Optimal",
        values=values,
        objective=float(-result.fun) if result.fun is not None else 0.0,
        backend="scipy/highs",
    )


# ============================================================================
# HELPERS
# ============================================================================

def _safe(raw: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(raw))


def _num(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
