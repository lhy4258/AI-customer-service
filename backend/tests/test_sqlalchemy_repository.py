import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core import database
from app.core.database import Base
from app.models.tables import (
    AiCallLogTable,
    ConversationMessageTable,
    ConversationTable,
    HandoffTicketTable,
    KnowledgeChunkTable,
    KnowledgeDocumentTable,
)
from app.services.demo_data import build_demo_service
from app.services.repository import SqlAlchemyRepository


class SqlAlchemyRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def test_repository_persists_seed_and_conversation_lifecycle(self):
        service = build_demo_service(repository=SqlAlchemyRepository(self.session_factory))

        summary = service.data_summary()
        self.assertEqual(
            summary,
            {
                "conversations": 0,
                "handoff_tickets": 0,
                "corrections": 0,
                "ai_call_logs": 0,
            },
        )

        ai_reply = service.chat("customer-001", "你好，我想咨询一下")
        handoff = service.chat("customer-002", "我要转人工，投诉人工处理")
        ticket = service.list_handoff_tickets()[0]
        service.claim_ticket(ticket["id"])
        service.human_reply(handoff["conversation_id"], "您好，我已经接入，会继续协助处理。")
        service.close_by_human_support(handoff["conversation_id"], "resolved")

        with self.session_factory() as session:
            self.assertEqual(session.query(ConversationTable).count(), 2)
            self.assertGreaterEqual(session.query(ConversationMessageTable).count(), 6)
            self.assertEqual(session.scalar(select(HandoffTicketTable.status)), "closed")
            self.assertEqual(session.query(AiCallLogTable).count(), 1)

        persisted = service.get_conversation(ai_reply["conversation_id"])
        self.assertEqual(persisted["messages"][-1]["sender_type"], "ai")

    def test_ai_call_log_table_stores_retrieval_metadata(self):
        columns = AiCallLogTable.__table__.columns
        self.assertIn("metadata_json", columns)

        service = build_demo_service(repository=SqlAlchemyRepository(self.session_factory))
        response = service.chat("customer-001", "unmatched question")

        with self.session_factory() as session:
            log = session.scalars(select(AiCallLogTable)).one()
            self.assertEqual(log.metadata_json["conversation_id"], response["conversation_id"])
            self.assertEqual(log.metadata_json["message_id"], response["message_id"])
            self.assertEqual(log.metadata_json["retrieval"]["query_text"], "unmatched question")
            self.assertEqual(log.metadata_json["retrieval"]["returned_count"], 0)
            self.assertEqual(log.metadata_json["retrieval"]["confidence"]["value"], 0.0)

    def test_knowledge_chunk_table_is_generic_and_uses_pgvector(self):
        columns = KnowledgeChunkTable.__table__.columns

        self.assertIn("dense_embedding", columns)
        self.assertIn("sparse_vector", columns)
        self.assertIn("search_vector", columns)
        self.assertIn("question_text", columns)
        self.assertIn("answer_text", columns)
        self.assertIn("retrieval_text", columns)
        self.assertIn("document_id", columns)
        self.assertIn("content_hash", columns)
        self.assertNotIn("source_type", columns)
        self.assertNotIn("source_id", columns)
        self.assertEqual(str(columns["dense_embedding"].type), "VECTOR(1536)")

    def test_knowledge_document_table_tracks_upload_status(self):
        columns = KnowledgeDocumentTable.__table__.columns

        self.assertIn("file_name", columns)
        self.assertIn("status", columns)
        self.assertIn("chunk_count", columns)
        self.assertIn("error", columns)

    def test_postgres_schema_initializes_pgvector_before_metadata_create_all(self):
        calls = []

        def record_create_all(bind):
            calls.append("metadata")

        def record_postgres_schema():
            calls.append("postgres")

        with (
            patch.object(database.settings, "database_url", "postgresql+psycopg://postgres:postgres@127.0.0.1/db"),
            patch.object(database.Base.metadata, "create_all", side_effect=record_create_all),
            patch.object(database, "_init_postgres_knowledge_schema", side_effect=record_postgres_schema),
        ):
            database.init_db_schema()

        self.assertEqual(calls, ["postgres", "metadata"])


if __name__ == "__main__":
    unittest.main()
