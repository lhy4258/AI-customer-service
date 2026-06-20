from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import get_customer_service
from app.api.v1.customer_service import router as customer_service_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="项目1 - 客服对话",
        version="0.1.0",
        description="客服对话、人工转接、客服后台和会话生命周期 MVP。",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(customer_service_router)

    @app.get("/health")
    def health() -> dict:
        service = get_customer_service()
        return {
            "status": "ok",
            "project": "customer-service",
            "summary": service.data_summary(),
        }

    return app


app = create_app()
