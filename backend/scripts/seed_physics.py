"""
Seed a 100-node Physics knowledge graph into Neo4j.

Structured as a realistic STEM curriculum DAG: 10 branches, each layered
intro -> intermediate -> advanced, with cross-links between related areas.
Gives ~79 nodes and ~150 prerequisite edges for testing traversal + solvers.

Usage:
    test/Scripts/python.exe -m scripts.seed_physics --reset
    test/Scripts/python.exe -m scripts.seed_physics --reset --optimize
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import clear_database, close_driver, init_database, verify_connectivity
from app.models import NodeCreate, RelationshipCreate

# (slug, name, description, target_relevance, downstream_utility)
# Relevance/utility are low at the roots and rise toward the frontier, so an
# optimizer aimed at an advanced topic has real decisions to make.
BRANCHES: dict[str, list[tuple[str, str, str, float, float]]] = {
    "math": [
        ("math_alg", "Algebra", "Rearranging equations, functions, polynomials", 0.10, 0.98),
        ("math_trig", "Trigonometry", "Sin, cos, tan and the unit circle", 0.14, 0.95),
        ("math_calc1", "Calculus I", "Limits, derivatives, integrals", 0.22, 0.95),
        ("math_linalg", "Linear Algebra", "Vectors, matrices, eigenvalues", 0.30, 0.92),
        ("math_calc2", "Calculus II", "Multivariable integrals", 0.38, 0.85),
        ("math_ode", "Ordinary Differential Equations", "dy/dx and motion equations", 0.48, 0.82),
        ("math_pde", "Partial Differential Equations", "Wave and field equations", 0.60, 0.72),
        ("math_fourier", "Fourier Analysis", "Decomposition into frequencies", 0.66, 0.70),
        ("math_prob", "Probability Theory", "Axioms, distributions, expectation", 0.58, 0.86),
        ("math_opt", "Optimization Theory", "Convexity, Lagrange multipliers", 0.72, 0.78),
    ],
    "mech": [
        ("mech_units", "Units and Dimensions", "SI units, dimensional analysis", 0.10, 0.92),
        ("mech_kin1", "Kinematics", "Position, velocity, acceleration", 0.16, 0.94),
        ("mech_newton", "Newtonian Mechanics", "Forces, free body diagrams", 0.26, 0.95),
        ("mech_energy", "Work and Energy", "Work, kinetic and potential energy", 0.34, 0.90),
        ("mech_mom", "Momentum and Collisions", "Conservation laws", 0.42, 0.86),
        ("mech_rot", "Rotational Dynamics", "Torque, angular momentum, rolling", 0.52, 0.84),
        ("mech_rigid", "Rigid Body Dynamics", "Inertia tensor, precession", 0.62, 0.76),
        ("mech_osc", "Oscillations", "Simple harmonic motion, pendulums, waves", 0.60, 0.82),
        ("mech_chaos", "Chaos and Nonlinear Dynamics", "Bifurcation, attractors, sensitivity", 0.74, 0.66),
        ("mech_fluids", "Fluid Mechanics", "Pressure, viscosity, Bernoulli", 0.58, 0.70),
        ("mech_cont", "Continuum Mechanics", "Stress, strain, elasticity", 0.68, 0.68),
        ("mech_grav", "Gravitation", "Newtonian gravity, orbits, tides", 0.55, 0.76),
    ],
    "em": [
        ("em_charge", "Electrostatics", "Coulomb's law, electric fields, potential", 0.22, 0.94),
        ("em_gauss", "Gauss's Law", "Field symmetry and flux", 0.32, 0.86),
        ("em_cap", "Capacitance", "Capacitors, dielectrics, energy storage", 0.40, 0.84),
        ("em_current", "Electric Current", "Resistance, Ohm's law, circuits", 0.44, 0.88),
        ("em_magnet", "Magnetism", "Magnetic fields, Lorentz force", 0.50, 0.90),
        ("em_induct", "Electromagnetic Induction", "Faraday's and Lenz's laws", 0.60, 0.84),
        ("em_trans", "Transmission Lines", "Impedance, reflection, waveguides", 0.66, 0.72),
        ("em_maxwell", "Maxwell's Equations", "Unified electromagnetism", 0.70, 0.86),
        ("em_waves", "Electromagnetic Waves", "Polarisation, reflection, refraction", 0.68, 0.76),
        ("em_antenna", "Antennas and Radio", "Radiation patterns, propagation", 0.70, 0.64),
        ("em_micro", "Microwave Engineering", "Waveguides, cavities, radar", 0.72, 0.60),
    ],
    "optics": [
        ("opt_geom", "Geometric Optics", "Reflection, refraction, lenses, mirrors", 0.26, 0.88),
        ("opt_interf", "Interference", "Young's double slit, coherence", 0.48, 0.82),
        ("opt_diffr", "Diffraction", "Single slit, gratings, resolution", 0.54, 0.80),
        ("opt_imaging", "Optical Imaging", "Aberrations, microscopy, resolution limits", 0.60, 0.72),
        ("opt_modern", "Modern Optics", "Fibre optics, polarisation, nonlinear optics", 0.62, 0.68),
        ("opt_laser", "Laser Physics", "Population inversion, gain, modes", 0.68, 0.66),
        ("opt_instr", "Optical Instruments", "Telescopes, spectrographs, detectors", 0.70, 0.62),
    ],
    "thermo": [
        ("th_temp", "Temperature and Heat", "Thermal equilibrium, thermometers", 0.18, 0.92),
        ("th_kin", "Kinetic Theory", "Molecular motion, ideal gas law", 0.28, 0.88),
        ("th_first", "First Law", "Energy conservation in gases", 0.36, 0.86),
        ("th_second", "Second Law", "Entropy, heat engines", 0.48, 0.82),
        ("th_cycles", "Thermodynamic Cycles", "Carnot, efficiency, power plants", 0.56, 0.70),
        ("th_phase", "Phase Transitions", "Order parameter, critical exponents", 0.66, 0.76),
        ("th_stat", "Statistical Mechanics", "Ensembles, partition functions", 0.70, 0.78),
        ("th_noneq", "Non-Equilibrium Thermodynamics", "Fluctuation theorems, transport", 0.78, 0.66),
    ],
    "quantum": [
        ("q_photo", "Photoelectric Effect", "Photons and quantised light", 0.34, 0.90),
        ("q_wavefn", "Wave Function", "Superposition and probability", 0.46, 0.92),
        ("q_schrod", "Schrodinger Equation", "Stationary states, hydrogen", 0.56, 0.90),
        ("q_ops", "Quantum Mechanics Operators", "Observables, commutators, uncertainty", 0.66, 0.84),
        ("q_spin", "Spin", "Angular momentum, Pauli exclusion", 0.70, 0.80),
        ("q_many", "Many-Body Quantum Physics", "Correlations, entanglement structure", 0.80, 0.76),
        ("q_decoh", "Quantum Decoherence", "Open systems, environmental coupling", 0.82, 0.68),
        ("q_rel", "Quantum Relativity", "Dirac equation and spinors", 0.82, 0.70),
        ("q_info", "Quantum Information", "Qubits, gates, error correction", 0.78, 0.70),
        ("q_field", "Quantum Field Theory", "Fields, quantisation, Feynman diagrams", 0.94, 0.55),
    ],
    "rel": [
        ("rel_sr", "Special Relativity", "Lorentz transforms, time dilation", 0.56, 0.88),
        ("rel_mass", "Relativistic Momentum", "E equals mc squared, relativistic energy", 0.68, 0.84),
        ("rel_gen", "General Relativity", "Equivalence principle, spacetime curvature", 0.88, 0.72),
        ("rel_gw", "Gravitational Waves", "Ripples in spacetime, LIGO", 0.96, 0.45),
    ],
    "nuclear": [
        ("nuc_radio", "Radioactivity", "Decay modes, half-life", 0.38, 0.88),
        ("nuc_react", "Nuclear Reactor Physics", "Neutron moderation, criticality", 0.58, 0.76),
        ("nuc_fission", "Nuclear Fission", "Chain reactions, reactors", 0.52, 0.80),
        ("nuc_fusion", "Nuclear Fusion", "Stars, tokamaks, hydrogen bomb", 0.58, 0.78),
        ("nuc_accel", "Particle Accelerators", "Synchrotrons, colliders, luminosity", 0.78, 0.72),
        ("nuc_particle", "Particle Physics", "Standard Model, quarks, bosons", 0.80, 0.72),
    ],
    "astro": [
        ("astro_obs", "Astronomical Observation", "Telescopes, spectra, magnitude", 0.20, 0.90),
        ("astro_star", "Stellar Structure", "Hydrostatic equilibrium, fusion", 0.44, 0.82),
        ("astro_form", "Star Formation", "Molecular clouds, collapse, protostars", 0.52, 0.80),
        ("astro_evo", "Stellar Evolution", "Lifecycle, supernovae, remnants", 0.58, 0.76),
        ("astro_gal", "Galaxies", "Formation, spiral structure, dark matter", 0.74, 0.74),
        ("astro_galdyn", "Galactic Dynamics", "Orbits, clusters, dark matter halos", 0.80, 0.70),
        ("astro_bh", "Black Holes", "Event horizons, accretion, Hawking radiation", 0.86, 0.70),
        ("astro_exo", "Exoplanet Detection", "Radial velocity, transit methods", 0.72, 0.68),
        ("astro_solar", "Solar System Physics", "Orbits, tides, planetary dynamics", 0.58, 0.72),
        ("astro_cosmo", "Cosmology", "Big Bang, expansion, CMB", 0.86, 0.70),
        ("astro_td", "Time Domain Astronomy", "Transients, pulsars, supernovae", 0.82, 0.66),
        ("astro_multi", "Multi-Messenger Astronomy", "Neutrinos, GWs, cosmic rays", 0.92, 0.58),
        ("astro_pert", "Cosmological Perturbations", "Power spectrum, inflation", 0.94, 0.52),
    ],
    "matter": [
        ("mat_crystal", "Crystal Structure", "Lattices, Bravais, Miller indices", 0.34, 0.84),
        ("mat_band", "Band Theory", "Semiconductors, insulators, metals", 0.56, 0.86),
        ("mat_mag", "Magnetism in Solids", "Exchange interaction, spin waves", 0.68, 0.78),
        ("mat_super", "Superconductivity", "BCS, critical temperature", 0.72, 0.76),
        ("mat_topo", "Topological Materials", "Topological insulators, Weyl semimetals", 0.84, 0.68),
        ("mat_soft", "Polymers and Soft Matter", "Entanglement, elasticity, rheology", 0.62, 0.66),
        ("mat_superfluid", "Superfluids", "Bose condensation, vortices in helium", 0.76, 0.72),
        ("mat_condense", "Condensed Matter Physics", "Phases, order, many-body systems", 0.82, 0.72),
    ],
    "plasma": [
        ("pl_intro", "Plasma Physics", "Debye shielding, plasmas, collective effects", 0.58, 0.80),
        ("pl_mhd", "Magnetohydrodynamics", "Frozen-in fields, Alfven waves", 0.72, 0.74),
        ("pl_diag", "Plasma Diagnostics", "Langmuir probes, interferometry", 0.78, 0.66),
    ],
    "comp": [
        ("comp_num", "Numerical Methods", "Root finding, quadrature, ODE integrators", 0.30, 0.92),
        ("comp_mc", "Monte Carlo Methods", "Stochastic sampling, importance sampling", 0.52, 0.84),
        ("comp_phys", "Computational Physics", "Simulation, finite difference, FEM", 0.68, 0.78),
        ("comp_ml", "Machine Learning for Physics", "Neural surrogates, inference", 0.76, 0.68),
    ],
    "theory": [
        ("th_eft", "Effective Field Theory", "Renormalisation group, matching", 0.84, 0.72),
        ("th_gauge", "Gauge Theory", "Symmetry, connections, non-Abelian groups", 0.90, 0.64),
        ("th_susy", "Supersymmetry", "Supercharges, the hierarchy problem", 0.95, 0.50),
        ("th_string", "String Theory", "Vibrational modes, dualities", 0.98, 0.42),
    ],
}

# Cross-links between branches.
#
# Within a branch the spine is HARD, so reaching a topic requires everything
# below it on that branch. Cross-branch links represent *background you would
# find helpful* rather than something that is strictly mandatory, so they are
# mostly SOFT. Keeping them SOFT is what gives the optimizer a real decision to
# make; if every cross-link were HARD the HARD closure would swallow the whole
# graph and all three solvers would be forced to return the same plan.
CROSS_EDGES: list[tuple[str, str, str]] = [
    # mathematics underpinning physical branches
    ("math_trig", "mech_osc", "SOFT"),
    ("math_alg", "em_charge", "HARD"),
    ("math_calc1", "em_gauss", "SOFT"),
    ("math_linalg", "q_ops", "HARD"),
    ("math_linalg", "em_current", "SOFT"),
    ("math_ode", "mech_osc", "SOFT"),
    ("math_ode", "em_induct", "SOFT"),
    ("math_pde", "th_stat", "SOFT"),
    ("math_fourier", "opt_diffr", "SOFT"),
    ("math_fourier", "em_waves", "SOFT"),
    ("math_calc2", "th_stat", "SOFT"),
    ("math_pde", "q_schrod", "SOFT"),
    ("math_prob", "q_wavefn", "SOFT"),
    ("math_prob", "th_kin", "SOFT"),
    ("math_opt", "q_many", "SOFT"),

    # physics feeding physics
    ("em_waves", "opt_geom", "SOFT"),
    ("em_maxwell", "opt_interf", "SOFT"),
    ("mech_osc", "em_waves", "SOFT"),
    ("mech_osc", "opt_interf", "SOFT"),
    ("th_first", "mech_energy", "SOFT"),
    ("th_second", "mech_grav", "SOFT"),
    ("th_cycles", "nuc_fission", "SOFT"),
    ("th_stat", "q_spin", "SOFT"),
    ("th_stat", "mat_band", "SOFT"),
    ("q_schrod", "nuc_radio", "SOFT"),
    ("q_ops", "rel_sr", "HARD"),
    ("rel_sr", "q_rel", "HARD"),
    ("rel_mass", "nuc_particle", "SOFT"),
    ("rel_gen", "astro_cosmo", "SOFT"),
    ("mech_grav", "rel_gen", "SOFT"),
    ("mech_grav", "astro_star", "SOFT"),
    ("mech_grav", "astro_solar", "SOFT"),
    ("astro_star", "nuc_fusion", "SOFT"),
    ("nuc_radio", "astro_evo", "SOFT"),
    ("mat_band", "q_field", "SOFT"),
    ("mat_band", "opt_modern", "SOFT"),
    ("mat_super", "mat_condense", "HARD"),
    ("nuc_fission", "th_stat", "OPTIONAL"),
    ("nuc_particle", "q_field", "SOFT"),
    ("rel_gw", "astro_cosmo", "SOFT"),
    ("astro_gal", "astro_cosmo", "HARD"),
    ("astro_evo", "astro_gal", "HARD"),
    ("astro_form", "astro_bh", "SOFT"),
    ("opt_interf", "astro_obs", "OPTIONAL"),
    ("opt_laser", "astro_td", "SOFT"),
    ("astro_td", "astro_multi", "SOFT"),
    ("th_temp", "astro_obs", "OPTIONAL"),
    ("em_magnet", "em_induct", "HARD"),

    # computational and theory branches
    ("comp_num", "math_ode", "SOFT"),
    ("comp_num", "math_pde", "SOFT"),
    ("comp_mc", "th_stat", "SOFT"),
    ("comp_ml", "q_many", "SOFT"),
    ("comp_phys", "mech_cont", "SOFT"),
    ("comp_phys", "em_trans", "SOFT"),
    ("q_field", "th_gauge", "HARD"),
    ("th_eft", "th_gauge", "HARD"),
    ("th_gauge", "th_susy", "HARD"),
    ("th_susy", "th_string", "HARD"),
    ("mat_topo", "th_gauge", "OPTIONAL"),
    ("pl_intro", "mech_fluids", "SOFT"),
    ("pl_intro", "em_waves", "SOFT"),
    ("pl_mhd", "mech_grav", "OPTIONAL"),
    ("pl_diag", "nuc_fusion", "SOFT"),
    ("mech_cont", "mat_soft", "SOFT"),
]

# PART_OF edges carry no constraint; they exercise that relationship type.
PART_OF_EDGES: list[tuple[str, str]] = [
    ("mech_kin1", "mech_newton"),
    ("mech_units", "mech_kin1"),
    ("em_charge", "em_gauss"),
    ("q_wavefn", "q_schrod"),
    ("astro_star", "astro_evo"),
    ("mat_crystal", "mat_band"),
]

# Branch position -> depth within that branch, used to scale time and effort.
DEPTH: dict[str, int] = {}
for _topics in BRANCHES.values():
    for _i, _entry in enumerate(_topics):
        DEPTH[_entry[0]] = _i


def build_records() -> tuple[list[dict], list[dict]]:
    nodes: list[dict] = []
    for topics in BRANCHES.values():
        for slug, name, desc, relevance, utility in topics:
            nodes.append(
                {
                    "id": slug,
                    "name": name,
                    "description": desc,
                    "target_relevance": relevance,
                    "downstream_utility": utility,
                }
            )

    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(source: str, target: str, rel_type: str, prereq_type: str | None) -> None:
        key = (source, target)
        if key in seen or source == target:
            return
        seen.add(key)
        depth = DEPTH.get(target, 2)
        edges.append(
            {
                "id": f"{source}__{target}",
                "source": source,
                "target": target,
                "type": rel_type,
                "prerequisite_type": prereq_type,
                "time_required_minutes": 25 + depth * 12,
                "cognitive_effort": min(5, 1 + depth // 2),
            }
        )

    # Every branch becomes a HARD chain: topic i -> topic i+1.
    for topics in BRANCHES.values():
        for i in range(len(topics) - 1):
            add(topics[i][0], topics[i + 1][0], "PREREQUISITE_OF", "HARD")

    for source, target, prereq_type in CROSS_EDGES:
        add(source, target, "PREREQUISITE_OF", prereq_type)

    for source, target in PART_OF_EDGES:
        add(source, target, "PART_OF", None)

    return nodes, edges


async def seed(reset: bool, demo_only: bool = False) -> bool:
    if not await verify_connectivity():
        print("[ERROR] Neo4j is not reachable on bolt://localhost:7687")
        return False

    await init_database()

    from app.crud import create_node, create_relationship, get_all_nodes

    if reset:
        await clear_database()
        print("Cleared existing data.")
    elif await get_all_nodes():
        if not demo_only:
            print("Database already has data. Re-run with --reset to reseed.")
            return False
        print("Using existing data (nothing written).")
        return True

    nodes, edges = build_records()

    for node in nodes:
        await create_node(NodeCreate(**node))
    print(f"Created {len(nodes)} nodes.")

    created = skipped = 0
    for edge in edges:
        try:
            await create_relationship(RelationshipCreate(**edge))
            created += 1
        except ValueError as exc:
            skipped += 1
            print(f"  skipped {edge['id']}: {exc}")
    print(f"Created {created} relationships ({skipped} skipped).")

    breakdown: dict[str, int] = {}
    for edge in edges:
        label = edge["prerequisite_type"] or edge["type"]
        breakdown[label] = breakdown.get(label, 0) + 1
    print(f"  breakdown: {breakdown}")
    return True


async def run_demo(target: str) -> None:
    from app.optimization_service import PipelineError, compare_solvers
    from app.schemas import ConstraintConfig, PathCompareRequest

    print("\n" + "=" * 78)
    print(f"PHYSICS KG PIPELINE -> target '{target}'")
    print("=" * 78)

    try:
        result = await compare_solvers(
            PathCompareRequest(
                target_node_id=target,
                search_method="AUTO",
                constraints=ConstraintConfig(),
                traversal={"max_subgraph_nodes": 60},
            )
        )
    except PipelineError as exc:
        print(f"pipeline error: {exc.message}")
        return

    traversal = result.traversal
    comparison = result.comparison

    print(f"AUTO chose {traversal.selected.value}: {traversal.reason}\n")
    size = comparison.subgraph_size
    print(
        f"search-space reduction: {size['full_graph_nodes']} nodes "
        f"-> {size['retrieved_nodes']} nodes "
        f"({round(size['reduction_ratio'] * 100)}% pruned)\n"
    )

    header = f"{'Solver':<28} {'ROI':>8} {'Utility':>9} {'Cost':>8} {'Time':>7} {'ms':>9}  OK"
    print(header)
    print("-" * 76)
    for r in comparison.results:
        print(
            f"{r.display_name:<28} {r.path_score:>8.4f} {r.net_utility:>9.4f} "
            f"{r.total_path_cost:>8.4f} {r.total_time_minutes:>5}m "
            f"{r.execution_time_ms:>9.1f}  {'Y' if r.is_feasible else 'N'}"
        )

    print(f"\nBEST: {comparison.best_solver.value}")
    print(f"{comparison.recommendation}\n")

    sequence = result.learning_sequences.get(comparison.best_solver.value, [])
    print(f"Learning sequence ({len(sequence)} steps):")
    for step in sequence:
        lock = " [HARD]" if step["is_hard_prerequisite"] else ""
        print(f"  {step['step']:>2}. {step['name']}{lock}  ~{step['estimated_time_minutes']}m")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="wipe existing data first")
    parser.add_argument("--target", default="q_field", help="target node id")
    parser.add_argument("--optimize", action="store_true", help="run the pipeline after seeding")
    args = parser.parse_args()

    if await seed(args.reset, demo_only=args.optimize and not args.reset) and args.optimize:
        await run_demo(args.target)

    await close_driver()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
