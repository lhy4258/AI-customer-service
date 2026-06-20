from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    customer_id: str
    content: str
    conversation_id: str | None = None


class HandoffRequest(BaseModel):
    reason: str = "manual_request"


class ReplyRequest(BaseModel):
    content: str


class CloseRequest(BaseModel):
    reason: str = "resolved"


class CorrectionRequest(BaseModel):
    question_id: str
    bad_answer: str
    fixed_answer: str
    reason: str


class KnowledgeUploadRequest(BaseModel):
    file_name: str
    content: str
    source: str = "manual-upload"
