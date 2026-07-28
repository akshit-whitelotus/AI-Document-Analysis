from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker,AsyncSession
from shared.config.settings import settings

engine=create_async_engine(settings.database_url,echo=settings.DEBUG,future=True)

AsyncSessionLocal=async_sessionmaker(bind=engine,class_=AsyncSession,expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as Session:
        yield Session
        