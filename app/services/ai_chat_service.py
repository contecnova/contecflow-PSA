"""
ai_chat_service — Aggregate module for AI chat services.
Imports and re-exports all AI-related services: prompts, rate limiting, RAG, conversations, etc.
Backward-compatible interface for existing code depending on this module.
"""
# Core logging and action tracking
from app.services.ai_chat.core_service import (
    log_action,
    demo_response,
    prepare_chat,
    persist_chat_response,
)

# Prompt template management
from app.services.ai_chat.prompt_service import (
    get_prompt,
    list_prompts,
    get_prompt_detail,
    create_prompt_template,
    toggle_prompt_template,
    delete_prompt_template,
)

# Rate limiting and governance
from app.services.ai_chat.rate_limit_service import check_rate_limit

# Knowledge base RAG
from app.services.ai_chat.rag_service import kb_rag_context

# Conversation management
from app.services.ai_chat.conversation_service import (
    list_conversations,
    get_conversation,
    archive_conversation,
    archive_all_conversations,
    get_or_create_conversation,
)

# Agent execution
from app.services.ai_chat.agent_execution_service import (
    create_agent_execution,
    get_agent_status,
    list_agent_executions,
    get_agent_detail_with_steps,
)

# Tool execution and definitions
from app.services.ai_chat.tool_execution_service import (
    AGENT_TOOLS,
    execute_tool,
    build_agent_system_prompt,
)

__all__ = [
    # Core
    "log_action",
    "demo_response",
    "prepare_chat",
    "persist_chat_response",
    # Prompts
    "get_prompt",
    "list_prompts",
    "get_prompt_detail",
    "create_prompt_template",
    "toggle_prompt_template",
    "delete_prompt_template",
    # Governance & Rate Limit
    "check_rate_limit",
    # RAG
    "kb_rag_context",
    # Conversations
    "list_conversations",
    "get_conversation",
    "archive_conversation",
    "archive_all_conversations",
    "get_or_create_conversation",
    # Agent Execution
    "create_agent_execution",
    "get_agent_status",
    "list_agent_executions",
    "get_agent_detail_with_steps",
    # Tool Execution
    "AGENT_TOOLS",
    "execute_tool",
    "build_agent_system_prompt",
]
