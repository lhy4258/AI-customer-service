from __future__ import annotations

import os


try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ModuleNotFoundError:
    BaseSettings = object
    SettingsConfigDict = None


if SettingsConfigDict:

    class Settings(BaseSettings):
        database_url: str = "sqlite:///./data/customer_service.db"
        redis_url: str = "redis://localhost:6379/0"
        project_id: str = "customer-service"
        llm_base_url: str = ""
        llm_api_key: str = ""
        llm_model: str = "local-dialog-summary"
        llm_temperature: float = 0.2
        llm_top_p: float = 0.8
        embedding_base_url: str = ""
        embedding_api_key: str = ""
        embedding_model: str = "text-embedding-3-small"
        embedding_dim: int = 1536
        retrieval_top_k: int = 4
        retrieval_min_score: float = 0.08
        hybrid_dense_weight: float = 0.65
        hybrid_sparse_weight: float = 0.35
        repository_backend: str = "memory"

        model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

else:

    class Settings:
        def __init__(self) -> None:
            self.database_url = os.getenv("DATABASE_URL", "sqlite:///./data/customer_service.db")
            self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self.project_id = os.getenv("PROJECT_ID", "customer-service")
            self.llm_base_url = os.getenv("LLM_BASE_URL", "")
            self.llm_api_key = os.getenv("LLM_API_KEY", "")
            self.llm_model = os.getenv("LLM_MODEL", "local-dialog-summary")
            self.llm_temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))
            self.llm_top_p = float(os.getenv("LLM_TOP_P", "0.8"))
            self.embedding_base_url = os.getenv("EMBEDDING_BASE_URL", "")
            self.embedding_api_key = os.getenv("EMBEDDING_API_KEY", "")
            self.embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
            self.embedding_dim = int(os.getenv("EMBEDDING_DIM", "1536"))
            self.retrieval_top_k = int(os.getenv("RETRIEVAL_TOP_K", "4"))
            self.retrieval_min_score = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.08"))
            self.hybrid_dense_weight = float(os.getenv("HYBRID_DENSE_WEIGHT", "0.65"))
            self.hybrid_sparse_weight = float(os.getenv("HYBRID_SPARSE_WEIGHT", "0.35"))
            self.repository_backend = os.getenv("REPOSITORY_BACKEND", "memory")


settings = Settings()
