"""HTTP mapping for a chat turn, shared by production and draft test chat.

Both endpoints run turns through app.services.chat_turn_service; this keeps
their error contract (429 + Retry-After, guardrail 400) and reply shape
identical, so the frontend handles a test reply exactly like a real one.
"""

from fastapi.responses import JSONResponse

from app.api.schemas import SourceReference
from app.services.chat_turn_service import ChatAdmission, ChatTurnOutcome
from app.services.rate_limiter_service import rate_limit_exceeded_response


def refused_admission_response(admission: ChatAdmission) -> JSONResponse:
    """The response for a message admit_chat_message did not admit.

    The input guardrail's 400 carries both the stable reason code (detail)
    and the guardrail's own human-readable message, which the frontend
    prefers so the two can never drift apart.
    """
    if admission.guardrail is None:
        return rate_limit_exceeded_response(
            admission.rate_limit,
            message="Too many requests. Please wait before sending another message.",
        )
    return JSONResponse(
        status_code=400,
        content={"detail": admission.guardrail.reason, "message": admission.guardrail.message},
    )


def reply_fields(outcome: ChatTurnOutcome) -> dict:
    """The ChatResponse fields every chat reply carries."""
    return {
        "response": outcome.text,
        "thread_id": outcome.thread_id,
        "sources": [
            SourceReference(
                knowledge_base_id=source.knowledge_base_id,
                title=source.title,
                heading_path=source.heading_path,
            )
            for source in outcome.sources
        ],
        "was_modified": outcome.was_modified,
    }
