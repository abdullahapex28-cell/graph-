"""Neo4j database connection and session management."""

from contextlib import asynccontextmanager
from neo4j import AsyncGraphDatabase, AsyncDriver
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

# Default Neo4j configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

_driver: Optional[AsyncDriver] = None


async def get_driver() -> AsyncDriver:
    """Get or create the Neo4j async driver."""
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            max_connection_lifetime=30 * 60,
            max_connection_pool_size=50,
            connection_acquisition_timeout=60,
        )
    return _driver


async def verify_connectivity() -> bool:
    """Verify Neo4j connectivity. Returns True if connected, False otherwise."""
    try:
        driver = await get_driver()
        await driver.verify_connectivity()
        return True
    except Exception:
        return False


async def close_driver():
    """Close the Neo4j driver."""
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


@asynccontextmanager
async def get_session():
    """Get a Neo4j session from the driver."""
    driver = await get_driver()
    async with driver.session() as session:
        yield session


async def init_database():
    """Initialize database with constraints and indexes."""
    try:
        async with get_session() as session:
            # Create constraints
            await session.run("""
                CREATE CONSTRAINT node_id_unique IF NOT EXISTS
                FOR (n:Concept) REQUIRE n.id IS UNIQUE
            """)
            await session.run("""
                CREATE CONSTRAINT rel_id_unique IF NOT EXISTS
                FOR ()-[r:RELATES_TO]-() REQUIRE r.id IS UNIQUE
            """)
            # Create indexes for performance
            await session.run("""
                CREATE INDEX node_name_idx IF NOT EXISTS
                FOR (n:Concept) ON (n.name)
            """)
            await session.run("""
                CREATE INDEX rel_type_idx IF NOT EXISTS
                FOR ()-[r:RELATES_TO]-() ON (r.type)
            """)
        return True
    except Exception as e:
        print(f"Warning: Could not initialize database (Neo4j may not be running): {e}")
        return False


async def clear_database():
    """Clear all data from the database (for testing)."""
    async with get_session() as session:
        await session.run("MATCH (n) DETACH DELETE n")