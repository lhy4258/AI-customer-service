from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.core.config import settings
from app.services.ai_clients import EmbeddingClient, LlmClient
from app.services.entities import (
    AiCallLog,
    Conversation,
    ConversationMessage,
    ConversationStatus,
    Correction,
    KnowledgeChunk,
    KnowledgeDocument,
    to_public_dict,
    utcnow,
)
from app.services.knowledge_base import (
    build_upload_items,
    content_hash,
    has_prompt_attack,
    knowledge_sparse_text,
    lexical_search_text,
    sparse_vector,
)
from app.services.repository import InMemoryRepository

HANDOFF_TERMS = ("转人工", "找客服", "人工处理", "投诉人工处理", "人工客服")
GENERIC_AI_ANSWER = (
    "资料中没有找到依据，我先记录你的问题。如需继续处理，可以回复“转人工”。"
)
CLARIFICATION_ANSWER = "我需要再确认一下，您想咨询的是发货、退款、优惠、商品信息，还是其他问题？"
BUSINESS_KEYWORDS = (
    "发货",
    "物流",
    "快递",
    "退款",
    "退货",
    "换货",
    "售后",
    "优惠",
    "优惠价",
    "便宜",
    "少点",
    "价格",
    "多少钱",
    "商品",
    "宝贝",
    "衣服",
    "尺码",
    "规格",
    "库存",
    "订单",
    "包邮",
    "发票",
    "客服",
    "活动",
    "coupon",
    "discount",
    "price",
    "refund",
    "shipping",
    "delivery",
    "order",
    "product",
)
AMBIGUOUS_REFERENCES = ("这个", "那个", "它", "他", "她", "这件", "那件", "上面", "刚才", "之前", "怎么办", "怎么弄")
CONTEXT_MESSAGE_LIMIT = 6


CONFIDENCE_EXPLANATION = (
    "confidence is the top returned chunk hybrid score after min_score filtering; "
    "score = dense_score * HYBRID_DENSE_WEIGHT + sparse_score * HYBRID_SPARSE_WEIGHT; "
    "when no chunk is returned, confidence = 0.0"
)


def _score(value: Any) -> float:
    return round(float(value), 4)


@dataclass(frozen=True)
class QueryContext:
    original_query: str
    rewritten_query: str
    action: str
    reason: str | None
    recent_messages: list[dict[str, str]]

    @property
    def should_clarify(self) -> bool:
        return self.action == "clarify"

    def to_metadata(self) -> dict[str, Any]:
        payload = {
            "original_query": self.original_query,
            "rewritten_query": self.rewritten_query,
            "action": self.action,
            "reason": self.reason,
            "recent_messages_count": len(self.recent_messages),
            "recent_messages": self.recent_messages,
        }
        return payload


