from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings

# Base is defined in models.py — import it from there to avoid
# having two separate metadata objects, which would cause tables
# created via Base.metadata.create_all() to be missed.
from app.models import Base  # noqa: F401  (re-exported for convenience)


engine = create_engine(
    settings.DATABASE_URL,
    poolclass=NullPool,  # Railway / serverless: no persistent connection pool
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

