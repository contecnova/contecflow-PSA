"""
AI Chat – Pydantic input schemas.

Extracted from ai_chat.py so they can be tested and imported independently.
"""
from typing import Optional
from pydantic import BaseModel


class ChatPayload(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    context_type: str = "global"
    context_id:   Optional[str] = None


class AgentPayload(BaseModel):
    instruction: str
    auto_approve: bool = False   # if True, skip confirmation for low-risk tools


class PromptTemplatePayload(BaseModel):
    module: str
    name: str
    content: str
    is_active: bool = True
