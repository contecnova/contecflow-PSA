"""Traduccion en tiempo real operador <-> cliente (16-11-2026). Se leen en vivo
por empresa (grupo `traduccion` del catalogo de ajustes); estos son los valores
por defecto. Las claves de DeepL y Azure Translator NO van aqui: son
credenciales cifradas por empresa (`deepl`, `azure_translator`)."""
from pydantic import Field


class TraduccionSettingsMixin:
    TRANSLATION_ENABLED: bool = Field(
        default=True, env="TRANSLATION_ENABLED",  # 16-11-2026: activada por defecto (decisión del usuario)
        description="Translation — on for the company: customer messages are shown in each operator's language and replies go out in the customer's (off: nothing is sent to a translator)")
    TRANSLATION_PROVIDER: str = Field(
        default="ai", env="TRANSLATION_PROVIDER",
        description="Translation — provider: ai (the company's AI provider), deepl or azure (credentials of the company)")
    TRANSLATION_CHANNELS: str = Field(
        default="ticket,email,livechat,whatsapp,slack,teams,portal_assistant,internal_chat,kb,editor,portal",
        env="TRANSLATION_CHANNELS",
        description="Translation — channels where it applies (CSV): ticket, email, livechat, whatsapp, slack, teams, portal_assistant, internal_chat, kb, editor, portal (announcements, portal wiki and service catalog read by portal clients)")
    TRANSLATION_OUTBOUND_AUTO: bool = Field(
        default=True, env="TRANSLATION_OUTBOUND_AUTO",
        description="Translation — a public reply sent without preview (Slack, API) goes out translated to the customer's language")
    TRANSLATION_INCLUDE_ORIGINAL: bool = Field(
        default=False, env="TRANSLATION_INCLUDE_ORIGINAL",
        description="Translation — the customer also receives the operator's original text below the translation")
    TRANSLATION_DETECT_MIN_CONFIDENCE: float = Field(
        default=0.6, env="TRANSLATION_DETECT_MIN_CONFIDENCE",
        description="Translation — local language detection decides from this confidence (0-1); below it, the provider detects")
    TRANSLATION_MAX_BATCH_CHARS: int = Field(
        default=12000, env="TRANSLATION_MAX_BATCH_CHARS",
        description="Translation — characters sent to the provider per call (longer batches are split)")
    TRANSLATION_AI_MAX_TOKENS: int = Field(
        default=8192, env="TRANSLATION_AI_MAX_TOKENS",
        description="Translation — AI provider: maximum tokens of the answer per call")
    TRANSLATION_COST_PER_MILLION_CHARS_USD: float = Field(
        default=0.0, env="TRANSLATION_COST_PER_MILLION_CHARS_USD",
        description="Translation — DeepL/Azure price per million characters (USD); counts towards the daily AI cap (0: not counted)")
    TRANSLATION_CACHE_RETENTION_DAYS: int = Field(
        default=180, env="TRANSLATION_CACHE_RETENTION_DAYS",
        description="Translation — cached translations unused for more than N days are deleted (0: never)")
    TRANSLATION_KB_LANGUAGES: str = Field(
        default="", env="TRANSLATION_KB_LANGUAGES",
        description="Translation — portal languages knowledge articles are generated in (CSV; empty: all of the portal)")
