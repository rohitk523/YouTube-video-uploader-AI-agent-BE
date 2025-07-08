"""
Database configuration and setup
"""

import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData

from app.config import get_settings

settings = get_settings()

# Global variables for engine and session factory
engine = None
AsyncSessionLocal = None

def _create_engine():
    """Create a new database engine with anti-caching settings."""
    return create_async_engine(
        settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
        echo=settings.debug,
        future=True,
        pool_pre_ping=True,  # Validate connections before use
        pool_recycle=3600,   # Recycle connections every hour
        connect_args={
            "prepared_statement_cache_size": 0,  # Disable prepared statement caching
            "statement_cache_size": 0,           # Disable statement caching
            "server_settings": {
                "application_name": "youtube_shorts_api",
            }
        }
    )

def _initialize_database_components():
    """Initialize or reinitialize database engine and session factory."""
    global engine, AsyncSessionLocal
    
    # Dispose of existing engine if it exists
    if engine is not None:
        asyncio.create_task(engine.dispose())
    
    # Create new engine and session factory
    engine = _create_engine()
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=True
    )

# Initialize on module import
_initialize_database_components()


class Base(DeclarativeBase):
    """Base class for all database models."""
    metadata = MetaData()


async def restart_database_connection() -> None:
    """
    Restart the database connection pool to clear all cached statements.
    This is useful when schema changes have been made.
    """
    _initialize_database_components()
    # Wait a bit for the old connections to be disposed
    await asyncio.sleep(0.1)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get database session.
    
    Yields:
        AsyncSession: Database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            # Only commit if there are pending changes
            if session.dirty or session.new or session.deleted:
                await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_database() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_database() -> None:
    """Close database connections."""
    await engine.dispose() 