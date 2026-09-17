"""Initialize database tables for development."""

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models.repository import Repository
from app.db.session import get_engine


async def init_db() -> None:
    """Create all database tables."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created successfully.")


if __name__ == "__main__":
    asyncio.run(init_db())