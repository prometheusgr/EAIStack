"""Agent tools. Tools are built per-request via factories so they can be
bound to a specific, authenticated user — never to a model-supplied one.
"""

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.repositories import EmbeddingRepository
from app.services import generate_embedding

MAX_EXCERPT_CHARS = 300


class _SearchKnowledgeBaseInput(BaseModel):
    """Arguments the model may supply when calling search_knowledge_base."""

    query: str = Field(..., description="The search query, in natural language.")
    top_k: int = Field(default=5, description="Maximum number of documents to return.")


def make_search_knowledge_base_tool(user_id: str, db: Session) -> StructuredTool:
    """Build a search_knowledge_base tool bound to one user's documents.

    user_id and db are closed over rather than exposed as model-supplied
    arguments: letting the model choose whose documents to search would be
    a session-isolation hole (one user's chat could read another user's
    knowledge base).
    """
    repo = EmbeddingRepository(db)

    def search_knowledge_base(query: str, top_k: int = 5) -> str:
        query_embedding = generate_embedding(query)
        matches = repo.search_similar(user_id, query_embedding, top_k)

        if not matches:
            return "No matching documents were found in the knowledge base."

        excerpts = []
        for _, knowledge_base, _ in matches:
            excerpt = knowledge_base.content[:MAX_EXCERPT_CHARS]
            if len(knowledge_base.content) > MAX_EXCERPT_CHARS:
                excerpt += "..."
            excerpts.append(f"Title: {knowledge_base.title}\n{excerpt}")

        return "\n\n".join(excerpts)

    return StructuredTool.from_function(
        func=search_knowledge_base,
        name="search_knowledge_base",
        description=(
            "Search the user's personal knowledge base for documents relevant to a "
            "query. Use this whenever answering the question requires specific facts, "
            "policies, or content that may have been uploaded by the user rather than "
            "general knowledge. Returns the title and a content excerpt for each "
            "matching document, or a message saying nothing matched."
        ),
        args_schema=_SearchKnowledgeBaseInput,
    )