class AnswerService:
    def __init__(self, repository: InMemoryRepository) -> None:
        self.repository = repository
        self.embedding_client = EmbeddingClient()
        self.llm_client = LlmClient()

    def generate(
        self,
        query: str,
        conversation: Conversation,
        recent_messages: list[ConversationMessage] | None = None,
    ) -> dict[str, Any]:
        query_context = self._build_query_context(query, recent_messages or [])
        if query_context.should_clarify:
            retrieval = self._clarification_observability(query_context)
            return {
                "answer": CLARIFICATION_ANSWER,
                "confidence": 0.0,
                "confidence_explanation": CONFIDENCE_EXPLANATION,
                "handoff_suggested": False,
                "citations": [],
                "chunks": [],
                "retrieval": retrieval,
            }

        retrieval_query = query_context.rewritten_query
        query_embedding = self._query_embedding(retrieval_query)
        hits = self.repository.search_knowledge_chunks(
            query=retrieval_query,
            top_k=settings.retrieval_top_k,
            min_score=settings.retrieval_min_score,
            dense_weight=settings.hybrid_dense_weight,
            sparse_weight=settings.hybrid_sparse_weight,
            query_embedding=query_embedding,
        )
        retrieval = self._retrieval_observability(query_context, query_embedding, hits)
        if not hits:
            return {
                "answer": GENERIC_AI_ANSWER,
                "confidence": 0.0,
                "confidence_explanation": CONFIDENCE_EXPLANATION,
                "handoff_suggested": True,
                "citations": [],
                "chunks": [],
                "retrieval": retrieval,
            }

        best_hit = hits[0]
        confidence = _score(best_hit.score)
        answer = self._grounded_answer(
            query=retrieval_query,
            answer_text=best_hit.answer_text,
            context="\n\n".join(hit.retrieval_text for hit in hits),
        )
        return {
            "answer": answer,
            "confidence": confidence,
            "confidence_explanation": CONFIDENCE_EXPLANATION,
                "handoff_suggested": False,
            "citations": [{"chunk_id": hit.id, "score": _score(hit.score)} for hit in hits],
            "chunks": [
                {
                    "id": hit.id,
                    "question_text": hit.question_text,
                    "answer_text": hit.answer_text,
                    "retrieval_text": hit.retrieval_text,
                    "score": _score(hit.score),
                    "dense_score": _score(hit.dense_score),
                    "sparse_score": _score(hit.sparse_score),
                }
                for hit in hits
            ],
            "retrieval": retrieval,
        }

    def _retrieval_observability(
        self,
        query_context: QueryContext,
        query_embedding: list[float] | None,
        hits: list[Any],
    ) -> dict[str, Any]:
        query = query_context.rewritten_query
        query_sparse = sparse_vector(query)
        hit_payloads = [self._hit_observability(hit, query_sparse) for hit in hits]
        selected_chunk = None
        confidence = 0.0
        confidence_source = "no_retrieved_chunks"
        if hit_payloads:
            first_hit = hit_payloads[0]
            confidence = first_hit["score"]
            confidence_source = "top_hybrid_score"
            selected_chunk = {
                "chunk_id": first_hit["chunk_id"],
                "question_text": first_hit["question_text"],
                "answer_text": first_hit["answer_text"],
                "retrieval_text": first_hit["retrieval_text"],
                "score": first_hit["score"],
                "dense_score": first_hit["dense_score"],
                "sparse_score": first_hit["sparse_score"],
            }

        return {
            "schema_version": "retrieval-observability-v1",
            "query_text": query,
            "original_query_text": query_context.original_query,
            "contextualization": query_context.to_metadata(),
            "clarification": {
                "action": "answer",
                "reason": None,
            },
            "query_sparse_vector": self._sparse_vector_payload(query_sparse),
            "query_dense_embedding": {
                "model": settings.embedding_model,
                "configured": self.embedding_client.is_configured(),
                "available": query_embedding is not None,
                "dimension": len(query_embedding) if query_embedding is not None else 0,
                "stored_in_log": False,
            },
            "strategy": "hybrid_dense_sparse",
            "top_k_requested": settings.retrieval_top_k,
            "min_score": settings.retrieval_min_score,
            "dense_weight": settings.hybrid_dense_weight,
            "sparse_weight": settings.hybrid_sparse_weight,
            "returned_count": len(hit_payloads),
            "hits": hit_payloads,
            "selected_chunk": selected_chunk,
            "confidence": {
                "value": confidence,
                "source": confidence_source,
                "formula": (
                    f"score = dense_score * {settings.hybrid_dense_weight} "
                    f"+ sparse_score * {settings.hybrid_sparse_weight}"
                ),
                "min_score": settings.retrieval_min_score,
            },
        }

    def _clarification_observability(self, query_context: QueryContext) -> dict[str, Any]:
        query_sparse = sparse_vector(query_context.rewritten_query)
        return {
            "schema_version": "retrieval-observability-v1",
            "query_text": query_context.rewritten_query,
            "original_query_text": query_context.original_query,
            "contextualization": query_context.to_metadata(),
            "clarification": {
                "action": "clarify",
                "reason": query_context.reason,
                "answer": CLARIFICATION_ANSWER,
            },
            "query_sparse_vector": self._sparse_vector_payload(query_sparse),
            "query_dense_embedding": {
                "model": settings.embedding_model,
                "configured": self.embedding_client.is_configured(),
                "available": False,
                "dimension": 0,
                "stored_in_log": False,
            },
            "strategy": "clarification_before_retrieval",
            "top_k_requested": settings.retrieval_top_k,
            "min_score": settings.retrieval_min_score,
            "dense_weight": settings.hybrid_dense_weight,
            "sparse_weight": settings.hybrid_sparse_weight,
            "returned_count": 0,
            "hits": [],
            "selected_chunk": None,
            "confidence": {
                "value": 0.0,
                "source": "clarification_required",
                "formula": (
                    f"score = dense_score * {settings.hybrid_dense_weight} "
                    f"+ sparse_score * {settings.hybrid_sparse_weight}"
                ),
                "min_score": settings.retrieval_min_score,
            },
        }

    def _hit_observability(self, hit: Any, query_sparse: dict[str, float]) -> dict[str, Any]:
        sparse_text = hit.retrieval_text
        chunk_sparse = sparse_vector(sparse_text)
        matched_terms = sorted(
            set(query_sparse) & set(chunk_sparse),
            key=lambda term: (-query_sparse[term], term),
        )
        return {
            "chunk_id": hit.id,
            "question_text": hit.question_text,
            "answer_text": hit.answer_text,
            "retrieval_text": hit.retrieval_text,
            "chunk_text": hit.chunk_text,
            "score": _score(hit.score),
            "dense_score": _score(hit.dense_score),
            "sparse_score": _score(hit.sparse_score),
            "matched_sparse_terms": matched_terms,
            "chunk_sparse_vector_preview": self._sparse_vector_payload(chunk_sparse, limit=30),
            "metadata": hit.metadata,
        }

    def _sparse_vector_payload(self, vector: dict[str, float], limit: int | None = None) -> dict[str, float]:
        items = sorted(vector.items(), key=lambda item: (-item[1], item[0]))
        if limit is not None:
            items = items[:limit]
        return {term: _score(weight) for term, weight in items}

    def _grounded_answer(self, query: str, answer_text: str, context: str) -> str:
        if has_prompt_attack(query):
            return answer_text or GENERIC_AI_ANSWER
        try:
            generated = self.llm_client.answer_with_context(query=query, context=context)
        except Exception:
            return answer_text or GENERIC_AI_ANSWER
        if not generated or has_prompt_attack(generated):
            return answer_text or GENERIC_AI_ANSWER
        return generated

    def _query_embedding(self, query: str) -> list[float] | None:
        try:
            return self.embedding_client.embed(query)
        except Exception:
            return None

    def _build_query_context(self, query: str, recent_messages: list[ConversationMessage]) -> QueryContext:
        context_payload = self._recent_message_payloads(recent_messages)
        current_has_business = self._has_business_keyword(query)
        context_text = "\n".join(
            message["content"]
            for message in context_payload
            if message["sender_type"] == "user"
        )
        context_has_business = self._has_business_keyword(context_text)
        current_is_ambiguous = self._is_ambiguous_query(query)

        if current_is_ambiguous and not context_has_business:
            return QueryContext(
                original_query=query,
                rewritten_query=query,
                action="clarify",
                reason="ambiguous_query_without_business_context",
                recent_messages=context_payload,
            )
        if not current_has_business and not context_has_business:
            return QueryContext(
                original_query=query,
                rewritten_query=query,
                action="clarify",
                reason="missing_business_keywords",
                recent_messages=context_payload,
            )

        rewritten_query = query
        action = "none"
        reason = None
        if current_is_ambiguous and context_has_business:
            context_focus = self._business_context_summary(context_payload)
            rewritten_query = f"{context_focus} {query}".strip()
            action = "rewrite"
            reason = "ambiguous_query_resolved_from_recent_context"

        return QueryContext(
            original_query=query,
            rewritten_query=rewritten_query,
            action=action,
            reason=reason,
            recent_messages=context_payload,
        )

    def _recent_message_payloads(self, messages: list[ConversationMessage]) -> list[dict[str, str]]:
        payloads = []
        for message in messages[-CONTEXT_MESSAGE_LIMIT:]:
            if message.sender_type not in {"user", "ai", "human"}:
                continue
            content = " ".join(message.content.split())
            if not content:
                continue
            payloads.append(
                {
                    "id": message.id,
                    "sender_type": message.sender_type,
                    "content": content[:300],
                }
            )
        return payloads

    def _has_business_keyword(self, text: str) -> bool:
        return any(keyword in text for keyword in BUSINESS_KEYWORDS)

    def _is_ambiguous_query(self, query: str) -> bool:
        query_sparse = sparse_vector(query)
        business_terms = {term for term in query_sparse if self._has_business_keyword(term)}
        if any(reference in query for reference in AMBIGUOUS_REFERENCES) and not business_terms:
            return True
        meaningful_terms = [term for term in query_sparse if len(term) > 1]
        return len(meaningful_terms) <= 1 and not business_terms

    def _business_context_summary(self, messages: list[dict[str, str]]) -> str:
        for message in reversed(messages):
            content = message["content"]
            if message["sender_type"] == "user" and self._has_business_keyword(content):
                return content
        for message in reversed(messages):
            content = message["content"]
            if self._has_business_keyword(content):
                return content
        return ""


