# PROMPT — Optimized Learning-Path Engine over a Knowledge Graph

> Reference specification for this project. This document is the complete,
> corrected build brief — it supersedes the original prompt and folds in every
> design decision and bug fix discovered during implementation.

**Role:** Principal Full-Stack Software Engineer & Graph Algorithm Specialist.

**Objective:** Build an optimized learning-path engine over a manually defined
Knowledge Graph. One unified, scalable architecture that behaves identically at
10 nodes and 1000+ nodes.

---

## 0. Non-Negotiable Engineering Rules

These exist because violating them silently produced wrong answers during
development.

**R1 — Never hand-roll graph algorithms.** Use NetworkX for traversal, cycle
detection, DAG checks, and topological sort. A custom ordering bug was masked by
a fallback so thoroughly that the tests passed while the algorithm never ran.

**R2 — Never write a fallback that hides an empty result.** "Return the
mandatory closure if nothing found" made a completely broken DP pass every test
on small graphs. If a solver produces nothing, surface it as a bug.

**R3 — Derived values are never persisted.** All costs, normalizations, and
scores are computed per-request against the retrieved subgraph.

**R4 — Verify at scale.** A bug-free 8-node fixture is not evidence. Test at
100+ nodes with branching, shared ancestors, and mixed HARD/SOFT/OPTIONAL.
Report each solver's actual optimality honestly.

**R5 — Always start the server with the venv interpreter.** Use
`test\Scripts\python.exe`, never bare `python`.

---

## 1. System Architecture & Pipeline

```
FULL KG
  → Global Graph Validation            (NetworkX: DAG check, cycles, dup IDs, self-loops)
  → Target Selection
  → Reverse Traversal                  (AUTO | BFS | DFS) → ancestor subgraph
  → Target-Specific Constraints        (HARD / SOFT / OPTIONAL)
  → Relevant DAG Construction
  → Runtime Normalization & Cost Calc  (never written to Neo4j)
  → Optimization                       (Greedy | DP | ILP)
  → Best Valid Plan
  → Topological Sort                   (NetworkX Kahn)
  → Final Path + Visual Explanation
```

**Key Principle:** Reverse traversal is the scalability hinge. At 10 nodes it
returns the whole graph — fine. At 1000+ nodes it collapses the search space to
the target's relevant ancestors (~30–60 nodes) before any optimization runs.

---

## 2. Tech Stack

| Layer | Choice |
|-------|--------|
| Frontend | Next.js 14 (TypeScript), Tailwind CSS |
| Backend | FastAPI (Python 3.10+) |
| Database | Neo4j via `neo4j-python-driver` (async), local `bolt://localhost:7687` |
| Graph algorithms | **NetworkX** (required — see R1) |
| Optimization | **PuLP** (CBC/HiGHS) with **`scipy.optimize.milp`** fallback |
| Visualization | React Flow |
| Python env | venv named `test` |

---

## 3. Manual Input Model (no LLM generation)

All data is entered manually through UI forms.

### Node

```json
{
  "id": "string",
  "name": "string",
  "description": "string",
  "target_relevance": 0.0,
  "downstream_utility": 0.0
}
```

### Relationship

```json
{
  "id": "string",
  "source": "node_id",
  "target": "node_id",
  "type": "PART_OF | PREREQUISITE_OF",
  "prerequisite_type": "HARD | SOFT | OPTIONAL | null",
  "time_required_minutes": 20,
  "cognitive_effort": 3
}
```

### Rules

- `time_required_minutes` and `cognitive_effort` exist on **both** relationship
  types.
- `prerequisite_type` applies **only** when `type == PREREQUISITE_OF`; must be
  `null` for `PART_OF`.
- No self-loops. Unique IDs enforced by database constraints.
- Derived values (`normalized_time`, `normalized_cognitive_effort`, `EdgeCost`,
  `PathScore`) are **never** written to Neo4j.

---

## 4. Runtime Calculations

Computed per request against the retrieved subgraph:

```
NormalizedTime           = edge_time / max(edge_time in subgraph)
NormalizedCognitiveEffort = edge_effort / 5.0
EdgeCost                 = (NormalizedTime + NormalizedCognitiveEffort) / 2.0
LearningValue            = (target_relevance + downstream_utility) / 2.0
```

