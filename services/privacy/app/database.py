from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

engine = create_async_engine(settings.database_url)
# expire_on_commit=False: after commit(), SQLAlchemy would normally expire all
# attributes and reload them on next access. In an async context that triggers a
# lazy load, which raises MissingGreenlet. Disabling expiry keeps attribute values
# accessible after commit without an extra round-trip.
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
