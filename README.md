# Learning Path Engine

Optimized learning-path engine over a manually defined Knowledge Graph (Neo4j).

**Stack:** Next.js 14 + React Flow · FastAPI · Neo4j · NetworkX · PuLP/HiGHS

---

## Pipeline

```
FULL KG
  → Global Validation          (NetworkX DAG check, cycle detection)
  → Target Selection
  → Reverse Traversal          (AUTO / BFS / DFS)
  → Constraints                (HARD / SOFT / OPTIONAL)
  → Relevant DAG Construction
  → Runtime Normalization      (never written to Neo4j)
  → Optimization               (Greedy / DP / ILP)
  → Best Valid Plan
  → Topological Sort           (NetworkX Kahn)
  → Final Path + Explanation
```

---

## Quick start

```bash
# 1. Neo4j must be running on bolt://localhost:7687 (neo4j / password)

# 2. Backend  -- ALWAYS use the venv interpreter, not plain `python`
cd backend
python -m venv test
test/Scripts/python.exe -m pip install -r requirements.txt
test/Scripts/python.exe -m scripts.preflight          # verify env + Neo4j
test/Scripts/python.exe -m scripts.seed_physics --reset   # 100-node Physics graph
test/Scripts/python.exe -m uvicorn app.main:app --port 8000

# 3. Frontend
cd frontend
npm install
npm run dev            # http://localhost:3000
```

Or just run `start.bat`, which does all of the above.

> **Why the venv matters.** Starting with plain `python -m uvicorn ...` fails with
> `ModuleNotFoundError: No module named 'networkx'` because the dependencies live
> in `backend\test`. Always prefix with `test\Scripts\python.exe`. If you see
> that error, run `scripts.preflight` to confirm what is missing.

### Try it immediately

Open http://localhost:3000, pick a target (try **Quantum Field Theory**,
**String Theory**, or **Gravitational Waves**), then click
**Compare All Solvers**. The graph has 100 nodes; AUTO traversal prunes it to
the ~60-node ancestor subgraph first.

---

## Three solvers, one subgraph

`POST /api/path/compare` traverses **once**, then runs all three solvers over the
identical subgraph so the comparison isolates the algorithm, not the input.

| Solver | Optimality | Approach |
|--------|-----------|----------|
| **Greedy Frontier** | approximate | Local utility with N-step lookahead |
| **Dynamic Programming** | heuristic (exact per-node subproblem) | Forward topological DP, best `(value − cost)` state per node, then marginal-gain assembly |
| **Integer Linear Programming** | **global (exact)** | Flow-conservation MILP |

The invariant the test suite enforces is **ILP ≥ DP ≥ Greedy** on net utility —
the exact solver must never be beaten. DP's forward pass is exact for each
node's covering subproblem, but its final assembly is a heuristic pass (branches
can share ancestors), so it is allowed to trail the ILP.

### Selection objective vs reporting metric

These are deliberately different, and the distinction matters:

```
NetUtility  = Σ LearningValue − Σ EdgeCost − skip penalties   ← what solvers MAXIMISE
PathScore   = AvgLearningValue / (TotalPathCost + 0.01)       ← what the UI REPORTS
```

`PathScore` is strictly **decreasing in cost** for fixed value, so maximising it
directly is degenerate — the optimum would always be "select nothing". It is
therefore used only to rank and compare plans the solvers actually produced.
`NetUtility` is additive and well-posed.

One more modelling rule: a selected node must **support** another selected node
(`x_v ≤ Σ y_e` over outgoing edges). Without it, a node whose dependents are all
skipped still collects its full learning value while paying no prerequisite-edge
cost — free value that makes every optimiser attach unrelated branches.

---

## AUTO traversal

When `search_method = "AUTO"` the system measures the target's ancestor region
and picks a strategy:

- **shallow + broad** → BFS, to surface all alternative branches cheaply
- **deep + narrow** → DFS, to follow the chain without materialising siblings

The decision and its metrics are returned to the UI, which shows the rationale.
Pin `BFS`/`DFS` to override.

---

## Runtime formulas

Computed per-request against the retrieved subgraph. **Nothing derived is stored
in Neo4j.**

