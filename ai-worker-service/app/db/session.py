from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.config.settings import settings

SYNC_DATABASE_URL=settings.database_url.replace("+asyncpg","+psycopg2")

engine=create_engine(SYNC_DATABASE_URL,echo=settings.DEBUG,future=True)
SessionLocal=sessionmaker(bind=engine,expire_on_commit=False)
