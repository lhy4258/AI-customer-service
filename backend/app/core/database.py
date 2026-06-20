from __future__ import annotations

from app.core.config import settings


try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
except ModuleNotFoundError:
    SQLALCHEMY_AVAILABLE = False
    engine = None
    SessionLocal = None

    class Base:
        pass

    def get_db():
        raise RuntimeError("SQLAlchemy is not installed. Run `uv sync` before using the DB layer.")

    def init_db_schema() -> None:
        raise RuntimeError("SQLAlchemy is not installed. Run `uv sync` before using the DB layer.")

else:
    SQLALCHEMY_AVAILABLE = True

    class Base(DeclarativeBase):
        pass

    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    engine = create_engine(settings.database_url, connect_args=connect_args)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def get_db():
        db: Session = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def init_db_schema() -> None:
        from app.models import tables  # noqa: F401

        if not settings.database_url.startswith("sqlite"):
            _init_postgres_knowledge_schema()
        Base.metadata.create_all(bind=engine)

    def _init_postgres_knowledge_schema() -> None:
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS knowledge_documents (
                        id character varying(64) PRIMARY KEY,
                        file_name character varying(255) NOT NULL,
                        source character varying(100) NOT NULL,
                        status character varying(40) NOT NULL,
                        chunk_count integer NOT NULL,
                        error text NULL,
                        created_at timestamp with time zone NOT NULL,
                        updated_at timestamp with time zone NOT NULL
                    )
                    """
                )
            )
            legacy_columns = connection.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'knowledge_chunks'
                    """
                )
            ).scalars().all()
            if legacy_columns and "dense_embedding" not in set(legacy_columns):
                connection.execute(text("DROP TABLE IF EXISTS knowledge_chunks CASCADE"))
            connection.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS knowledge_chunks (
                        id character varying(64) PRIMARY KEY,
                        document_id character varying(64) NOT NULL REFERENCES knowledge_documents(id),
                        question_text text NOT NULL,
                        answer_text text NOT NULL,
                        retrieval_text text NOT NULL,
                        chunk_text text NOT NULL,
                        dense_embedding vector({settings.embedding_dim}) NULL,
                        sparse_vector json NOT NULL,
                        search_vector tsvector NULL,
                        content_hash character varying(64) NOT NULL UNIQUE,
                        metadata_json json NOT NULL,
                        created_at timestamp with time zone NOT NULL,
                        updated_at timestamp with time zone NOT NULL
                    )
                    """
                )
            )
            for statement in (
                "CREATE INDEX IF NOT EXISTS ix_knowledge_documents_file_name ON knowledge_documents (file_name)",
                "CREATE INDEX IF NOT EXISTS ix_knowledge_documents_source ON knowledge_documents (source)",
                "CREATE INDEX IF NOT EXISTS ix_knowledge_documents_status ON knowledge_documents (status)",
                "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_document_id ON knowledge_chunks (document_id)",
                "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_content_hash ON knowledge_chunks (content_hash)",
                "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_search_vector ON knowledge_chunks USING GIN (search_vector)",
            ):
                connection.execute(text(statement))
            connection.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.tables
                            WHERE table_schema = 'public' AND table_name = 'ai_call_logs'
                        ) THEN
                            ALTER TABLE ai_call_logs
                            ADD COLUMN IF NOT EXISTS metadata_json json NOT NULL DEFAULT '{}'::json;
                        END IF;
                    END $$;
                    """
                )
            )