class CustomerServiceFacade:
    def __init__(self, repository: InMemoryRepository) -> None:
        self.repository = repository
        self.answer_service = AnswerService(repository)
        self.embedding_client = EmbeddingClient()

    @classmethod
    def empty(cls) -> "CustomerServiceFacade":
        return cls(InMemoryRepository())

    def data_summary(self) -> dict[str, int]:
        return self.repository.data_summary()

    def ingest_training_corpus(self, file_name: str, content: str, source: str = "training-corpus") -> dict[str, Any]:
        return self.ingest_knowledge_text(file_name=file_name, content=content, source=source)

    def create_knowledge_document(self, file_name: str, source: str = "manual-upload") -> KnowledgeDocument:
        document = KnowledgeDocument(
            id=self.repository.next_id("doc"),
            file_name=file_name,
            source=source,
            status="processing",
        )
        self.repository.add_knowledge_document(document)
        return document

    def ingest_knowledge_text(self, file_name: str, content: str, source: str = "manual-upload") -> dict[str, Any]:
        document = self.create_knowledge_document(file_name=file_name, source=source)
        self.process_knowledge_document(document, content, source)
        return to_public_dict(document)

    def process_knowledge_document(
        self,
        document: KnowledgeDocument,
        content: str,
        source: str = "manual-upload",
        raise_errors: bool = True,
    ) -> None:
        try:
            items = build_upload_items(content)
            inserted = 0
            for item in items:
                current = self._knowledge_document(document.id)
                if current.status == "canceled":
                    document.status = "canceled"
                    document.chunk_count = inserted
                    self.repository.save_knowledge_document(document)
                    return
                retrieval_text = item.retrieval_text
                sparse_text = knowledge_sparse_text(item)
                chunk = KnowledgeChunk(
                    id=self.repository.next_id("kchunk"),
                    document_id=document.id,
                    question_text=item.question_text,
                    answer_text=item.answer_text,
                    retrieval_text=retrieval_text,
                    chunk_text=retrieval_text,
                    dense_embedding=self.embedding_client.embed(retrieval_text),
                    sparse_vector=sparse_vector(sparse_text),
                    search_text=lexical_search_text(sparse_text),
                    content_hash=content_hash(retrieval_text),
                    metadata={"source": source, "file_name": document.file_name},
                )
                if self.repository.add_knowledge_chunk(chunk):
                    inserted += 1
            document.chunk_count = inserted
            document.status = "ready"
            self.repository.save_knowledge_document(document)
        except Exception as exc:
            document.status = "failed"
            document.error = str(exc)
            self.repository.save_knowledge_document(document)
            if raise_errors:
                raise

    def list_knowledge_documents(self) -> list[dict[str, Any]]:
        return to_public_dict(self.repository.list_knowledge_documents())

    def cancel_knowledge_document(self, document_id: str) -> dict[str, Any]:
        document = self._knowledge_document(document_id)
        if document.status != "processing":
            raise ValueError("only processing knowledge documents can be canceled")
        document.status = "canceled"
        self.repository.save_knowledge_document(document)
        return to_public_dict(document)

    def delete_knowledge_document(self, document_id: str) -> dict[str, Any]:
        document = self._knowledge_document(document_id)
        if document.status == "processing":
            raise ValueError("processing knowledge document must be canceled before delete")
        return to_public_dict(self.repository.delete_knowledge_document(document_id))

    def _knowledge_document(self, document_id: str) -> KnowledgeDocument:
        for document in self.repository.list_knowledge_documents():
            if document.id == document_id:
                return document
        raise ValueError(f"knowledge document not found: {document_id}")

    def chat(
        self,
        customer_id: str,
        content: str,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        conversation = self._get_or_create_conversation(customer_id, conversation_id)
        self._ensure_open(conversation)
        recent_messages = self.repository.list_messages(conversation.id)[-CONTEXT_MESSAGE_LIMIT:]
        self.repository.add_message(conversation.id, "user", customer_id, content)

        if conversation.status in {ConversationStatus.HANDOFF_REQUESTED, ConversationStatus.HUMAN_ACTIVE}:
            return self._waiting_for_human_response(conversation)

        if self._is_handoff_intent(content):
            return self.request_handoff(conversation.id, "explicit_user_request")

        start = time.perf_counter()
        generated = self.answer_service.generate(content, conversation, recent_messages)
        latency_ms = int((time.perf_counter() - start) * 1000)
        message = self.repository.add_message(
            conversation.id,
            "ai",
            "ai-customer-service",
            generated["answer"],
            metadata={
                "citations": generated["citations"],
                "confidence": generated["confidence"],
                "confidence_explanation": generated["confidence_explanation"],
                "handoff_suggested": generated["handoff_suggested"],
                "retrieval": generated["retrieval"],
            },
        )
        self._log_ai_call(
            prompt=content,
            answer=generated["answer"],
            latency_ms=latency_ms,
            error=None,
            conversation_id=conversation.id,
            message_id=message.id,
            retrieval=generated["retrieval"],
            confidence=generated["confidence"],
            handoff_suggested=generated["handoff_suggested"],
        )
        return {
            "conversation_id": conversation.id,
            "message_id": message.id,
            "status": conversation.status.value,
            "answer": generated["answer"],
            "confidence": generated["confidence"],
            "citations": generated["citations"],
            "chunks": generated["chunks"],
            "handoff_requested": False,
            "handoff_suggested": generated["handoff_suggested"],
        }

    def request_handoff(self, conversation_id: str, reason: str) -> dict[str, Any]:
        conversation = self.repository.get_conversation(conversation_id)
        self._ensure_open(conversation)
        conversation.status = ConversationStatus.HANDOFF_REQUESTED
        conversation.mode = "handoff"
        self.repository.save_conversation(conversation)
        ticket = self.repository.create_handoff_ticket(conversation_id, reason)
        message = self.repository.add_message(
            conversation_id,
            "system",
            "handoff",
            "已为你转接人工客服，请稍候。",
            {"ticket_id": ticket.id},
        )
        return {
            "conversation_id": conversation_id,
            "message_id": message.id,
            "ticket_id": ticket.id,
            "status": conversation.status.value,
            "answer": message.content,
            "confidence": 1.0,
            "citations": [],
            "chunks": [],
            "handoff_requested": True,
            "handoff_suggested": False,
        }

    def list_handoff_tickets(self, status: str | None = "pending") -> list[dict[str, Any]]:
        return [to_public_dict(ticket) for ticket in self.repository.list_handoff_tickets(status=status)]

    def claim_ticket(self, ticket_id: str) -> dict[str, Any]:
        ticket = self.repository.get_ticket(ticket_id)
        if ticket.status != "pending":
            raise ValueError("handoff ticket is not pending")
        conversation = self.repository.get_conversation(ticket.conversation_id)
        if conversation.status != ConversationStatus.HANDOFF_REQUESTED:
            raise ValueError("conversation is not waiting for handoff")
        ticket.status = "claimed"
        ticket.accepted_at = utcnow()
        self.repository.save_ticket(ticket)
        conversation.status = ConversationStatus.HUMAN_ACTIVE
        conversation.mode = "human"
        self.repository.save_conversation(conversation)
        self.repository.add_message(
            conversation.id,
            "system",
            "handoff",
            "人工客服已接入会话。",
            {"ticket_id": ticket.id},
        )
        return to_public_dict(ticket)

    def human_reply(self, conversation_id: str, content: str) -> dict[str, Any]:
        conversation = self.repository.get_conversation(conversation_id)
        if conversation.status != ConversationStatus.HUMAN_ACTIVE:
            raise ValueError("conversation is not human_active")
        ticket = self.repository.find_open_ticket(conversation_id)
        if not ticket or ticket.status != "claimed":
            raise ValueError("handoff ticket has not been claimed")
        message = self.repository.add_message(
            conversation_id,
            "human",
            "human-support",
            content,
            {"ticket_id": ticket.id},
        )
        return to_public_dict(message)

    def close_by_human_support(self, conversation_id: str, reason: str) -> dict[str, Any]:
        conversation = self.repository.get_conversation(conversation_id)
        if conversation.status != ConversationStatus.HUMAN_ACTIVE:
            raise ValueError("only human_active conversations can be closed by human support")
        ticket = self.repository.find_open_ticket(conversation_id)
        if not ticket or ticket.status != "claimed":
            raise ValueError("handoff ticket has not been claimed")
        ticket.status = "closed"
        ticket.closed_at = utcnow()
        self.repository.save_ticket(ticket)
        self.repository.add_message(
            conversation_id,
            "system",
            "handoff",
            "人工客服已结束本次服务，如需继续咨询请重新发起会话。",
            {"reason": reason},
        )
        closed = self.repository.close_conversation(conversation, ConversationStatus.HUMAN_CLOSED, reason)
        return to_public_dict(closed)

    def auto_close_idle_ai_sessions(self, now: datetime) -> dict[str, list[str]]:
        closed_ids = []
        threshold = now - timedelta(seconds=60)
        for conversation in list(self.repository.iter_conversations()):
            if conversation.status != ConversationStatus.AI_ACTIVE:
                continue
            if conversation.last_message_at > threshold:
                continue
            closed = self.repository.close_conversation(
                conversation,
                ConversationStatus.AUTO_CLOSED,
                "idle_timeout",
            )
            self.repository.add_message(
                closed.id,
                "system",
                "lifecycle",
                "AI 会话超过 1 分钟无新消息，已自动结束。",
                {"reason": "idle_timeout"},
            )
            closed_ids.append(closed.id)
        return {"closed": closed_ids}

    def record_correction(
        self,
        question_id: str,
        bad_answer: str,
        fixed_answer: str,
        reason: str,
    ) -> dict[str, Any]:
        correction = Correction(
            id=self.repository.next_id("corr"),
            question_id=question_id,
            bad_answer=bad_answer,
            fixed_answer=fixed_answer,
            reason=reason,
        )
        self.repository.add_correction(correction)
        return to_public_dict(correction)

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        return self.repository.conversation_to_dict(self.repository.get_conversation(conversation_id))

    def get_events(self, conversation_id: str) -> list[dict[str, Any]]:
        events = []
        for message in self.repository.list_messages(conversation_id):
            events.append(
                {
                    "event": "message",
                    "id": message.id,
                    "data": to_public_dict(message),
                }
            )
        return events

    def _get_or_create_conversation(
        self,
        customer_id: str,
        conversation_id: str | None,
    ) -> Conversation:
        if conversation_id:
            return self.repository.get_conversation(conversation_id)
        return self.repository.create_conversation(customer_id)

    def _ensure_open(self, conversation: Conversation) -> None:
        if conversation.status in {ConversationStatus.HUMAN_CLOSED, ConversationStatus.AUTO_CLOSED}:
            raise ValueError("conversation is closed; start a new conversation")

    def _waiting_for_human_response(self, conversation: Conversation) -> dict[str, Any]:
        content = "已记录你的消息，人工客服会在当前会话中继续处理。"
        message = self.repository.add_message(
            conversation.id,
            "system",
            "handoff",
            content,
            {"status": conversation.status.value},
        )
        return {
            "conversation_id": conversation.id,
            "message_id": message.id,
            "status": conversation.status.value,
            "answer": content,
            "confidence": 1.0,
            "citations": [],
            "chunks": [],
            "handoff_requested": conversation.status == ConversationStatus.HANDOFF_REQUESTED,
            "handoff_suggested": False,
        }

    def _is_handoff_intent(self, content: str) -> bool:
        return any(term in content for term in HANDOFF_TERMS)

    def _log_ai_call(
        self,
        prompt: str,
        answer: str,
        latency_ms: int,
        error: str | None,
        conversation_id: str,
        message_id: str,
        retrieval: dict[str, Any],
        confidence: float,
        handoff_suggested: bool,
    ) -> None:
        log = AiCallLog(
            id=self.repository.next_id("ailog"),
            request_id=str(uuid.uuid4()),
            model="local-dialog-summary",
            prompt_version="customer-service-dialog-v1",
            input_hash=hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
            token_in=max(1, len(prompt) // 2),
            token_out=max(1, len(answer) // 2),
            latency_ms=latency_ms,
            error=error,
            metadata={
                "conversation_id": conversation_id,
                "message_id": message_id,
                "confidence": confidence,
                "confidence_explanation": CONFIDENCE_EXPLANATION,
                "handoff_suggested": handoff_suggested,
                "retrieval": retrieval,
            },
        )
        self.repository.add_ai_call_log(log)
