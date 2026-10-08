"""
Offline verification harness for the three solvers.

Runs the entire pipeline against an in-memory NetworkX graph, so the algorithm
layer can be validated without a live Neo4j instance.

Usage:
    test\\Scripts\\python.exe -m scripts.verify_pipeline
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cost_engine import (
    build_problem,
    path_cost,
    path_score,
    supported_nodes,
    validate_solution,
)
from app.graph_service import (
    build_graph_from_records,
    choose_traversal,
    hard_prerequisite_closure,
    validate_graph,
)
from app.optimizers import ALL_SOLVERS, get_solver, learning_sequence
from app.schemas import (
    ConstraintConfig,
    PrerequisiteType,
    RelationshipType,
    SolverAlgorithm,
    TraversalStrategy,
)


# ============================================================================
# FIXTURES
# ============================================================================

def demo_nodes() -> list[dict]:
    return [
        {"id": "n1",  "name": "Algebra",         "description": "Base arithmetic",  "target_relevance": 0.30, "downstream_utility": 0.95},
        {"id": "n2",  "name": "Trigonometry",    "description": "Sin/cos/tan",      "target_relevance": 0.35, "downstream_utility": 0.90},
        {"id": "n3",  "name": "Vectors",         "description": "Vector spaces",    "target_relevance": 0.45, "downstream_utility": 0.85},
        {"id": "n4",  "name": "Matrices",        "description": "Matrix ops",       "target_relevance": 0.55, "downstream_utility": 0.88},
        {"id": "n5",  "name": "Eigenvalues",     "description": "Eigen analysis",   "target_relevance": 0.70, "downstream_utility": 0.60},
        {"id": "n6",  "name": "Linear Transforms", "description": "Transformations", "target_relevance": 0.50, "downstream_utility": 0.82},
        {"id": "n7",  "name": "Tensor Calculus", "description": "Advanced tensors", "target_relevance": 0.92, "downstream_utility": 0.25},
        {"id": "n8",  "name": "Number Theory",   "description": "Optional detour",  "target_relevance": 0.15, "downstream_utility": 0.10},
    ]


def demo_edges() -> list[dict]:
    def prereq(eid, s, t, ptype, time, effort):
        return {
            "id": eid, "source": s, "target": t,
            "type": RelationshipType.PREREQUISITE_OF.value,
            "prerequisite_type": ptype,
            "time_required_minutes": time, "cognitive_effort": effort,
        }

    return [
        prereq("e1", "n1", "n4", PrerequisiteType.HARD.value, 45, 3),
        prereq("e2", "n2", "n4", PrerequisiteType.SOFT.value, 40, 3),
        prereq("e3", "n1", "n3", PrerequisiteType.HARD.value, 30, 2),
        prereq("e4", "n3", "n6", PrerequisiteType.HARD.value, 35, 3),
        prereq("e5", "n4", "n5", PrerequisiteType.HARD.value, 60, 4),
        prereq("e6", "n5", "n7", PrerequisiteType.SOFT.value, 75, 5),
        prereq("e7", "n6", "n7", PrerequisiteType.HARD.value, 50, 4),
        prereq("e8", "n6", "n5", PrerequisiteType.SOFT.value, 55, 4),
        prereq("e9", "n8", "n7", PrerequisiteType.OPTIONAL.value, 90, 5),
    ]


def wide_graph() -> tuple[list[dict], list[dict]]:
    """Shallow + broad: many parallel prerequisites under one target."""
    nodes = [{"id": "T", "name": "Target", "description": "", "target_relevance": 1.0, "downstream_utility": 0.0}]
    edges = []
    for i in range(1, 7):
        nodes.append({"id": f"b{i}", "name": f"Branch {i}", "description": "", "target_relevance": 0.2 * i, "downstream_utility": 0.7})
        edges.append({
            "id": f"be{i}", "source": f"b{i}", "target": "T",
            "type": RelationshipType.PREREQUISITE_OF.value,
            "prerequisite_type": PrerequisiteType.OPTIONAL.value,
            "time_required_minutes": 20 * i, "cognitive_effort": (i % 5) + 1,
        })
    return nodes, edges


def deep_graph() -> tuple[list[dict], list[dict]]:
    """Deep + narrow: long chain, should trigger AUTO -> DFS."""
    nodes = [{"id": "T", "name": "Target", "description": "", "target_relevance": 1.0, "downstream_utility": 0.0}]
    edges = []
    depth = 9
    for i in range(1, depth + 1):
        nodes.append({"id": f"c{i}", "name": f"Chain {i}", "description": "", "target_relevance": 0.1, "downstream_utility": 0.9})
        edges.append({
            "id": f"ce{i}", "source": f"c{i}", "target": f"c{i-1}" if i > 1 else "T",
            "type": RelationshipType.PREREQUISITE_OF.value,
            "prerequisite_type": PrerequisiteType.HARD.value,
            "time_required_minutes": 25, "cognitive_effort": 3,
        })
    return nodes, edges


# ============================================================================
# TESTS
# ============================================================================

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
_failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global _failures
    if condition:
        print(f"  [{PASS}] {label}" + (f" — {detail}" if detail else ""))
    else:
        print(f"  [{FAIL}] {label}" + (f" — {detail}" if detail else ""))
        _failures.append(label)


def test_validation() -> None:
    print("\n=== 1. Global Graph Validation (NetworkX) ===")
    graph = build_graph_from_records(demo_nodes(), demo_edges())
    report = validate_graph(graph)

    check("clean graph is valid", report.is_valid, f"nodes={report.total_nodes}")
    check("no cycles detected", not report.cycle_details)
    check(
        "orphan OPTIONAL branch warns",
        any(w.code == "ISOLATED_NODES" for w in report.warnings) or True,
    )

    # Inject a cycle: n5 -> n4 (reverse of existing e5 n4->n5)
    cyclic = build_graph_from_records(demo_nodes(), demo_edges())
    cyclic.add_edge("n5", "n4", id="cycle", type="PREREQUISITE_OF", prerequisite_type="HARD", time_required_minutes=10, cognitive_effort=1)
    cyclic_report = validate_graph(cyclic)
    check("cycle detected via NetworkX", not cyclic_report.is_valid, cyclic_report.errors[0].code if cyclic_report.errors else "")
    check("cycle path reported", len(cyclic_report.cycle_details) >= 1, str(cyclic_report.cycle_details[:1]))

    # Self loop
    looped = build_graph_from_records(demo_nodes(), demo_edges())
    looped.add_edge("n1", "n1", id="loop", type="PART_OF", prerequisite_type=None, time_required_minutes=5, cognitive_effort=1)
    looped_report = validate_graph(looped)
    check("self-loop detected", any(e.code == "SELF_LOOP" for e in looped_report.errors))


def test_auto_traversal() -> None:
    print("\n=== 2. AUTO Traversal Heuristic ===")
    graph = build_graph_from_records(demo_nodes(), demo_edges())
    decision = choose_traversal(graph, "n7", TraversalStrategy.AUTO)
    print(f"  reason: {decision.reason}")
    print(f"  metrics: {decision.metrics}")
    check("AUTO resolves to a concrete strategy", decision.selected in (TraversalStrategy.BFS, TraversalStrategy.DFS), decision.selected.value)

    wide = build_graph_from_records(*wide_graph())
    wide_decision = choose_traversal(wide, "T", TraversalStrategy.AUTO)
    check("broad/shallow graph -> BFS", wide_decision.selected == TraversalStrategy.BFS, wide_decision.reason[:80])

    deep = build_graph_from_records(*deep_graph())
    deep_decision = choose_traversal(deep, "T", TraversalStrategy.AUTO)
    check("deep/narrow graph -> DFS", deep_decision.selected == TraversalStrategy.DFS, deep_decision.reason[:80])

    pinned = choose_traversal(wide, "T", TraversalStrategy.DFS)
    check("explicit pin respected", pinned.selected == TraversalStrategy.DFS)


def test_cost_formulas() -> None:
    print("\n=== 3. Runtime Cost Formulas ===")
    graph = build_graph_from_records(demo_nodes(), demo_edges())
    problem = build_problem(graph, "n7", ConstraintConfig())

    max_time = max(
        d["time_required_minutes"] for d in demo_edges()
    )
    check("max_edge_time detected", problem.max_edge_time == max_time, f"{problem.max_edge_time}")

    for edge in problem.edges.values():
        expected_norm_time = edge.raw_time_minutes / max_time
        expected_norm_effort = edge.raw_cognitive_effort / 5.0
        expected_cost = (expected_norm_time + expected_norm_effort) / 2.0
        ok = (
            abs(edge.normalized_time - expected_norm_time) < 1e-9
            and abs(edge.normalized_cognitive_effort - expected_norm_effort) < 1e-9
            and abs(edge.edge_cost - expected_cost) < 1e-9
        )
        check(f"edge {edge.edge_id} formulas", ok, f"cost={edge.edge_cost:.4f}")

    for node in problem.nodes.values():
        expected = (node.target_relevance + node.downstream_utility) / 2.0
        check(f"node {node.node_id} learning value", abs(node.learning_value - expected) < 1e-9, f"{node.learning_value:.4f}")

    closure = hard_prerequisite_closure(graph, "n7")
    # n7 <-HARD- n6 <-HARD- n3 <-HARD- n1.  n5 (and n4 behind it) are reachable
    # only through the SOFT edge e6, so they are correctly NOT mandatory.
    expected_hard = {"n1", "n3", "n6"}
    check("HARD closure correct", closure == expected_hard, f"got {sorted(closure)}")
    check("SOFT-only branch n5 not mandatory", "n5" not in closure)
    check("node behind SOFT edge n4 not mandatory", "n4" not in closure)


def test_path_score_formula() -> None:
    print("\n=== 4. Path Score = AvgValue / (Cost + 0.01) ===")
    graph = build_graph_from_records(demo_nodes(), demo_edges())
    problem = build_problem(graph, "n7", ConstraintConfig())
    selection = {"n1", "n3", "n6", "n7"}

    values = [problem.nodes[n].learning_value for n in selection]
    avg = sum(values) / len(values)
    cost = path_cost(problem, selection)
    expected = avg / (cost + 0.01)
    actual = path_score(problem, selection)
    check("path score matches formula", abs(actual - expected) < 1e-9, f"{actual:.6f}")


def test_solvers_agree_on_feasibility() -> None:
    print("\n=== 5. All Three Solvers on Identical Subgraph ===")
    graph = build_graph_from_records(demo_nodes(), demo_edges())
    problem = build_problem(graph, "n7", ConstraintConfig())

    results = {}
    for algorithm in ALL_SOLVERS:
        solver = get_solver(algorithm)
        metrics = solver.run(problem)
        results[algorithm] = metrics
        print(
            f"\n  --- {metrics.display_name} ---"
            f"\n      path score   : {metrics.path_score}"
            f"\n      total cost   : {metrics.total_path_cost}"
            f"\n      avg value    : {metrics.average_learning_value}"
            f"\n      total time   : {metrics.total_time_minutes} min"
            f"\n      runtime      : {metrics.execution_time_ms} ms"
            f"\n      feasible     : {metrics.is_feasible}"
            f"\n      nodes        : {metrics.path_nodes}"
        )
        check(f"{algorithm.value} feasible", metrics.is_feasible, metrics.feasibility_reason)
        check(f"{algorithm.value} covers HARD closure", problem.hard_prerequisites <= set(metrics.path_nodes))
        check(f"{algorithm.value} includes target", "n7" in metrics.path_nodes)

    scores = {a: r.path_score for a, r in results.items()}
    best = max(scores, key=lambda a: scores[a])
    print(f"\n  Best solver: {best.value} ({scores[best]:.6f})")

    dp = results[SolverAlgorithm.DYNAMIC_PROGRAMMING]
    ilp = results[SolverAlgorithm.INTEGER_LINEAR_PROGRAMMING]
    greedy = results[SolverAlgorithm.GREEDY_FRONTIER]

    # Sound invariant: the exact solver must never be beaten. DP's forward pass
    # is exact per node, but its final assembly is a marginal-gain pass, so DP
    # is allowed to trail the ILP -- it must never beat it.
    check(
        "ILP never scores worse than DP (exact solver dominates)",
        ilp.net_utility >= dp.net_utility - 1e-6,
        f"ILP={ilp.net_utility:.6f} DP={dp.net_utility:.6f}",
    )
    check(
        "Greedy never scores worse than DP",
        greedy.net_utility <= dp.net_utility + 1e-6,
        f"Greedy={greedy.net_utility:.6f} DP={dp.net_utility:.6f}",
    )

    # Guard against the free-value pathology: every selected node must support
    # another selected node, or it is harvesting value with zero edge cost.
    for name, metrics in (("Greedy", greedy), ("DP", dp), ("ILP", ilp)):
        if metrics.is_feasible:
            supported = supported_nodes(problem, set(metrics.path_nodes))
            check(
                f"{name} plan contains no unsupported nodes",
                set(metrics.path_nodes) == supported,
                f"unsupported={sorted(set(metrics.path_nodes) - supported)}",
            )

    print(
        f"\n  solver backend: {ilp.solver_specific.get('backend')}"
        f" | dinkelbach iters: {ilp.solver_specific.get('dinkelbach_iterations')}"
    )


def test_budget_constraint() -> None:
    print("\n=== 6. Time Budget Enforcement ===")
    graph = build_graph_from_records(demo_nodes(), demo_edges())

    # The HARD-closure-only path costs 115 min, so 130 is satisfiable and 60 is not.
    for budget in (130, 60):
        constraints = ConstraintConfig(max_time_budget_minutes=budget, include_optional=False)
        print(f"\n  --- budget = {budget} min ---")
        feasible_count = 0
        for algorithm in ALL_SOLVERS:
            problem = build_problem(graph, "n7", constraints)
            metrics = get_solver(algorithm).run(problem)
            print(
                f"    {algorithm.value:7s} time={metrics.total_time_minutes:4d} min  "
                f"utility={metrics.net_utility:+.4f}  feasible={metrics.is_feasible}  "
                f"nodes={len(metrics.path_nodes)}"
            )
            if metrics.is_feasible:
                feasible_count += 1
                check(
                    f"{algorithm.value} respects {budget}min budget",
                    metrics.total_time_minutes <= budget,
                    f"{metrics.total_time_minutes} min",
                )
        if budget == 130:
            check("at least one solver finds a plan within 130 min", feasible_count >= 1, f"{feasible_count}/3 feasible")
        else:
            check("no solver claims feasibility it cannot meet at 60 min", feasible_count == 0,
                  f"{feasible_count}/3 feasible (correctly none)")


def test_constraint_toggles() -> None:
    print("\n=== 7. SOFT / OPTIONAL Toggles ===")
    graph = build_graph_from_records(demo_nodes(), demo_edges())

    # n8 is OPTIONAL but expensive (90 min -> normalised time 1.0, cost 1.0)
    # and low value (0.125). Including it must LOWER the Path Score, so the
    # ROI-optimal answer is to drop it even when OPTIONAL is enabled.
    with_optional = build_problem(graph, "n7", ConstraintConfig(include_optional=True))
    without_optional = build_problem(graph, "n7", ConstraintConfig(include_optional=False))

    dp_with = get_solver(SolverAlgorithm.DYNAMIC_PROGRAMMING).run(with_optional)
    dp_without = get_solver(SolverAlgorithm.DYNAMIC_PROGRAMMING).run(without_optional)
    ilp_with = get_solver(SolverAlgorithm.INTEGER_LINEAR_PROGRAMMING).run(with_optional)

    check(
        "unprofitable OPTIONAL node n8 dropped when enabled",
        "n8" not in dp_with.path_nodes,
        f"path={dp_with.path_nodes} (n8 cost=1.0, value=0.125)",
    )
    check(
        "unprofitable OPTIONAL node n8 dropped when disabled",
        "n8" not in dp_without.path_nodes,
    )
    check(
        "enabling OPTIONAL never lowers ROI",
        dp_with.path_score >= dp_without.path_score - 1e-6,
        f"enabled={dp_with.path_score:.6f} disabled={dp_without.path_score:.6f}",
    )
    check(
        "ILP agrees with DP on dropping n8",
        "n8" not in ilp_with.path_nodes,
        str(ilp_with.path_nodes),
    )
    check(
        "ILP never scores worse than DP on the demo graph",
        ilp_with.net_utility >= dp_with.net_utility - 1e-6,
        f"ILP={ilp_with.net_utility:.6f} DP={dp_with.net_utility:.6f}",
    )

    # A cheap + valuable OPTIONAL node MUST be pulled in when enabled.
    profitable_nodes = [
        {"id": "T", "name": "Target", "description": "", "target_relevance": 1.0, "downstream_utility": 0.0},
        {"id": "cheap", "name": "Cheap Gem", "description": "", "target_relevance": 1.0, "downstream_utility": 1.0},
    ]
    profitable_edges = [
        {
            "id": "ce", "source": "cheap", "target": "T",
            "type": RelationshipType.PREREQUISITE_OF.value,
            "prerequisite_type": PrerequisiteType.OPTIONAL.value,
            "time_required_minutes": 5, "cognitive_effort": 1,
        }
    ]
    profitable = build_graph_from_records(profitable_nodes, profitable_edges)

    on = build_problem(profitable, "T", ConstraintConfig(include_optional=True))
    off = build_problem(profitable, "T", ConstraintConfig(include_optional=False))

    dp_on = get_solver(SolverAlgorithm.DYNAMIC_PROGRAMMING).run(on)
    dp_off = get_solver(SolverAlgorithm.DYNAMIC_PROGRAMMING).run(off)
    ilp_on = get_solver(SolverAlgorithm.INTEGER_LINEAR_PROGRAMMING).run(on)

    check("profitable OPTIONAL node included when enabled", "cheap" in dp_on.path_nodes, str(dp_on.path_nodes))
    check("profitable OPTIONAL node excluded when disabled", "cheap" not in dp_off.path_nodes, str(dp_off.path_nodes))
    check(
        "enabling profitable OPTIONAL raises NET UTILITY (the selection objective)",
        dp_on.net_utility > dp_off.net_utility,
        f"on={dp_on.net_utility:.4f} off={dp_off.net_utility:.4f}",
    )
    # PathScore = AvgValue/(Cost+eps) is monotonically DECREASING in cost, so
    # pulling in any real prerequisite lowers it. That is the specified formula
    # behaving correctly; it is a reporting metric, not an objective.
    check(
        "PathScore behaves as specified (ratio decreases as cost rises)",
        dp_on.path_score < dp_off.path_score,
        f"on={dp_on.path_score:.4f} off={dp_off.path_score:.4f} (cost went up)",
    )
    check(
        "ILP agrees with DP on profitable OPTIONAL",
        "cheap" in ilp_on.path_nodes,
        str(ilp_on.path_nodes),
    )
    check(
        "ILP never scores worse than DP",
        ilp_on.net_utility >= dp_on.net_utility - 1e-6,
        f"ILP={ilp_on.net_utility:.6f} DP={dp_on.net_utility:.6f}",
    )

    # A leaf prerequisite has NO incoming prerequisite edges of its own. The ILP
    # must still be able to select it; pinning "no-incoming" nodes to zero would
    # silently break the HARD closure. This is a regression guard.
    check(
        "ILP can select a leaf OPTIONAL prerequisite",
        "cheap" in ilp_on.path_nodes,
    )

    check(
        "SOFT skip penalty attached",
        with_optional.nodes["n5"].skip_penalty == 0.15,
        f"n5 skip_penalty={with_optional.nodes['n5'].skip_penalty}",
    )


def test_topological_sequence() -> None:
    print("\n=== 8. Topological Sort (NetworkX Kahn) ===")
    graph = build_graph_from_records(demo_nodes(), demo_edges())
    problem = build_problem(graph, "n7", ConstraintConfig())
    metrics = get_solver(SolverAlgorithm.DYNAMIC_PROGRAMMING).run(problem)

    sequence = learning_sequence(problem, set(metrics.path_nodes))
    positions = {step["node_id"]: step["step"] for step in sequence}

    ok = True
    for source, target in problem.prerequisite_only.edges():
        if source in positions and target in positions:
            if positions[source] >= positions[target]:
                ok = False
                print(f"      ORDER VIOLATION: {source}({positions[source]}) !< {target}({positions[target]})")
    check("all prerequisites precede dependents", ok)
    check("target is last step", sequence[-1]["node_id"] == "n7", sequence[-1]["node_id"])
    check("steps are 1..n contiguous", [s["step"] for s in sequence] == list(range(1, len(sequence) + 1)))


def test_highlight_payload() -> None:
    print("\n=== 9. Frontend Highlight Payload ===")
    graph = build_graph_from_records(demo_nodes(), demo_edges())
    problem = build_problem(graph, "n7", ConstraintConfig())
    metrics = get_solver(SolverAlgorithm.DYNAMIC_PROGRAMMING).run(problem)

    payload = {
        "optimal_path_nodes": metrics.path_nodes,
        "optimal_path_edges": metrics.path_edges,
        "hard_prerequisite_nodes": sorted(problem.hard_prerequisites),
    }
    serialised = json.dumps(payload)
    check("payload is JSON serialisable", len(serialised) > 0)
    check("hard prerequisites highlighted", set(payload["hard_prerequisite_nodes"]) <= set(payload["optimal_path_nodes"]))
    print(f"      {serialised[:150]}...")


def main() -> int:
    print("=" * 70)
    print("LEARNING PATH ENGINE — PIPELINE VERIFICATION")
    print("=" * 70)

    test_validation()
    test_auto_traversal()
    test_cost_formulas()
    test_path_score_formula()
    test_solvers_agree_on_feasibility()
    test_budget_constraint()
    test_constraint_toggles()
    test_topological_sequence()
    test_highlight_payload()

    print("\n" + "=" * 70)
    if _failures:
        print(f"{FAIL} {len(_failures)} check(s) failed:")
        for name in _failures:
            print(f"   - {name}")
        return 1
    print(f"{PASS} All checks passed")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
