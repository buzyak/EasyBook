from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from backend.config import settings
engine=create_async_engine(settings.database_url, echo=False)
SessionLocal=async_sessionmaker(engine, expire_on_commit=False)
async def get_db():
    async with SessionLocal() as s:
        yield s
