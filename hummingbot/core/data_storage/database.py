"""
Database connection and migration management for Hummingbot.

Provides centralized database connectivity with support for both SQLite and PostgreSQL,
along with automatic migrations and connection pooling.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import aiosqlite
import asyncpg
import asyncpg.pool

from hummingbot.client.config.global_config_map import global_config_map
from hummingbot.core.utils.async_utils import safe_ensure_future


class DatabaseManager:
    """Manages database connections and migrations."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._pool: Optional[Union[asyncpg.pool.Pool, aiosqlite.Connection]] = None
        self._db_type: Optional[str] = None
        self._migrations_path = Path(__file__).parent.parent.parent.parent / "db"
        
    async def initialize(self, db_config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize database connection based on configuration."""
        if db_config is None:
            db_config = self._get_db_config_from_global()
            
        self._db_type = db_config.get("type", "sqlite")
        
        if self._db_type == "postgresql":
            await self._init_postgresql(db_config)
        else:
            await self._init_sqlite(db_config)
            
        await self._run_migrations()
        
    def _get_db_config_from_global(self) -> Dict[str, Any]:
        """Extract database configuration from global config."""
        # Default to SQLite for development
        return {
            "type": global_config_map.get("db_type", "sqlite"),
            "host": global_config_map.get("db_host", "localhost"),
            "port": global_config_map.get("db_port", 5432),
            "database": global_config_map.get("db_name", "hummingbot"),
            "user": global_config_map.get("db_user", "hummingbot"),
            "password": global_config_map.get("db_password", ""),
            "sqlite_path": global_config_map.get("sqlite_path", "data/hummingbot.db"),
        }
        
    async def _init_postgresql(self, config: Dict[str, Any]) -> None:
        """Initialize PostgreSQL connection pool."""
        try:
            self._pool = await asyncpg.create_pool(
                host=config["host"],
                port=config["port"],
                database=config["database"],
                user=config["user"],
                password=config["password"],
                min_size=2,
                max_size=10,
                command_timeout=30,
            )
            self.logger.info("PostgreSQL connection pool initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize PostgreSQL: {e}")
            raise
            
    async def _init_sqlite(self, config: Dict[str, Any]) -> None:
        """Initialize SQLite connection."""
        try:
            db_path = Path(config["sqlite_path"])
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            self._pool = await aiosqlite.connect(str(db_path))
            await self._pool.execute("PRAGMA foreign_keys = ON")
            await self._pool.execute("PRAGMA journal_mode = WAL")
            await self._pool.commit()
            self.logger.info(f"SQLite database initialized: {db_path}")
        except Exception as e:
            self.logger.error(f"Failed to initialize SQLite: {e}")
            raise
            
    async def _run_migrations(self) -> None:
        """Run database migrations in order."""
        migration_files = sorted(self._migrations_path.glob("*.sql"))
        
        # Create migrations tracking table
        await self._create_migrations_table()
        
        # Get applied migrations
        applied_migrations = await self._get_applied_migrations()
        
        for migration_file in migration_files:
            if migration_file.name not in applied_migrations:
                await self._apply_migration(migration_file)
                
    async def _create_migrations_table(self) -> None:
        """Create migrations tracking table."""
        sql = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        await self.execute(sql)
        
    async def _get_applied_migrations(self) -> List[str]:
        """Get list of applied migration versions."""
        sql = "SELECT version FROM schema_migrations ORDER BY version"
        rows = await self.fetch(sql)
        return [row[0] for row in rows]
        
    async def _apply_migration(self, migration_file: Path) -> None:
        """Apply a single migration file."""
        try:
            self.logger.info(f"Applying migration: {migration_file.name}")
            
            with open(migration_file, 'r') as f:
                migration_sql = f.read()
                
            # Split on semicolons and execute each statement
            statements = [stmt.strip() for stmt in migration_sql.split(';') if stmt.strip()]
            
            for statement in statements:
                await self.execute(statement)
                
            # Record migration as applied
            await self.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)" if self._db_type == "sqlite"
                else "INSERT INTO schema_migrations (version) VALUES ($1)",
                migration_file.name
            )
            
            self.logger.info(f"Migration applied successfully: {migration_file.name}")
            
        except Exception as e:
            self.logger.error(f"Failed to apply migration {migration_file.name}: {e}")
            raise
            
    @asynccontextmanager
    async def get_connection(self):
        """Get database connection from pool."""
        if self._db_type == "postgresql":
            async with self._pool.acquire() as conn:
                yield conn
        else:
            yield self._pool
            
    async def execute(self, sql: str, *args) -> None:
        """Execute SQL statement."""
        async with self.get_connection() as conn:
            if self._db_type == "postgresql":
                await conn.execute(sql, *args)
            else:
                await conn.execute(sql, args)
                await conn.commit()
                
    async def fetch(self, sql: str, *args) -> List[tuple]:
        """Fetch multiple rows."""
        async with self.get_connection() as conn:
            if self._db_type == "postgresql":
                rows = await conn.fetch(sql, *args)
                return [tuple(row) for row in rows]
            else:
                cursor = await conn.execute(sql, args)
                rows = await cursor.fetchall()
                return rows
                
    async def fetchone(self, sql: str, *args) -> Optional[tuple]:
        """Fetch single row."""
        async with self.get_connection() as conn:
            if self._db_type == "postgresql":
                row = await conn.fetchrow(sql, *args)
                return tuple(row) if row else None
            else:
                cursor = await conn.execute(sql, args)
                row = await cursor.fetchone()
                return row
                
    async def close(self) -> None:
        """Close database connections."""
        if self._pool:
            if self._db_type == "postgresql":
                await self._pool.close()
            else:
                await self._pool.close()
            self._pool = None
            self.logger.info("Database connections closed")


# Global database manager instance
db_manager = DatabaseManager()


class DatabaseError(Exception):
    """Custom exception for database operations."""
    pass


# Utility functions for common database operations

async def init_database(config: Optional[Dict[str, Any]] = None) -> None:
    """Initialize database with optional configuration."""
    await db_manager.initialize(config)


async def close_database() -> None:
    """Close database connections."""
    await db_manager.close()


def convert_decimal_to_db(value: Any) -> Any:
    """Convert Decimal values for database storage."""
    if isinstance(value, Decimal):
        return float(value)
    return value


def convert_db_to_decimal(value: Any) -> Any:
    """Convert database values back to Decimal."""
    if isinstance(value, (int, float)) and value is not None:
        return Decimal(str(value))
    return value