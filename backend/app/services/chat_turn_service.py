"""One chat turn, shared by production chat and draft test chat (issue #84).

POST /api/agents/chat runs a thread's published workflow version;
POST /api/workflows/{name}/versions/{id}/test-chat runs any saved version
for an admin. Both go through these two functions so the rate limit, both
guardrails, tracing metadata and per-turn version record cannot drift apart
between the two - a draft must be tested under exactly production's rules.

The caller resolves the thread and the workflow version in between
(admission comes first, so a rejected message never creates a thread or
reaches the LLM) and maps outcomes to HTTP.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from langchain_core.messages import HumanMessage
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import ConversationThread
from app.guardrails.input_guardrail import GuardrailVerdict, InputGuardrailResult
from app.mcp_client.doc_search_client import Source
from app.repositories import ChatTurnVersionRepository, ThreadRepository
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services.chat_guardrail_service import check_input_guardrail, filter_agent_response
from app.services.guardrail_config_service import GuardrailConfig, resolve_guardrail_config
from app.services.rate_limit_config_service import resolve_rate_limit_config
from app.services.rate_limiter_service import RateLimitCheckResult, check_chat_rate_limit
from app.services.workflow_service import ResolvedWorkflow
from app.workflows.primitives import extract_sources_from_messages

# Recorded on every turn and in Phoenix trace metadata, so production
# traffic and an admin's test runs are never confused with one another.
RunKind = Literal["production", "test"]


@dataclass(frozen=True)
class ChatAdmission:
    """Whether a message may run, and the guardrail config it runs under.

    rate_limit is checked first; guardrail is None when the rate limit
    already refused the message, since it was never evaluated.
    """

    rate_limit: RateLimitCheckResult
    guardrail: InputGuardrailResult | None
    guardrail_config: GuardrailConfig

    @property
    def admitted(self) -> bool:
        return self.guardrail is not None and self.guardrail.verdict != GuardrailVerdict.REJECTED


@dataclass(frozen=True)
class ChatTurnOutcome:
    """The guarded reply to one admitted message."""

    text: str
    thread_id: str
    sources: list[Source]
    was_modified: bool


def admit_chat_message(db: Session, *, user_id: str, message: str, now: datetime) -> ChatAdmission:
    """Rate-limit then input-guardrail one message.

    Test chat shares the caller's production chat bucket: a test turn costs
    the same inference, and a second bucket would double an admin's budget
    against the same LLM. The SystemSettings row is fetched once and shared
    by both resolvers (config can't legitimately change mid-request).

    A guardrail rejection writes its audit entry; the caller commits it.
    """
    db_settings = SystemSettingsRepository(db).get()
    guardrail_config = resolve_guardrail_config(db, db_settings)

    rate_limit = check_chat_rate_limit(
        db, user_id=user_id, now=now, config=resolve_rate_limit_config(db, db_settings)
    )
    if not rate_limit.allowed:
        return ChatAdmission(
            rate_limit=rate_limit, guardrail=None, guardrail_config=guardrail_config
        )

    guardrail = check_input_guardrail(
        db, message=message, actor_user_id=user_id, now=now, config=guardrail_config
    )
    return ChatAdmission(
        rate_limit=rate_limit, guardrail=guardrail, guardrail_config=guardrail_config
    )


async def run_chat_turn(
    db: Session,
    *,
    user: dict,
    thread: ConversationThread,
    workflow: ResolvedWorkflow,
    message: str,
    guardrail_config: GuardrailConfig,
    run_kind: RunKind,
    now: datetime,
) -> ChatTurnOutcome:
    """Run workflow on thread, guard the reply, record the turn, commit.

    The output guardrail's leak detector compares against the prompts of
    the version that actually ran - a draft's in test chat - never the
    published version's.
    """
    agent_definition = workflow.agent_definition
    agent = agent_definition.factory(db, user["access_token"], settings.doc_search_mcp_url)
    result = await agent.ainvoke(
        {
            "messages": [HumanMessage(content=message)],
            "thread_id": thread.id,
            "user_id": user["user_id"],
            "step_outputs": {},
        },
        config={
            "configurable": {"thread_id": thread.id},
            # Tags every Phoenix span of this run (epic #80 invariant 2: the
            # version ID travels everywhere).
            "metadata": {
                "workflow_name": workflow.workflow_name,
                "workflow_version_id": workflow.version_id,
                "workflow_run_kind": run_kind,
            },
        },
    )

    filtered = filter_agent_response(
        db,
        final_message=result["messages"][-1],
        system_prompt=agent_definition.guarded_prompt_text,
        actor_user_id=user["user_id"],
        thread_id=thread.id,
        config=guardrail_config,
        now=now,
    )

    ThreadRepository(db).touch(thread.id, now=now)
    ChatTurnVersionRepository(db).record(
        user_id=user["user_id"],
        thread_id=thread.id,
        workflow_name=workflow.workflow_name,
        workflow_version_id=workflow.version_id,
        is_test_run=run_kind == "test",
        now=now,
    )
    db.commit()

    return ChatTurnOutcome(
        text=filtered.text,
        thread_id=result["thread_id"],
        sources=extract_sources_from_messages(result["messages"]),
        was_modified=filtered.was_modified,
    )
