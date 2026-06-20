from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.api.deps import get_customer_service
from app.schemas.customer_service import (
    ChatRequest,
    CloseRequest,
    CorrectionRequest,
    HandoffRequest,
    KnowledgeUploadRequest,
    ReplyRequest,
)
from app.services.customer_service import CustomerServiceFacade
from app.services.entities import to_public_dict
from app.services.realtime import connection_manager

router = APIRouter(prefix="/api/v1/customer-service", tags=["customer-service"])
ServiceDep = Annotated[CustomerServiceFacade, Depends(get_customer_service)]


def _handle_value_error(error: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


async def _broadcast_new_messages(service: CustomerServiceFacade, conversation_id: str, seen_ids: set[str]) -> None:
    messages = service.repository.list_messages(conversation_id)
    for message in messages:
        if message.id in seen_ids:
            continue
        await connection_manager.broadcast(
            conversation_id,
            {
                "event": "message",
                "conversation_id": conversation_id,
                "message": to_public_dict(message),
            },
        )


def _message_ids(service: CustomerServiceFacade, conversation_id: str | None) -> set[str]:
    if not conversation_id:
        return set()
    try:
        return {message.id for message in service.repository.list_messages(conversation_id)}
    except ValueError:
        return set()


@router.get("/summary")
def summary(service: ServiceDep) -> dict:
    return service.data_summary()


@router.post("/chat")
async def chat(payload: ChatRequest, service: ServiceDep) -> dict:
    seen_ids = _message_ids(service, payload.conversation_id)
    try:
        response = service.chat(
            customer_id=payload.customer_id,
            content=payload.content,
            conversation_id=payload.conversation_id,
        )
        await _broadcast_new_messages(service, response["conversation_id"], seen_ids)
        return response
    except ValueError as error:
        raise _handle_value_error(error)


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, service: ServiceDep) -> dict:
    try:
        return service.get_conversation(conversation_id)
    except ValueError as error:
        raise _handle_value_error(error)


@router.post("/conversations/{conversation_id}/handoff")
async def request_handoff(conversation_id: str, payload: HandoffRequest, service: ServiceDep) -> dict:
    seen_ids = _message_ids(service, conversation_id)
    try:
        response = service.request_handoff(conversation_id, payload.reason)
        await _broadcast_new_messages(service, conversation_id, seen_ids)
        return response
    except ValueError as error:
        raise _handle_value_error(error)


@router.get("/admin/handoff-tickets")
def list_handoff_tickets(service: ServiceDep, status: str | None = "pending") -> list[dict]:
    return service.list_handoff_tickets(status=status)


@router.post("/admin/handoff-tickets/{ticket_id}/claim")
async def claim_ticket(ticket_id: str, service: ServiceDep) -> dict:
    try:
        ticket = service.repository.get_ticket(ticket_id)
        seen_ids = _message_ids(service, ticket.conversation_id)
        response = service.claim_ticket(ticket_id)
        await _broadcast_new_messages(service, response["conversation_id"], seen_ids)
        return response
    except ValueError as error:
        raise _handle_value_error(error)


@router.post("/admin/conversations/{conversation_id}/reply")
async def human_reply(conversation_id: str, payload: ReplyRequest, service: ServiceDep) -> dict:
    seen_ids = _message_ids(service, conversation_id)
    try:
        response = service.human_reply(conversation_id, payload.content)
        await _broadcast_new_messages(service, conversation_id, seen_ids)
        return response
    except ValueError as error:
        raise _handle_value_error(error)


@router.post("/admin/conversations/{conversation_id}/close")
async def close_by_human_support(conversation_id: str, payload: CloseRequest, service: ServiceDep) -> dict:
    seen_ids = _message_ids(service, conversation_id)
    try:
        response = service.close_by_human_support(conversation_id, payload.reason)
        await _broadcast_new_messages(service, conversation_id, seen_ids)
        return response
    except ValueError as error:
        raise _handle_value_error(error)


@router.websocket("/ws/conversations/{conversation_id}")
async def conversation_websocket(websocket: WebSocket, conversation_id: str, service: ServiceDep) -> None:
    try:
        service.repository.get_conversation(conversation_id)
    except ValueError:
        await websocket.close(code=1008, reason="conversation not found")
        return
    await connection_manager.connect(conversation_id, websocket)
    try:
        await websocket.send_json({"event": "connected", "conversation_id": conversation_id})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connection_manager.disconnect(conversation_id, websocket)


@router.get("/conversations/{conversation_id}/events")
def conversation_events(conversation_id: str, service: ServiceDep) -> StreamingResponse:
    try:
        events = service.get_events(conversation_id)
    except ValueError as error:
        raise _handle_value_error(error)

    def stream():
        for event in events:
            data = json.dumps(event["data"], ensure_ascii=False)
            yield f"event: {event['event']}\nid: {event['id']}\ndata: {data}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/corrections")
def record_correction(payload: CorrectionRequest, service: ServiceDep) -> dict:
    return service.record_correction(
        question_id=payload.question_id,
        bad_answer=payload.bad_answer,
        fixed_answer=payload.fixed_answer,
        reason=payload.reason,
    )


@router.post("/admin/lifecycle/auto-close-idle")
async def auto_close_idle(service: ServiceDep) -> dict:
    before = {conversation.id: _message_ids(service, conversation.id) for conversation in service.repository.iter_conversations()}
    response = service.auto_close_idle_ai_sessions(datetime.now(timezone.utc))
    for conversation_id in response["closed"]:
        await _broadcast_new_messages(service, conversation_id, before.get(conversation_id, set()))
    return response


@router.post("/admin/knowledge/upload")
def upload_knowledge(payload: KnowledgeUploadRequest, background_tasks: BackgroundTasks, service: ServiceDep) -> dict:
    try:
        document = service.create_knowledge_document(file_name=payload.file_name, source=payload.source)
        background_tasks.add_task(service.process_knowledge_document, document, payload.content, payload.source, False)
        return to_public_dict(document)
    except ValueError as error:
        raise _handle_value_error(error)


@router.get("/admin/knowledge/documents")
def list_knowledge_documents(service: ServiceDep) -> list[dict]:
    return service.list_knowledge_documents()


@router.post("/admin/knowledge/documents/{document_id}/cancel")
def cancel_knowledge_document(document_id: str, service: ServiceDep) -> dict:
    try:
        return service.cancel_knowledge_document(document_id)
    except ValueError as error:
        raise _handle_value_error(error)


@router.delete("/admin/knowledge/documents/{document_id}")
def delete_knowledge_document(document_id: str, service: ServiceDep) -> dict:
    try:
        return service.delete_knowledge_document(document_id)
    except ValueError as error:
        raise _handle_value_error(error)
