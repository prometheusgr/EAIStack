"""Backend service layer for business logic."""

from app.services.chat_guardrail_service import check_input_guardrail, filter_agent_response
from app.services.embedding_service import (
    EmbeddingResult,
    embed_document,
    embed_documents,
    embed_query,
    generate_and_attach_embeddings,
    generate_embedding,
    replace_embeddings,
)
from app.services.retention_service import (
    RetentionConfig,
    purge_expired_api_keys,
    purge_expired_conversations,
    purge_expired_knowledge_base,
    purge_user_conversations,
    resolve_retention_config,
    run_retention_sweep,
)
from app.services.system_settings_service import (
    EmbeddingConfig,
    LLMConfig,
    available_provider_options,
    resolve_embedding_config,
    resolve_llm_config,
)

__all__ = [
    "check_input_guardrail",
    "filter_agent_response",
    "generate_embedding",
    "embed_document",
    "embed_documents",
    "embed_query",
    "generate_and_attach_embeddings",
    "replace_embeddings",
    "EmbeddingResult",
    "RetentionConfig",
    "purge_expired_api_keys",
    "purge_expired_conversations",
    "purge_expired_knowledge_base",
    "purge_user_conversations",
    "resolve_retention_config",
    "run_retention_sweep",
    "EmbeddingConfig",
    "LLMConfig",
    "available_provider_options",
    "resolve_embedding_config",
    "resolve_llm_config",
]
