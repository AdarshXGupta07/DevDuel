from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings

engine = create_async_engine(settings.supabase_url)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with async_session_factory() as session:
        yield session