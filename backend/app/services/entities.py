from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConversationStatus(str, Enum):
    AI_ACTIVE = "ai_active"
    HANDOFF_REQUESTED = "handoff_requested"
    HUMAN_ACTIVE = "human_active"
    HUMAN_CLOSED = "human_closed"
    AUTO_CLOSED = "auto_closed"


@dataclass
class Conversation:
    id: str
    customer_id: str
    status: ConversationStatus = ConversationStatus.AI_ACTIVE
    mode: str = "ai"
    last_message_at: datetime = field(default_factory=utcnow)
    closed_at: datetime | None = None
    close_reason: str | None = None
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class ConversationMessage:
    id: str
    conversation_id: str
    sender_type: str
    sender_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class HandoffTicket:
    id: str
    conversation_id: str
    status: str
    requested_reason: str
    requested_at: datetime = field(default_factory=utcnow)
    accepted_at: datetime | None = None
    closed_at: datetime | None = None


@dataclass
class Correction:
    id: str
    question_id: str
    bad_answer: str
    fixed_answer: str
    reason: str
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class AiCallLog:
    id: str
    request_id: str
    model: str
    prompt_version: str
    input_hash: str
    token_in: int
    token_out: int
    latency_ms: int
    error: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class KnowledgeDocument:
    id: str
    file_name: str
    source: str
    status: str
    chunk_count: int = 0
    error: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


@dataclass
class KnowledgeChunk:
    id: str
    document_id: str
    question_text: str
    answer_text: str
    retrieval_text: str
    chunk_text: str
    dense_embedding: list[float] | None
    sparse_vector: dict[str, float]
    search_text: str
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


def to_public_dict(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {key: to_public_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [to_public_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_public_dict(item) for key, item in value.items()}
    return value
