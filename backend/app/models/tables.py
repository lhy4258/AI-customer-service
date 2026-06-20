from __future__ import annotations

try:
    from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.orm import Mapped, mapped_column
    from sqlalchemy.types import UserDefinedType
    from pgvector.sqlalchemy import Vector
except ModuleNotFoundError:
    TABLES_AVAILABLE = False
else:
    TABLES_AVAILABLE = True
    from app.core.database import Base
    from app.core.config import settings

    class SearchVectorType(UserDefinedType):
        cache_ok = True

        def get_col_spec(self, **kw) -> str:
            return "TSVECTOR"

    @compiles(SearchVectorType, "sqlite")
    def _compile_search_vector_sqlite(type_, compiler, **kw):
        return "TEXT"

    @compiles(SearchVectorType, "postgresql")
    def _compile_search_vector_postgresql(type_, compiler, **kw):
        return "TSVECTOR"

    class ConversationTable(Base):
        __tablename__ = "conversations"

        id: Mapped[str] = mapped_column(String(64), primary_key=True)
        customer_id: Mapped[str] = mapped_column(String(64), index=True)
        status: Mapped[str] = mapped_column(String(40), index=True)
        mode: Mapped[str] = mapped_column(String(40))
        last_message_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)
        closed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
        close_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
        created_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)

    class ConversationMessageTable(Base):
        __tablename__ = "conversation_messages"

        id: Mapped[str] = mapped_column(String(64), primary_key=True)
        conversation_id: Mapped[str] = mapped_column(String(64), ForeignKey("conversations.id"), index=True)
        sender_type: Mapped[str] = mapped_column(String(40), index=True)
        sender_id: Mapped[str] = mapped_column(String(64))
        content: Mapped[str] = mapped_column(Text)
        metadata_json: Mapped[dict] = mapped_column(JSON)
        created_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)

    class HandoffTicketTable(Base):
        __tablename__ = "handoff_tickets"

        id: Mapped[str] = mapped_column(String(64), primary_key=True)
        conversation_id: Mapped[str] = mapped_column(String(64), ForeignKey("conversations.id"), index=True)
        status: Mapped[str] = mapped_column(String(40), index=True)
        requested_reason: Mapped[str] = mapped_column(String(200))
        requested_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)
        accepted_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
        closed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    class CorrectionTable(Base):
        __tablename__ = "corrections"

        id: Mapped[str] = mapped_column(String(64), primary_key=True)
        question_id: Mapped[str] = mapped_column(String(64), index=True)
        bad_answer: Mapped[str] = mapped_column(Text)
        fixed_answer: Mapped[str] = mapped_column(Text)
        reason: Mapped[str] = mapped_column(Text)
        created_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)

    class AiCallLogTable(Base):
        __tablename__ = "ai_call_logs"

        id: Mapped[str] = mapped_column(String(64), primary_key=True)
        request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
        model: Mapped[str] = mapped_column(String(100))
        prompt_version: Mapped[str] = mapped_column(String(100))
        input_hash: Mapped[str] = mapped_column(String(64))
        token_in: Mapped[int] = mapped_column(Integer)
        token_out: Mapped[int] = mapped_column(Integer)
        latency_ms: Mapped[int] = mapped_column(Integer)
        error: Mapped[str | None] = mapped_column(Text, nullable=True)
        metadata_json: Mapped[dict] = mapped_column(JSON)
        created_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)

    class KnowledgeDocumentTable(Base):
        __tablename__ = "knowledge_documents"

        id: Mapped[str] = mapped_column(String(64), primary_key=True)
        file_name: Mapped[str] = mapped_column(String(255), index=True)
        source: Mapped[str] = mapped_column(String(100), index=True)
        status: Mapped[str] = mapped_column(String(40), index=True)
        chunk_count: Mapped[int] = mapped_column(Integer)
        error: Mapped[str | None] = mapped_column(Text, nullable=True)
        created_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)
        updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)

    class KnowledgeChunkTable(Base):
        __tablename__ = "knowledge_chunks"

        id: Mapped[str] = mapped_column(String(64), primary_key=True)
        document_id: Mapped[str] = mapped_column(String(64), ForeignKey("knowledge_documents.id"), index=True)
        question_text: Mapped[str] = mapped_column(Text)
        answer_text: Mapped[str] = mapped_column(Text)
        retrieval_text: Mapped[str] = mapped_column(Text)
        chunk_text: Mapped[str] = mapped_column(Text)
        dense_embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.embedding_dim), nullable=True)
        sparse_vector: Mapped[dict] = mapped_column(JSON)
        search_vector: Mapped[str | None] = mapped_column(SearchVectorType, nullable=True)
        content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
        metadata_json: Mapped[dict] = mapped_column(JSON)
        created_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)
        updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)
