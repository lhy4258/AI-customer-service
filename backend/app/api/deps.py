from functools import lru_cache

from app.core.config import settings
from app.core.database import SessionLocal, init_db_schema
from app.services.customer_service import CustomerServiceFacade
from app.services.demo_data import build_demo_service
from app.services.repository import SqlAlchemyRepository


@lru_cache(maxsize=1)
def get_customer_service() -> CustomerServiceFacade:
    if settings.repository_backend == "postgres":
        if SessionLocal is None:
            raise RuntimeError("SQLAlchemy is not available. Run `uv sync` before using PostgreSQL.")
        init_db_schema()
        repository = SqlAlchemyRepository(SessionLocal)
        return CustomerServiceFacade(repository)
    return build_demo_service()
