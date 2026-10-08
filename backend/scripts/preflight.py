"""
Preflight environment check.

Run this first if the server fails to start, or to confirm the virtual
environment has every dependency:

    test/Scripts/python.exe -m scripts.preflight
"""

from __future__ import annotations

import sys
from pathlib import Path

REQUIRED = [
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("pydantic", "pydantic"),
    ("networkx", "networkx"),
    ("neo4j", "neo4j"),
    ("pulp", "pulp"),
    ("scipy", "scipy"),
    ("numpy", "numpy"),
]

OPTIONAL = [
    ("dotenv", "python-dotenv"),
    ("httpx", "httpx (test client only)"),
]

VENV_MARKERS = ("venv", "test", ".venv")


def in_virtualenv() -> bool:
    return sys.prefix != sys.base_prefix or any(
        marker in sys.prefix.lower() for marker in VENV_MARKERS
    )


def main() -> int:
    print("=" * 68)
    print("PREFLIGHT CHECK")
    print("=" * 68)
    print(f"python     : {sys.executable}")
    print(f"prefix     : {sys.prefix}")

    if in_virtualenv():
        print("venv       : OK (running inside a virtual environment)")
    else:
        print(
            "venv       : MISSING -- you are using the system Python.\n"
            "             Fix:  test\\Scripts\\python.exe -m uvicorn app.main:app --port 8000"
        )

    print("\nrequired packages:")
    missing = []
    for module, package in REQUIRED:
        try:
            mod = __import__(module)
            version = getattr(mod, "__version__", "?")
            print(f"  [OK]    {module:<12} {version:<12} ({package})")
        except ModuleNotFoundError:
            print(f"  [MISS]  {module:<12} {'':<12} ({package})")
            missing.append(package)

    print("\noptional packages:")
    for module, package in OPTIONAL:
        try:
            mod = __import__(module)
            version = getattr(mod, "__version__", "?")
            print(f"  [OK]    {module:<12} {version}")
        except ModuleNotFoundError:
            print(f"  [MISS]  {module:<12} (optional)")

    # Neo4j connectivity is the other common blocker. Everything async runs in
    # a single event loop -- calling asyncio.run twice would tear the loop down
    # underneath the cached driver.
    print("\nNeo4j:")
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import asyncio

        from app.database import (
            NEO4J_URI,
            NEO4J_USER,
            close_driver,
            verify_connectivity,
        )

        async def probe() -> bool:
            try:
                return await verify_connectivity()
            finally:
                await close_driver()

        print(f"  uri      : {NEO4J_URI}")
        print(f"  user     : {NEO4J_USER}")
        if asyncio.run(probe()):
            print("  [OK]    connected")
        else:
            print("  [FAIL]  cannot connect -- is Neo4j running?")
    except Exception as exc:  # pragma: no cover - diagnostics path
        print(f"  [FAIL]  {type(exc).__name__}: {exc}")

    print("\n" + "=" * 68)
    if missing:
        print(f"MISSING {len(missing)} required package(s): {', '.join(missing)}")
        print("\nInstall everything into the venv:")
        print("    test\\Scripts\\python.exe -m pip install -r requirements.txt")
        return 1

    print("All required packages present.")
    print("\nStart the server with:")
    print("    test\\Scripts\\python.exe -m uvicorn app.main:app --port 8000 --reload")
    print("\nSeed a 100-node Physics graph:")
    print("    test\\Scripts\\python.exe -m scripts.seed_physics --reset")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
