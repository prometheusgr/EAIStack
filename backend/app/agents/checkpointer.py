"""LangGraph checkpointer backed by the project's own SQLAlchemy tables.

A custom BaseCheckpointSaver rather than langgraph-checkpoint-postgres:
that package owns its schema outside Alembic, requires a second Postgres
driver (psycopg v3) alongside this project's psycopg2/SQLAlchemy stack,
and only runs against real Postgres - this project's fast unit tests run
against SQLite. See docs/DATABASE_MODELS.md and docs/REPOSITORY_PATTERN.md
for the schema/repository conventions this follows instead.

Stores only the latest checkpoint per thread (upserted), not full
checkpoint history - Phase 4a's scope is resuming a conversation, not
LangGraph time-travel/replay. put_writes is a no-op for the same reason:
pending-writes tracking exists to resume mid-superstep after a crash or
an interrupt(), neither of which this graph uses.

The a* methods (aget_tuple, alist, aput, aput_writes) exist because
BaseCheckpointSaver's own defaults raise NotImplementedError rather than
falling back to the sync methods above - the compiled graph is invoked via
ainvoke() (see app.api.agents.chat), so LangGraph calls these directly.
Each wraps its sync counterpart in anyio.to_thread.run_sync rather than
duplicating the CheckpointRepository/SQLAlchemy calls: this class's db
Session is synchronous (see docs/DATABASE_MODELS.md), so "async" here
means "don't block the event loop while doing sync I/O", not "use an
async DB driver".
"""

from typing import Any, AsyncIterator, Iterator, Sequence

import anyio.to_thread
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from sqlalchemy.orm import Session

from app.repositories import CheckpointRepository


class SqlAlchemyCheckpointSaver(BaseCheckpointSaver):
    """Checkpoint saver storing one row per thread via CheckpointRepository.

    Built fresh per request from the same db session already threaded
    through create_chat_agent - never a global/cached instance, matching
    the per-request lifecycle of make_search_knowledge_base_tool in
    app.agents.tools and for the same reason (session/lifecycle safety).

    Isolation is NOT enforced here: like LangGraph's own checkpointers,
    this saver is keyed purely by thread_id, with no concept of a user.
    The (user_id, thread_id) ownership check happens one layer up, in
    ThreadRepository, before a thread_id ever reaches this class.
    """

    def __init__(self, db: Session):
        super().__init__(serde=JsonPlusSerializer())
        self._repo = CheckpointRepository(db)

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id = config["configurable"]["thread_id"]
        row = self._repo.get(thread_id)
        if row is None:
            return None

        checkpoint = self.serde.loads_typed(("msgpack", row.checkpoint))
        metadata = self.serde.loads_typed(("msgpack", row.checkpoint_metadata))

        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": config["configurable"].get("checkpoint_ns", ""),
                    "checkpoint_id": checkpoint["id"],
                }
            },
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=None,
            pending_writes=[],
        )

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        """Yield the thread's single stored checkpoint, if any.

        filter/before/limit are unsupported and raise NotImplementedError
        rather than being silently ignored: this saver keeps at most one
        checkpoint per thread (see the module docstring), so none of them is
        a meaningful operation on a result that is already 0-or-1 items -
        returning the one checkpoint anyway regardless of what was asked for
        would be silently wrong in a way the caller has no way to detect.
        Matches BaseCheckpointSaver.list's own default of NotImplementedError
        for behavior a subclass doesn't actually provide.
        """
        if filter is not None or before is not None or limit is not None:
            raise NotImplementedError(
                "SqlAlchemyCheckpointSaver.list() does not support filter/before/limit: "
                "it stores only the latest checkpoint per thread, so none of these "
                "arguments has a meaningful result to return."
            )
        if config is None:
            return
        result = self.get_tuple(config)
        if result is not None:
            yield result

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id = config["configurable"]["thread_id"]
        _, checkpoint_bytes = self.serde.dumps_typed(checkpoint)
        _, metadata_bytes = self.serde.dumps_typed(metadata)
        self._repo.upsert(thread_id, checkpoint=checkpoint_bytes, metadata=metadata_bytes)
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": config["configurable"].get("checkpoint_ns", ""),
                "checkpoint_id": checkpoint["id"],
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """No-op: this saver does not support mid-superstep resume (see module docstring)."""

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return await anyio.to_thread.run_sync(self.get_tuple, config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        # list()'s own filter/before/limit validation (see its docstring)
        # applies unchanged; consuming the sync generator to a list off the
        # event loop thread is what makes this "async" rather than a second
        # implementation of the same logic.
        results = await anyio.to_thread.run_sync(
            lambda: list(self.list(config, filter=filter, before=before, limit=limit))
        )
        for result in results:
            yield result

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return await anyio.to_thread.run_sync(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """No-op: this saver does not support mid-superstep resume (see module docstring)."""
