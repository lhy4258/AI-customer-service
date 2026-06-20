from __future__ import annotations

from typing import Any

from app.services.customer_service import CustomerServiceFacade
from app.services.repository import InMemoryRepository


def build_demo_service(repository: Any | None = None) -> CustomerServiceFacade:
    repository = repository or InMemoryRepository()
    return CustomerServiceFacade(repository)
