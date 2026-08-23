# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from api.schemas_chat import ChatRequest, ChatResponse
from application.task_executor import TaskExecutionError, TaskExecutor
from container import get_chat_rate_limiter, get_task_executor
from domain.workflow import TaskNode
from infrastructure.rate_limiter import client_key_from_request
from infrastructure.security import verify_user_api_key

logger = logging.getLogger("reus_veritas.api.chat")


def enforce_chat_rate_limit(request: Request) -> None:
    limiter = get_chat_rate_limiter()
    allowed, retry_after = limiter.allow(client_key_from_request(request))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Request rate limit exceeded. Please try again later.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


router = APIRouter(
    prefix="/chat",
    tags=["chat"],
    # Rate-limit before key verification. If verification came first, failed
    # key guesses would be rejected with 401 before reaching the limiter,
    # allowing unlimited guessing. This ordering prevents that bypass.
    dependencies=[Depends(enforce_chat_rate_limit), Depends(verify_user_api_key)],
)


@router.post("", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    request: Request,
    executor: TaskExecutor = Depends(get_task_executor),
) -> ChatResponse:
    """Public web entry point for free-text chat. It creates a `TaskNode`
    directly instead of traversing a full workflow state machine, then executes
    it through an executor that actually supports agentless chat, such as
    Ollama or `model_router` according to `REUS_TASK_EXECUTOR`.

    The `cognitive` executor is a valid configuration value but does not serve
    this route because it requires capability metadata that `/chat` deliberately
    does not assign. The default `DefaultTaskExecutor` also does not support
    `/chat`, because it requires a registered agent for every task. Operators
    must explicitly configure a compatible executor; otherwise this endpoint
    returns 502 with a safe availability message.
    """
    task = TaskNode(name="web_chat", payload={"prompt": body.prompt, "system": body.system})
    try:
        result = executor.execute(task)
    except TaskExecutionError as exc:
        request_id = getattr(request.state, "request_id", None)
        logger.warning(
            "chat_executor_unavailable",
            extra={"event_name": "chat_executor_unavailable", "payload": {"request_id": request_id}},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "Model service is currently unavailable.", "request_id": request_id},
        ) from exc
    return ChatResponse.from_executor_result(result)


@router.post("/stream")
def stream_chat(
    body: ChatRequest,
    request: Request,
    executor: TaskExecutor = Depends(get_task_executor),
) -> StreamingResponse:
    """Stream execution state and the final response through SSE.

    This endpoint does not claim token streaming when the executor cannot
    provide it. It guarantees a real stream from request acceptance to a
    normalized result event and can later use a token-streaming executor without
    changing the event contract.
    """

    request_id = getattr(request.state, "request_id", None)

    def events():
        yield _sse("accepted", {"request_id": request_id})
        task = TaskNode(name="web_chat", payload={"prompt": body.prompt, "system": body.system})
        try:
            result = executor.execute(task)
        except TaskExecutionError:
            logger.warning(
                "chat_stream_executor_unavailable",
                extra={"event_name": "chat_stream_executor_unavailable", "payload": {"request_id": request_id}},
                exc_info=True,
            )
            yield _sse("error", {"message": "Model service is currently unavailable.", "request_id": request_id})
            return
        yield _sse("answer", ChatResponse.from_executor_result(result).model_dump())
        yield _sse("complete", {"request_id": request_id})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
