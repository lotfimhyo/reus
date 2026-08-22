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
            detail="تجاوزت الحد المسموح من الطلبات. حاول لاحقًا.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


router = APIRouter(
    prefix="/chat",
    tags=["chat"],
    # الترتيب مقصود: تحديد المعدل قبل التحقق من المفتاح، لا بعده. لو كان
    # التحقق أولًا، لَما احتُسِبت محاولات تخمين المفتاح الفاشلة ضمن الحد
    # أصلًا (لأن الطلب يُرفَض بـ401 قبل الوصول لتحديد المعدل)، فيبقى مفتوحًا
    # لتخمين غير محدود للمفتاح. هذا الترتيب يمنع ذلك تحديدًا.
    dependencies=[Depends(enforce_chat_rate_limit), Depends(verify_user_api_key)],
)


@router.post("", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    request: Request,
    executor: TaskExecutor = Depends(get_task_executor),
) -> ChatResponse:
    """نقطة الدخول الوحيدة لواجهة الويب العامة: يُنشئ TaskNode مباشرة (بلا
    عبور آلة حالة workflow كاملة — غير ضروري لمحادثة عديمة الحالة) ويُنفِّذه
    فورًا عبر أي منفّذ يدعم فعليًا محادثة نصية حرة بلا وكيل مُسجَّل (Ollama أو
    النماذج الثانوية عبر model_router — حسب REUS_TASK_EXECUTOR). ملاحظة: منفِّذ
    "cognitive" لا يدعم هذا المسار رغم أنه أحد قيم REUS_TASK_EXECUTOR الصالحة —
    يتطلب required_capability_name/required_tags في الحمولة، وهو ما لا يُسنِده
    /chat أبدًا (اكتُشِف بالتشغيل الحي الفعلي، لا افتراضًا).

    تنبيه تشغيلي مُتحقَّق منه فعليًا: REUS_TASK_EXECUTOR الافتراضي في
    config.py هو "default" (DefaultTaskExecutor)، وهو **لا يدعم /chat**
    — يتطلب وكيلًا مُسجَّلًا مسبقًا لكل مهمة، بينما هذا المسار لا يُسنِد
    أي agent_id عمدًا. نشر بلا ضبط REUS_TASK_EXECUTOR صراحة يُنتج 502 على
    كل طلب /chat؛ الرسالة المُعادة من DefaultTaskExecutor في هذه الحالة
    تحديدًا (انظر infrastructure/default_task_executor.py) تشرح الحل."""
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
            detail={"message": "خدمة النموذج غير متاحة حالياً", "request_id": request_id},
        ) from exc
    return ChatResponse.from_executor_result(result)


@router.post("/stream")
def stream_chat(
    body: ChatRequest,
    request: Request,
    executor: TaskExecutor = Depends(get_task_executor),
) -> StreamingResponse:
    """بث حالة التنفيذ ثم الاستجابة الفعلية عبر SSE.

    لا يدعي هذا المسار بثاً رمزياً إذا كان المنفذ لا يدعمه؛ يضمن بدلاً من ذلك
    قناة streaming حقيقية تتقدم من حدث قبول الطلب إلى حدث النتيجة الموحدة.
    يمكن استبدال المنفذ لاحقاً بمنفذ token-streaming دون تغيير عقد الأحداث.
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
            yield _sse("error", {"message": "خدمة النموذج غير متاحة حالياً", "request_id": request_id})
            return
        yield _sse("answer", ChatResponse.from_executor_result(result).model_dump())
        yield _sse("complete", {"request_id": request_id})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
