"""
Solver registry for the Learning Path Engine.

Three independent solvers, one shared problem instance:

    GreedyFrontierSolver    fast, local approximation with N-step lookahead
    DynamicProgrammingSolver global Pareto-frontier DP over the DAG
    ILPSolver               Dinkelbach-linearised MILP via PuLP/CBC
"""

from app.optimizers.base import BaseSolver, learning_sequence
from app.optimizers.dp import DynamicProgrammingSolver
from app.optimizers.greedy import GreedyFrontierSolver
from app.optimizers.ilp import ILPSolver
from app.schemas import SolverAlgorithm

__all__ = [
    "BaseSolver",
    "DynamicProgrammingSolver",
    "GreedyFrontierSolver",
    "ILPSolver",
    "learning_sequence",
    "get_solver",
    "default_solvers",
    "ALL_SOLVERS",
]


_REGISTRY: Dict[SolverAlgorithm, BaseSolver] = {
    SolverAlgorithm.GREEDY_FRONTIER: GreedyFrontierSolver(),
    SolverAlgorithm.DYNAMIC_PROGRAMMING: DynamicProgrammingSolver(),
    SolverAlgorithm.INTEGER_LINEAR_PROGRAMMING: ILPSolver(),
}

ALL_SOLVERS: list[SolverAlgorithm] = [
    SolverAlgorithm.GREEDY_FRONTIER,
    SolverAlgorithm.DYNAMIC_PROGRAMMING,
    SolverAlgorithm.INTEGER_LINEAR_PROGRAMMING,
]


def get_solver(algorithm: SolverAlgorithm) -> BaseSolver:
    solver = _REGISTRY.get(algorithm)
    if solver is None:
        raise ValueError(f"Unknown solver: {algorithm}")
    return solver


def default_solvers() -> list[BaseSolver]:
    """All three solvers, ordered cheapest-first for narrative output."""
    return [_REGISTRY[algorithm] for algorithm in ALL_SOLVERS]