---

## 5. Objective Function — Read Carefully

The specified reporting metric is:

```
PathScore = AverageLearningValue / (TotalPathCost + 0.01)
```

> **This is a REPORTING / RANKING metric. It must NOT be the optimization
> objective.**

`PathScore` is strictly **decreasing in cost** for fixed value. Maximizing it
directly is degenerate — the optimum is always "select nothing" (zero cost ⇒
maximal ratio). A Dinkelbach linearization was implemented and then removed for
exactly this reason.

Use instead, as the selection objective:

```
NetUtility = Σ LearningValue(v) − Σ EdgeCost(e) − skipPenalties
```

`NetUtility` is additive and linear, and cannot be gamed.

Report **both**: solvers maximize `NetUtility`; the UI ranks and displays
`PathScore`.

### 5.1 Support Constraint (mandatory)

Edge cost only accrues when **both** endpoints are selected. A node whose
dependents are all skipped therefore collects full learning value at zero cost.
Without a guard, every solver attaches unrelated branches purely to harvest that
free value.

> Require: **every selected non-target node must have at least one selected
> dependent.**

- **DP / Greedy:** a branch is added only if its *marginal* `NetUtility` gain
  against the complete current plan is positive.
- **ILP:** `x_v ≤ Σ y_e` over outgoing edges.

### 5.2 Constraint Semantics

| Type | Meaning |
|------|---------|
| `HARD` | Mandatory. Transitive closure always selected. Cannot be skipped. |
| `SOFT` | Skippable at a `soft_skip_penalty` (default `0.15`), charged **only when the target is selected and the source is not**. Disabled entirely when `include_soft=false`. |
| `OPTIONAL` | Free to skip, no penalty. |

---

## 6. AUTO Traversal

`search_method ∈ {"AUTO", "BFS", "DFS"}`

When `AUTO`, measure the target's ancestor region and choose:

- **shallow + broad** → BFS (surface all alternative branches before committing)
- **deep + narrow** → DFS (follow the chain, skip irrelevant siblings)

Return the decision **and its rationale + metrics** so the UI can explain itself.
Pinning BFS/DFS must override.

---

## 7. Three Parallel Solvers

`POST /api/path/compare` traverses **once**, then runs all three over the
**identical subgraph** so the comparison isolates the algorithm, not the input.

| Solver | Optimality | Approach |
|--------|-----------|----------|
| Greedy Frontier | approximate | Local utility with N-step lookahead |
| Dynamic Programming | heuristic (exact per-node subproblem) | Forward topological DP |
| Integer Linear Programming | **global (exact)** | Flow-conservation MILP |

**Enforced invariant:** `ILP ≥ DP ≥ Greedy` on `NetUtility`. The exact solver
must never be beaten.

### 7.1 DP — Required Properties

- Iterate **forward** topological order (parents first). Iterating in reverse
  silently yields empty states.
- The objective is linear ⇒ keep **one best `(value − cost)` state per node**. A
  Pareto frontier is a ratio-objective tool, and its cross-product **does not
  terminate** at 60 nodes.
- Assembly: mandatory HARD core first, then optional branches by **marginal**
  gain with a fixpoint loop. Do not test branches in isolation (shared
  ancestors) or against a partial set (unpaid ancestor costs).

### 7.2 ILP — Required Formulation

Variables: `x_v ∈ {0,1}`, `y_e ∈ {0,1}`

**Edge = AND of its endpoints.** Encode exactly:

```
y_e ≤ x_source
y_e ≤ x_target
y_e ≥ x_source + x_target − 1
```

Leaving `y_e` free for SOFT/OPTIONAL edges lets the model select both endpoints
and pay **no** edge cost, while `NetUtility` charges it in full — the ILP then
optimizes a strictly cheaper problem than its own metric, and can return plans
that score *worse* than DP's.

Consequences that must hold:

- HARD parent forced on: `x_target=1 ⇒ y_e ≥ x_source ∧ y_e ≤ x_source ⇒ y_e=x_source=1`
- "Skipped" ⇔ target selected ∧ source not ⇒ penalty `penalty·(x_target − y_e)`
  is exact and linear
