from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable

try:
    from sqlalchemy import delete, func, select
except ModuleNotFoundError:
    SQLALCHEMY_REPOSITORY_AVAILABLE = False
else:
    SQLALCHEMY_REPOSITORY_AVAILABLE = True

if SQLALCHEMY_REPOSITORY_AVAILABLE:
    from app.models.tables import (
        AiCallLogTable,
        ConversationMessageTable,
        ConversationTable,
        CorrectionTable,
        HandoffTicketTable,
        KnowledgeChunkTable,
        KnowledgeDocumentTable,
    )

from app.services.knowledge_base import KnowledgeSearchHit, hybrid_score
from app.services.entities import (
    AiCallLog,
    Conversation,
    ConversationMessage,
    ConversationStatus,
    Correction,
    HandoffTicket,
    KnowledgeChunk,
    KnowledgeDocument,
    to_public_dict,
    utcnow,
)


class InMemoryRepository:
    def __init__(self) -> None:
        self.conversations: dict[str, Conversation] = {}
        self.messages: dict[str, list[ConversationMessage]] = defaultdict(list)
        self.handoff_tickets: dict[str, HandoffTicket] = {}
        self.corrections: dict[str, Correction] = {}
        self.ai_call_logs: dict[str, AiCallLog] = {}
        self.knowledge_documents: dict[str, KnowledgeDocument] = {}
        self.knowledge_chunks: dict[str, KnowledgeChunk] = {}
        self._counters: defaultdict[str, int] = defaultdict(int)

    def next_id(self, prefix: str) -> str:
        self._counters[prefix] += 1
        return f"{prefix}-{self._counters[prefix]:04d}"

    def create_conversation(self, customer_id: str) -> Conversation:
        conversation = Conversation(id=self.next_id("conv"), customer_id=customer_id)
        self.conversations[conversation.id] = conversation
        return conversation

    def get_conversation(self, conversation_id: str) -> Conversation:
        try:
            return self.conversations[conversation_id]
        except KeyError as exc:
            raise ValueError(f"conversation not found: {conversation_id}") from exc

    def save_conversation(self, conversation: Conversation) -> Conversation:
        self.conversations[conversation.id] = conversation
        return conversation

    def add_message(
        self,
        conversation_id: str,
        sender_type: str,
        sender_id: str,
        content: str,
        metadata: dict | None = None,
    ) -> ConversationMessage:
        conversation = self.get_conversation(conversation_id)
        message = ConversationMessage(
            id=self.next_id("msg"),
            conversation_id=conversation_id,
            sender_type=sender_type,
            sender_id=sender_id,
            content=content,
            metadata=metadata or {},
        )
        self.messages[conversation_id].append(message)
        conversation.last_message_at = message.created_at
        self.save_conversation(conversation)
        return message

    def list_messages(self, conversation_id: str) -> list[ConversationMessage]:
        self.get_conversation(conversation_id)
        return list(self.messages[conversation_id])

    def create_handoff_ticket(self, conversation_id: str, reason: str) -> HandoffTicket:
        existing = self.find_open_ticket(conversation_id)
        if existing:
            return existing
        ticket = HandoffTicket(
            id=self.next_id("ticket"),
            conversation_id=conversation_id,
            status="pending",
            requested_reason=reason,
        )
        self.handoff_tickets[ticket.id] = ticket
        return ticket

    def find_open_ticket(self, conversation_id: str) -> HandoffTicket | None:
        for ticket in self.handoff_tickets.values():
            if ticket.conversation_id == conversation_id and ticket.status in {"pending", "claimed"}:
                return ticket
        return None

    def get_ticket(self, ticket_id: str) -> HandoffTicket:
        try:
            return self.handoff_tickets[ticket_id]
        except KeyError as exc:
            raise ValueError(f"handoff ticket not found: {ticket_id}") from exc

    def save_ticket(self, ticket: HandoffTicket) -> HandoffTicket:
        self.handoff_tickets[ticket.id] = ticket
        return ticket

    def list_handoff_tickets(self, status: str | None = None) -> list[HandoffTicket]:
        tickets = list(self.handoff_tickets.values())
        if status:
            tickets = [ticket for ticket in tickets if ticket.status == status]
        return tickets

    def add_correction(self, correction: Correction) -> Correction:
        self.corrections[correction.id] = correction
        return correction

    def add_ai_call_log(self, log: AiCallLog) -> AiCallLog:
        self.ai_call_logs[log.id] = log
        return log

    def add_knowledge_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        self.knowledge_documents[document.id] = document
        return document

    def save_knowledge_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        document.updated_at = utcnow()
        self.knowledge_documents[document.id] = document
        return document

    def list_knowledge_documents(self) -> list[KnowledgeDocument]:
        return sorted(self.knowledge_documents.values(), key=lambda document: document.created_at)

    def delete_knowledge_document(self, document_id: str) -> KnowledgeDocument:
        try:
            document = self.knowledge_documents.pop(document_id)
        except KeyError as exc:
            raise ValueError(f"knowledge document not found: {document_id}") from exc
        self.knowledge_chunks = {
            chunk_id: chunk
            for chunk_id, chunk in self.knowledge_chunks.items()
            if chunk.document_id != document_id
        }
        return document

    def add_knowledge_chunk(self, chunk: KnowledgeChunk) -> KnowledgeChunk | None:
        for existing in self.knowledge_chunks.values():
            if existing.content_hash == chunk.content_hash:
                return None
        self.knowledge_chunks[chunk.id] = chunk
        return chunk

    def search_knowledge_chunks(
        self,
        query: str,
        top_k: int,
        min_score: float,
        dense_weight: float,
        sparse_weight: float,
        query_embedding: list[float] | None = None,
    ) -> list[KnowledgeSearchHit]:
        hits = []
        for chunk in self.knowledge_chunks.values():
            score, dense_score, sparse_score = hybrid_score(
                query=query,
                text=chunk.retrieval_text,
                sparse=chunk.sparse_vector,
                dense_weight=dense_weight,
                sparse_weight=sparse_weight,
                query_embedding=query_embedding,
                dense_embedding=chunk.dense_embedding,
            )
            if score < min_score:
                continue
            hits.append(
                KnowledgeSearchHit(
                    id=chunk.id,
                    question_text=chunk.question_text,
                    answer_text=chunk.answer_text,
                    retrieval_text=chunk.retrieval_text,
                    chunk_text=chunk.chunk_text,
                    dense_score=dense_score,
                    sparse_score=sparse_score,
                    score=score,
                    metadata=chunk.metadata,
                )
            )
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:top_k]

    def force_last_message_at(self, conversation_id: str, value: datetime) -> None:
        conversation = self.get_conversation(conversation_id)
        conversation.last_message_at = value
        self.save_conversation(conversation)

    def iter_conversations(self) -> Iterable[Conversation]:
        return self.conversations.values()

    def data_summary(self) -> dict[str, int]:
        return {
            "conversations": len(self.conversations),
            "handoff_tickets": len(self.handoff_tickets),
            "corrections": len(self.corrections),
            "ai_call_logs": len(self.ai_call_logs),
        }

    def conversation_to_dict(self, conversation: Conversation) -> dict:
        payload = to_public_dict(conversation)
        payload["messages"] = to_public_dict(self.list_messages(conversation.id))
        ticket = self.find_open_ticket(conversation.id)
        payload["handoff_ticket"] = to_public_dict(ticket) if ticket else None
        return payload

    def close_conversation(
        self,
        conversation: Conversation,
        status: ConversationStatus,
        reason: str,
    ) -> Conversation:
        conversation.status = status
        conversation.closed_at = utcnow()
        conversation.close_reason = reason
        conversation.mode = "closed"
        self.save_conversation(conversation)
        return conversation


