"""
End-to-end API smoke test.
 *
 * Runs the whole pipeline against an in-memory graph by monkey-patching the
 * Neo4j loader, so the FastAPI routes, Pydantic schemas and JSON serialisation
 * are all exercised without a live database.
 *
 * Usage:
 *     test/Scripts/python.exe -m scripts.verify_api
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import app.graph_service as graph_service
import app.main as main_module
import app.optimization_service as optimization_service
from app.graph_service import build_graph_from_records
from app.main import app
from app.schemas import PrerequisiteType, RelationshipType

NODES = [
    {"id": "n1", "name": "Algebra", "description": "Base arithmetic", "target_relevance": 0.30, "downstream_utility": 0.95},
    {"id": "n2", "name": "Trigonometry", "description": "Sin/cos/tan", "target_relevance": 0.35, "downstream_utility": 0.90},
    {"id": "n3", "name": "Vectors", "description": "Vector spaces", "target_relevance": 0.45, "downstream_utility": 0.85},
    {"id": "n4", "name": "Matrices", "description": "Matrix ops", "target_relevance": 0.55, "downstream_utility": 0.88},
    {"id": "n5", "name": "Eigenvalues", "description": "Eigen analysis", "target_relevance": 0.70, "downstream_utility": 0.60},
    {"id": "n6", "name": "Linear Transforms", "description": "Transformations", "target_relevance": 0.50, "downstream_utility": 0.82},
    {"id": "n7", "name": "Tensor Calculus", "description": "Advanced tensors", "target_relevance": 0.92, "downstream_utility": 0.25},
    {"id": "n8", "name": "Number Theory", "description": "Optional detour", "target_relevance": 0.15, "downstream_utility": 0.10},
]


def prereq(eid, s, t, p, time, effort):
    return {
        "id": eid, "source": s, "target": t,
        "type": RelationshipType.PREREQUISITE_OF.value,
        "prerequisite_type": p, "time_required_minutes": time, "cognitive_effort": effort,
    }


EDGES = [
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

_GRAPH = build_graph_from_records(NODES, EDGES)


async def _load_graph():
    """Stand-in for the Neo4j loader."""
    return _GRAPH


# Patch every module that imported the loader. FastAPI route handlers bind
# `load_full_graph` into `app.main`'s namespace, and the service binds its own
# copy, so both must be redirected.
optimization_service.load_full_graph = _load_graph
main_module.load_full_graph = _load_graph


PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
_failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [{PASS}] {label}" + (f" - {detail}" if detail else ""))
    else:
        print(f"  [{FAIL}] {label}" + (f" - {detail}" if detail else ""))
        _failures.append(label)


def test_solvers_endpoint(client: TestClient) -> None:
    print("\n=== GET /api/solvers ===")
    response = client.get("/api/solvers")
    check("200 OK", response.status_code == 200, str(response.status_code))
    body = response.json()
    check("three solvers listed", len(body["solvers"]) == 3,
          str([s["id"] for s in body["solvers"]]))
    ids = {s["id"] for s in body["solvers"]}
    check("ids are GREEDY/DP/ILP", ids == {"GREEDY", "DP", "ILP"}, str(sorted(ids)))
    for solver in body["solvers"]:
        check(f"{solver['id']} reports a backend", bool(solver["backend"]), solver["backend"])
    check("metrics documented", "selection_objective" in body["metrics"])


def test_traversal_preview(client: TestClient) -> None:
    print("\n=== GET /api/traversal/preview ===")
    response = client.get("/api/traversal/preview", params={"target_node_id": "n7"})
    check("200 OK", response.status_code == 200, str(response.status_code))
    body = response.json()
    check("AUTO resolved", body["traversal"]["requested"] == "AUTO")
    check("selected a concrete strategy", body["traversal"]["selected"] in ("BFS", "DFS"),
          body["traversal"]["selected"])
    check("rationale present", len(body["traversal"]["reason"]) > 20)
    check("reduction ratio computed", "reduction_ratio" in body["stats"],
          str(body["stats"].get("reduction_ratio")))

    missing = client.get("/api/traversal/preview", params={"target_node_id": "nope"})
    check("404 for unknown target", missing.status_code == 404, str(missing.status_code))


def test_optimize(client: TestClient) -> None:
    print("\n=== POST /api/path/optimize ===")
    for solver in ("DP", "GREEDY", "ILP"):
        response = client.post("/api/path/optimize", json={
            "target_node_id": "n7",
            "search_method": "AUTO",
            "solver": solver,
            "constraints": {
                "include_soft": True,
                "include_optional": True,
                "soft_skip_penalty": 0.15,
                "greedy_lookahead_depth": 3,
            },
            "traversal": {"max_subgraph_nodes": 60},
        })
        check(f"{solver}: 200 OK", response.status_code == 200, str(response.status_code))
        if response.status_code != 200:
            print("      ", response.text[:400])
            continue
        body = response.json()
        result = body["result"]
        check(f"{solver}: feasible", result["is_feasible"], result["feasibility_reason"])
        check(f"{solver}: target in path", "n7" in result["path_nodes"])
        check(f"{solver}: HARD closure covered",
              {"n1", "n3", "n6"} <= set(result["path_nodes"]),
              str(result["path_nodes"]))
        check(f"{solver}: path score positive", result["path_score"] > 0,
              f"{result['path_score']:.4f}")
        check(f"{solver}: net utility reported", "net_utility" in result)
        check(f"{solver}: sequence ordered", len(body["learning_sequence"]) == len(result["path_nodes"]))
        check(f"{solver}: sequence ends at target",
              body["learning_sequence"][-1]["node_id"] == "n7")
        check(f"{solver}: explanation generated", len(body["explanation"]) > 100)

    # Constraint toggle
    print("\n  --- include_optional=False ---")
    response = client.post("/api/path/optimize", json={
        "target_node_id": "n7",
        "search_method": "BFS",
        "solver": "DP",
        "constraints": {"include_soft": True, "include_optional": False,
                        "soft_skip_penalty": 0.15, "greedy_lookahead_depth": 3},
        "traversal": {"max_subgraph_nodes": 60},
    })
    body = response.json()
    check("optional n8 excluded", "n8" not in body["result"]["path_nodes"],
          str(body["result"]["path_nodes"]))

    # Time budget
    print("\n  --- max_time_budget_minutes=60 (unsatisfiable) ---")
    response = client.post("/api/path/optimize", json={
        "target_node_id": "n7",
        "search_method": "DFS",
        "solver": "DP",
        "constraints": {"include_soft": True, "include_optional": True,
                        "soft_skip_penalty": 0.15, "greedy_lookahead_depth": 3,
                        "max_time_budget_minutes": 60},
        "traversal": {"max_subgraph_nodes": 60},
    })
    body = response.json()
    check("reports infeasible under tight budget",
          not body["result"]["is_feasible"], body["result"]["feasibility_reason"])

    # Unknown target -> 404
    missing = client.post("/api/path/optimize", json={
        "target_node_id": "does-not-exist", "search_method": "AUTO", "solver": "DP",
        "constraints": {"include_soft": True, "include_optional": True,
                        "soft_skip_penalty": 0.15, "greedy_lookahead_depth": 3},
        "traversal": {"max_subgraph_nodes": 60},
    })
    check("404 for unknown target", missing.status_code == 404, str(missing.status_code))


def test_compare(client: TestClient) -> None:
    print("\n=== POST /api/path/compare ===")
    response = client.post("/api/path/compare", json={
        "target_node_id": "n7",
        "search_method": "AUTO",
        "constraints": {"include_soft": True, "include_optional": True,
                        "soft_skip_penalty": 0.15, "greedy_lookahead_depth": 3},
        "traversal": {"max_subgraph_nodes": 60},
    })
    check("200 OK", response.status_code == 200, str(response.status_code))
    if response.status_code != 200:
        print("      ", response.text[:500])
        return

    body = response.json()
    comparison = body["comparison"]

    check("all three solvers ran", len(comparison["results"]) == 3,
          str([r["solver"] for r in comparison["results"]]))

    # Same subgraph for every solver
    subgraph_ids = set(comparison["shared_subgraph_node_ids"])
    check("shared subgraph non-empty", len(subgraph_ids) > 0, f"{len(subgraph_ids)} nodes")

    for result in comparison["results"]:
        check(f"{result['solver']}: has all comparison metrics",
              all(key in result for key in (
                  "path_nodes", "total_path_cost", "average_learning_value",
                  "path_score", "total_time_minutes", "is_feasible", "execution_time_ms")))
        check(f"{result['solver']}: execution time measured",
              result["execution_time_ms"] >= 0, f"{result['execution_time_ms']} ms")

    check("best solver identified", comparison["best_solver"] is not None,
          str(comparison["best_solver"]))
    check("recommendation written", len(comparison["recommendation"]) > 60)
    check("rationale lines present", len(comparison["recommendation_rationale"]) > 0,
          f"{len(comparison['recommendation_rationale'])} lines")

    # Learning sequence for every solver
    for key in ("GREEDY", "DP", "ILP"):
        check(f"sequence for {key}", key in body["learning_sequences"],
              f"{len(body['learning_sequences'].get(key, []))} steps")

    # DP and ILP must agree on the global optimum
    dp = next(r for r in comparison["results"] if r["solver"] == "DP")
    ilp = next(r for r in comparison["results"] if r["solver"] == "ILP")
    check("DP and ILP agree on net utility",
          abs(dp["net_utility"] - ilp["net_utility"]) < 1e-6,
          f"DP={dp['net_utility']:.6f} ILP={ilp['net_utility']:.6f}")

    # JSON round-trip
    serialised = json.dumps(body)
    check("response is JSON serialisable", len(serialised) > 500, f"{len(serialised)} bytes")

    print("\n  Comparison table preview:")
    print(f"    {'Solver':<28} {'ROI':>9} {'Utility':>9} {'Cost':>8} {'Time':>8} {'ms':>9}")
    for r in comparison["results"]:
        print(
            f"    {r['display_name']:<28} {r['path_score']:>9.4f} "
            f"{r['net_utility']:>9.4f} {r['total_path_cost']:>8.4f} "
            f"{r['total_time_minutes']:>6}m {r['execution_time_ms']:>9.1f}"
        )
    print(f"\n    BEST: {comparison['best_solver']}")
    print(f"    {comparison['recommendation'][:220]}...")


def test_compare_subset(client: TestClient) -> None:
    print("\n=== POST /api/path/compare (solver subset) ===")
    response = client.post("/api/path/compare", json={
        "target_node_id": "n7",
        "search_method": "DFS",
        "solvers": ["DP"],
        "constraints": {"include_soft": True, "include_optional": True,
                        "soft_skip_penalty": 0.15, "greedy_lookahead_depth": 3},
        "traversal": {"max_subgraph_nodes": 60},
    })
    check("200 OK", response.status_code == 200, str(response.status_code))
    body = response.json()
    check("only requested solver ran", len(body["comparison"]["results"]) == 1,
          str([r["solver"] for r in body["comparison"]["results"]]))


def main() -> int:
    print("=" * 70)
    print("LEARNING PATH ENGINE - API VERIFICATION")
    print("=" * 70)

    with TestClient(app) as client:
        test_solvers_endpoint(client)
        test_traversal_preview(client)
        test_optimize(client)
        test_compare(client)
        test_compare_subset(client)

    print("\n" + "=" * 70)
    if _failures:
        print(f"{FAIL} {len(_failures)} check(s) failed:")
        for name in _failures:
            print(f"   - {name}")
        return 1
    print(f"{PASS} All API checks passed")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