- SOFT penalty lives in coefficients: node `−penalty` (if it has a SOFT parent),
  soft edge `+penalty`

Other constraints: support (`x_v ≤ Σ y_out`), time budget
(`Σ y_e·time_e ≤ budget`), target forced on.

> **Do NOT** use `Σ y_in == x_v` — it forces traversing every parent edge
> including detours, and goes infeasible.
>
> **Do NOT** use `x_v ≤ Σ y_in` — it pins root concepts to 0, making HARD
> closure unsatisfiable.

**Backend dispatch:** declare the model once as backend-neutral linear data,
then dispatch to PuLP (if a CBC/HiGHS binary exists) else `scipy.optimize.milp`.
One formulation, two backends — they must not drift.

---

## 8. API

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/path/optimize` | Full pipeline, single solver |
| `POST` | `/api/path/compare` | All three solvers, one subgraph |
| `GET` | `/api/solvers` | Catalogue + active ILP backend |
| `GET` | `/api/traversal/preview` | AUTO heuristic dry-run |
| `*CRUD*` | `/nodes`, `/relationships` | Manual data entry |
| `GET` | `/graph`, `/validate`, `/stats` | Inspection |
| `POST` | `/reset` | Clear database |

Each solver result must expose: selected path, total path cost, average learning
value, PathScore, total time, feasibility + reason, execution time, net
utility. Comparison must include a written recommendation explaining the winner
and why.

---

## 9. UI & Visualization

- **Layout:** Top Toolbar (CRUD + Method/AUTO + Optimizer + Compare), Left Panel
  (calculations & metrics), Center (React Flow), Right Panel (traversal &
  algorithm explanation).
- **Clean canvas:** Node shows only `Name`; edge shows only `Relationship Type`.
  All other metadata (time, effort, cost, relevance) appears in a side
  panel/drawer on click.
- **Comparison modal:** side-by-side table; highest PathScore highlighted green;
  narrative summary of the winner.
- **Highlighting:** optimal-path nodes/edges in green; HARD prerequisites in red.
- **Dropdowns must use `z-50`** over a `z-40` backdrop.
- **CORS:** allow **any loopback port** via regex — Next.js silently falls back
  to 3001 when 3000 is busy, and a pinned origin list breaks the app at that
  moment.

---

## 10. Seed Data & Verification

Provide:

- `scripts/seed_physics.py` — 100-node / 146-edge Physics curriculum, ~13
  branches. Within-branch spine HARD; cross-branch links mostly SOFT (making
  them all HARD would force the whole graph into the mandatory closure, leaving
  nothing to optimize).
- `scripts/preflight.py` — detects wrong interpreter, missing packages, Neo4j
  connectivity.
- `scripts/verify_pipeline.py` — algorithms, no DB required.
- `scripts/verify_api.py` — routes + schemas.
- `scripts/check_solvers.py` — audits `ILP ≥ DP ≥ Greedy` across many targets.

---

## 11. Delivery

- Modular, production-ready code, commented with **why** non-obvious choices were
  made.
- `requirements.txt`, `.env.example`, and a `.gitignore` that **excludes the
  venv, `node_modules`, `.next`, and `.env`**.
- README with exact startup commands, always using the venv interpreter.
- One-command startup script that runs preflight, seeds, and launches both
  services.

---

## Appendix — What Changed vs the Original Prompt

| Original | Now | Reason |
|----------|-----|--------|
| PathScore as the optimization goal | NetUtility optimizes; PathScore reports | The ratio always prefers the empty path |
| One DP optimizer | Greedy + DP + ILP, compared | Shows *which* algorithm wins, not just that one ran |
| BFS/DFS only | + AUTO with rationale | Removes a manual choice the system can make |
| DP = "globally optimal" | DP = heuristic, ILP = exact | DP's assembly is a marginal-gain pass; honest labeling only |
| No anti-degeneracy rules | R1, R2, R4 + support constraint | Each one guards a bug that actually shipped |
| No scale test | 100-node seed is mandatory | Small fixtures hid a completely broken DP |
| Fixed CORS origins | Loopback regex | Port fallback silently broke the app |