```
NormalizedTime           = edge_time / max_subgraph_edge_time
NormalizedCognitiveEffort = edge_effort / 5.0
EdgeCost                 = (NormalizedTime + NormalizedCognitiveEffort) / 2.0
LearningValue            = (target_relevance + downstream_utility) / 2.0
```

---

## API

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/path/optimize` | Full pipeline, single solver |
| POST | `/api/path/compare` | All three solvers on one subgraph |
| GET | `/api/solvers` | Solver catalogue + active ILP backend |
| GET | `/api/traversal/preview` | AUTO heuristic dry-run |
| POST/GET/PATCH/DELETE | `/nodes`, `/relationships` | CRUD |
| GET | `/graph`, `/validate`, `/stats` | Inspection |
| POST | `/reset` | Clear database |

Interactive docs: http://localhost:8000/docs

---

## Verification

```bash
cd backend
test/Scripts/python.exe -m scripts.preflight        # env + Neo4j connectivity
test/Scripts/python.exe -m scripts.seed_physics --reset   # 100-node Physics KG
test/Scripts/python.exe -m scripts.seed_physics --optimize --target q_field
test/Scripts/python.exe -m scripts.check_solvers   # ILP >= DP >= Greedy audit
test/Scripts/python.exe -m scripts.check_cycles    # prerequisite cycle report
test/Scripts/python.exe -m scripts.verify_pipeline # algorithms, 70+ checks
test/Scripts/python.exe -m scripts.verify_api      # routes + schemas
```

`verify_pipeline` covers cycle detection, the AUTO heuristic, every cost
formula, solver ordering, budget enforcement, constraint toggles and
topological ordering — without needing Neo4j.

---

## Physics graph

`scripts/seed_physics.py` builds a 100-node, 146-edge Physics curriculum:

| Branch | Topics |
|--------|--------|
| Mathematics | 10 (algebra → optimisation theory) |
| Mechanics | 12 (kinematics → continuum) |
| Electromagnetism | 11 (electrostatics → microwaves) |
| Optics | 7 |
| Thermodynamics | 8 |
| Quantum | 10 (photoelectric → QFT) |
| Relativity | 4 |
| Nuclear | 6 |
| Astrophysics | 12 |
| Condensed matter | 8 |
| Plasma | 3 |
| Computational | 4 |
| Field theory | 4 |

Within a branch the spine is HARD; cross-branch links are mostly SOFT (helpful
background rather than mandatory). That balance is deliberate — making every
cross-link HARD would put the whole graph in the mandatory closure and all three
solvers would return the same plan, leaving nothing to optimise.

---

## Layout

```
backend/
  app/
    schemas.py             enums + request/response models
    database.py            Neo4j async driver
    graph_service.py       load → NetworkX, validation, AUTO traversal
    cost_engine.py         runtime metrics, scoring, feasibility
    optimization_service.py pipeline orchestration + comparison
    optimizers/
      base.py              shared timing / metrics / sequence
      greedy.py            frontier + lookahead
      dp.py                Pareto-frontier DP
      ilp.py               MILP with pluggable backend
    main.py                FastAPI routes
    crud.py, models.py, validation.py, topological_sort.py   (legacy CRUD layer)
  scripts/                 verification + demo seeding
frontend/src/
  app/                     layout, page, global styles
  components/
    Toolbar.tsx            method / optimizer / compare
    panels/LeftPanel.tsx   CRUD + calculations
    panels/RightPanel.tsx  traversal + algorithm explanation
    graph/GraphView.tsx    React Flow canvas
    compare/CompareModal.tsx  side-by-side solver table
  store/pipelineStore.ts   Zustand state
  lib/api.ts, pipelineTypes.ts, utils.ts
```

---

## ILP backend

The MILP is declared once as backend-neutral linear data and dispatched to
whichever solver is installed:

1. **PuLP** with a CBC/HiGHS binary (preferred)
2. **`scipy.optimize.milp`** — HiGHS in-process (always available)

A single formulation serves both, so the backends cannot drift apart. Check the
active backend with `GET /api/solvers`.
