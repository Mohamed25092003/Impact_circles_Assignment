from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from Models.constants import DATABASE_URL


def get_database_url() -> str:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required. Set it in .env.")
    return DATABASE_URL


engine = create_engine(get_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        yield session