class SqlAlchemyRepository:
    def __init__(self, session_factory) -> None:
        if not SQLALCHEMY_REPOSITORY_AVAILABLE:
            raise RuntimeError("SQLAlchemy is not installed. Run `uv sync` before using the DB layer.")
        self.session_factory = session_factory

    def next_id(self, prefix: str) -> str:
        table = {
            "conv": ConversationTable,
            "msg": ConversationMessageTable,
            "ticket": HandoffTicketTable,
            "corr": CorrectionTable,
            "ailog": AiCallLogTable,
            "doc": KnowledgeDocumentTable,
            "kchunk": KnowledgeChunkTable,
        }.get(prefix)
        if table is None:
            raise ValueError(f"unsupported id prefix: {prefix}")
        with self.session_factory() as session:
            ids = session.scalars(select(table.id).where(table.id.like(f"{prefix}-%"))).all()
        max_number = 0
        for value in ids:
            try:
                max_number = max(max_number, int(value.rsplit("-", 1)[1]))
            except (IndexError, ValueError):
                continue
        return f"{prefix}-{max_number + 1:04d}"

    def create_conversation(self, customer_id: str) -> Conversation:
        conversation = Conversation(id=self.next_id("conv"), customer_id=customer_id)
        return self.save_conversation(conversation)

    def get_conversation(self, conversation_id: str) -> Conversation:
        with self.session_factory() as session:
            row = session.get(ConversationTable, conversation_id)
            if row is None:
                raise ValueError(f"conversation not found: {conversation_id}")
            return self._conversation(row)

    def save_conversation(self, conversation: Conversation) -> Conversation:
        with self.session_factory() as session:
            session.merge(
                ConversationTable(
                    id=conversation.id,
                    customer_id=conversation.customer_id,
                    status=conversation.status.value,
                    mode=conversation.mode,
                    last_message_at=conversation.last_message_at,
                    closed_at=conversation.closed_at,
                    close_reason=conversation.close_reason,
                    created_at=conversation.created_at,
                )
            )
            session.commit()
        return conversation

    def add_message(
        self,
        conversation_id: str,
        sender_type: str,
        sender_id: str,
        content: str,
        metadata: dict | None = None,
    ) -> ConversationMessage:
        conversation = self.get_conversation(conversation_id)
        message = ConversationMessage(
            id=self.next_id("msg"),
            conversation_id=conversation_id,
            sender_type=sender_type,
            sender_id=sender_id,
            content=content,
            metadata=metadata or {},
        )
        conversation.last_message_at = message.created_at
        with self.session_factory() as session:
            session.merge(
                ConversationMessageTable(
                    id=message.id,
                    conversation_id=message.conversation_id,
                    sender_type=message.sender_type,
                    sender_id=message.sender_id,
                    content=message.content,
                    metadata_json=message.metadata,
                    created_at=message.created_at,
                )
            )
            session.merge(
                ConversationTable(
                    id=conversation.id,
                    customer_id=conversation.customer_id,
                    status=conversation.status.value,
                    mode=conversation.mode,
                    last_message_at=conversation.last_message_at,
                    closed_at=conversation.closed_at,
                    close_reason=conversation.close_reason,
                    created_at=conversation.created_at,
                )
            )
            session.commit()
        return message

    def list_messages(self, conversation_id: str) -> list[ConversationMessage]:
        self.get_conversation(conversation_id)
        with self.session_factory() as session:
            rows = session.scalars(
                select(ConversationMessageTable)
                .where(ConversationMessageTable.conversation_id == conversation_id)
                .order_by(ConversationMessageTable.created_at, ConversationMessageTable.id)
            ).all()
            return [self._message(row) for row in rows]

    def create_handoff_ticket(self, conversation_id: str, reason: str) -> HandoffTicket:
        existing = self.find_open_ticket(conversation_id)
        if existing:
            return existing
        ticket = HandoffTicket(
            id=self.next_id("ticket"),
            conversation_id=conversation_id,
            status="pending",
            requested_reason=reason,
        )
        with self.session_factory() as session:
            session.merge(
                HandoffTicketTable(
                    id=ticket.id,
                    conversation_id=ticket.conversation_id,
                    status=ticket.status,
                    requested_reason=ticket.requested_reason,
                    requested_at=ticket.requested_at,
                    accepted_at=ticket.accepted_at,
                    closed_at=ticket.closed_at,
                )
            )
            session.commit()
        return ticket

    def find_open_ticket(self, conversation_id: str) -> HandoffTicket | None:
        with self.session_factory() as session:
            row = session.scalars(
                select(HandoffTicketTable)
                .where(
                    HandoffTicketTable.conversation_id == conversation_id,
                    HandoffTicketTable.status.in_(["pending", "claimed"]),
                )
                .order_by(HandoffTicketTable.requested_at)
            ).first()
            return self._ticket(row) if row else None

    def get_ticket(self, ticket_id: str) -> HandoffTicket:
        with self.session_factory() as session:
            row = session.get(HandoffTicketTable, ticket_id)
            if row is None:
                raise ValueError(f"handoff ticket not found: {ticket_id}")
            return self._ticket(row)

    def save_ticket(self, ticket: HandoffTicket) -> HandoffTicket:
        with self.session_factory() as session:
            session.merge(
                HandoffTicketTable(
                    id=ticket.id,
                    conversation_id=ticket.conversation_id,
                    status=ticket.status,
                    requested_reason=ticket.requested_reason,
                    requested_at=ticket.requested_at,
                    accepted_at=ticket.accepted_at,
                    closed_at=ticket.closed_at,
                )
            )
            session.commit()
        return ticket

    def list_handoff_tickets(self, status: str | None = None) -> list[HandoffTicket]:
        with self.session_factory() as session:
            statement = select(HandoffTicketTable)
            if status:
                statement = statement.where(HandoffTicketTable.status == status)
            rows = session.scalars(statement.order_by(HandoffTicketTable.requested_at)).all()
            return [self._ticket(row) for row in rows]

    def add_correction(self, correction: Correction) -> Correction:
        with self.session_factory() as session:
            session.merge(
                CorrectionTable(
                    id=correction.id,
                    question_id=correction.question_id,
                    bad_answer=correction.bad_answer,
                    fixed_answer=correction.fixed_answer,
                    reason=correction.reason,
                    created_at=correction.created_at,
                )
            )
            session.commit()
        return correction

    def add_ai_call_log(self, log: AiCallLog) -> AiCallLog:
        with self.session_factory() as session:
            session.merge(
                AiCallLogTable(
                    id=log.id,
                    request_id=log.request_id,
                    model=log.model,
                    prompt_version=log.prompt_version,
                    input_hash=log.input_hash,
                    token_in=log.token_in,
                    token_out=log.token_out,
                    latency_ms=log.latency_ms,
                    error=log.error,
                    metadata_json=log.metadata,
                    created_at=log.created_at,
                )
            )
            session.commit()
        return log

    def add_knowledge_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        with self.session_factory() as session:
            session.merge(
                KnowledgeDocumentTable(
                    id=document.id,
                    file_name=document.file_name,
                    source=document.source,
                    status=document.status,
                    chunk_count=document.chunk_count,
                    error=document.error,
                    created_at=document.created_at,
                    updated_at=document.updated_at,
                )
            )
            session.commit()
        return document

    def save_knowledge_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        document.updated_at = utcnow()
        return self.add_knowledge_document(document)

    def list_knowledge_documents(self) -> list[KnowledgeDocument]:
        with self.session_factory() as session:
            rows = session.scalars(select(KnowledgeDocumentTable).order_by(KnowledgeDocumentTable.created_at)).all()
            return [self._knowledge_document(row) for row in rows]

    def delete_knowledge_document(self, document_id: str) -> KnowledgeDocument:
        with self.session_factory() as session:
            row = session.get(KnowledgeDocumentTable, document_id)
            if row is None:
                raise ValueError(f"knowledge document not found: {document_id}")
            document = self._knowledge_document(row)
            session.execute(delete(KnowledgeChunkTable).where(KnowledgeChunkTable.document_id == document_id))
            session.delete(row)
            session.commit()
            return document

    def add_knowledge_chunk(self, chunk: KnowledgeChunk) -> KnowledgeChunk | None:
        with self.session_factory() as session:
            existing = session.scalars(
                select(KnowledgeChunkTable).where(KnowledgeChunkTable.content_hash == chunk.content_hash)
            ).first()
            if existing:
                return None
            session.merge(
                KnowledgeChunkTable(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    question_text=chunk.question_text,
                    answer_text=chunk.answer_text,
                    retrieval_text=chunk.retrieval_text,
                    chunk_text=chunk.chunk_text,
                    dense_embedding=chunk.dense_embedding,
                    sparse_vector=chunk.sparse_vector,
                    search_vector=chunk.search_text,
                    content_hash=chunk.content_hash,
                    metadata_json=chunk.metadata,
                    created_at=chunk.created_at,
                    updated_at=chunk.updated_at,
                )
            )
            session.commit()
        return chunk

    def search_knowledge_chunks(
        self,
        query: str,
        top_k: int,
        min_score: float,
        dense_weight: float,
        sparse_weight: float,
        query_embedding: list[float] | None = None,
    ) -> list[KnowledgeSearchHit]:
        with self.session_factory() as session:
            rows = session.scalars(select(KnowledgeChunkTable)).all()
            hits = []
            for row in rows:
                sparse = row.sparse_vector or {}
                score, dense_score, sparse_score = hybrid_score(
                    query=query,
                    text=row.retrieval_text,
                    sparse=sparse,
                    dense_weight=dense_weight,
                    sparse_weight=sparse_weight,
                    query_embedding=query_embedding,
                    dense_embedding=row.dense_embedding,
                )
                if score < min_score:
                    continue
                hits.append(
                    KnowledgeSearchHit(
                        id=row.id,
                        question_text=row.question_text,
                        answer_text=row.answer_text,
                        retrieval_text=row.retrieval_text,
                        chunk_text=row.chunk_text,
                        dense_score=dense_score,
                        sparse_score=sparse_score,
                        score=score,
                        metadata=row.metadata_json or {},
                    )
                )
            return sorted(hits, key=lambda hit: hit.score, reverse=True)[:top_k]

    def force_last_message_at(self, conversation_id: str, value: datetime) -> None:
        conversation = self.get_conversation(conversation_id)
        conversation.last_message_at = value
        self.save_conversation(conversation)

    def iter_conversations(self) -> Iterable[Conversation]:
        with self.session_factory() as session:
            rows = session.scalars(select(ConversationTable).order_by(ConversationTable.id)).all()
            return [self._conversation(row) for row in rows]

    def data_summary(self) -> dict[str, int]:
        with self.session_factory() as session:
            return {
                "conversations": self._count(session, ConversationTable),
                "handoff_tickets": self._count(session, HandoffTicketTable),
                "corrections": self._count(session, CorrectionTable),
                "ai_call_logs": self._count(session, AiCallLogTable),
            }

    def conversation_to_dict(self, conversation: Conversation) -> dict:
        payload = to_public_dict(conversation)
        payload["messages"] = to_public_dict(self.list_messages(conversation.id))
        ticket = self.find_open_ticket(conversation.id)
        payload["handoff_ticket"] = to_public_dict(ticket) if ticket else None
        return payload

    def close_conversation(
        self,
        conversation: Conversation,
        status: ConversationStatus,
        reason: str,
    ) -> Conversation:
        conversation.status = status
        conversation.closed_at = utcnow()
        conversation.close_reason = reason
        conversation.mode = "closed"
        self.save_conversation(conversation)
        return conversation

    def _count(self, session, table) -> int:
        return session.scalar(select(func.count()).select_from(table)) or 0

    def _conversation(self, row) -> Conversation:
        return Conversation(
            id=row.id,
            customer_id=row.customer_id,
            status=ConversationStatus(row.status),
            mode=row.mode,
            last_message_at=row.last_message_at,
            closed_at=row.closed_at,
            close_reason=row.close_reason,
            created_at=row.created_at,
        )

    def _message(self, row) -> ConversationMessage:
        return ConversationMessage(
            id=row.id,
            conversation_id=row.conversation_id,
            sender_type=row.sender_type,
            sender_id=row.sender_id,
            content=row.content,
            metadata=row.metadata_json,
            created_at=row.created_at,
        )

    def _ticket(self, row) -> HandoffTicket:
        return HandoffTicket(
            id=row.id,
            conversation_id=row.conversation_id,
            status=row.status,
            requested_reason=row.requested_reason,
            requested_at=row.requested_at,
            accepted_at=row.accepted_at,
            closed_at=row.closed_at,
        )

    def _knowledge_document(self, row) -> KnowledgeDocument:
        return KnowledgeDocument(
            id=row.id,
            file_name=row.file_name,
            source=row.source,
            status=row.status,
            chunk_count=row.chunk_count,
            error=row.error,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
