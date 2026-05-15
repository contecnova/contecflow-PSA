"""
AI Providers — Configuración multi-proveedor de IA.
Soporta: Anthropic (Claude), OpenAI (GPT), Google (Gemini),
         DeepSeek, Ollama/Llama, Mistral, Groq.
"""
import uuid
import enum
from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer, Float, ForeignKey, Enum
from sqlalchemy.sql import func
from app.db.base import Base


class AIProviderType(str, enum.Enum):
    anthropic = "anthropic"   # Claude 3.5/4
    openai    = "openai"      # GPT-4o, GPT-4, GPT-3.5
    gemini    = "gemini"      # Gemini 2.x Pro/Flash
    deepseek  = "deepseek"    # DeepSeek-V3, DeepSeek-R1
    ollama    = "ollama"      # Llama 3, Mistral, Phi (local)
    groq      = "groq"        # Llama, Mixtral via Groq (ultra rápido)
    mistral   = "mistral"     # Mistral Large, Codestral
    azure     = "azure"       # Azure OpenAI


class AIProviderStatus(str, enum.Enum):
    active   = "active"
    inactive = "inactive"
    error    = "error"


class AIProvider(Base):
    """Configuración de un proveedor de IA para la organización."""
    __tablename__ = "ai_providers"
    # TenantSession should include shared/global provider rows (org_id IS NULL)
    # so tenant users can use centrally managed AI connectors.
    _tenant_filter_include_global = True

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    name         = Column(String(100), nullable=False)           # "Claude Production", "GPT-4 Dev"
    provider     = Column(Enum(AIProviderType), nullable=False)
    status       = Column(Enum(AIProviderStatus), default=AIProviderStatus.active)

    # Credenciales (cifradas en producción)
    api_key      = Column(String(500), nullable=True)
    api_base_url = Column(String(500), nullable=True)           # Para Ollama/Azure custom
    api_version  = Column(String(50),  nullable=True)           # Para Azure

    # Modelo por defecto para este proveedor
    default_model    = Column(String(100), nullable=True)
    # Modelos disponibles (JSON lista separada por comas)
    available_models = Column(Text, nullable=True)

    # Configuración
    is_default       = Column(Boolean, default=False)            # Proveedor por defecto
    max_tokens       = Column(Integer, default=2000)
    temperature      = Column(Float, default=0.7)
    timeout_seconds  = Column(Integer, default=30)

    # Estadísticas de uso
    total_requests   = Column(Integer, default=0)
    total_tokens_in  = Column(Integer, default=0)
    total_tokens_out = Column(Integer, default=0)
    total_cost_usd   = Column(Float, default=0.0)
    last_used_at     = Column(DateTime(timezone=True), nullable=True)
    last_error       = Column(Text, nullable=True)
    last_error_at    = Column(DateTime(timezone=True), nullable=True)

    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())
    created_by   = Column(String(36), ForeignKey("users.id"), nullable=True)

    is_active    = Column(Boolean, default=True, nullable=False, server_default="1", index=True)  # audit #36 soft-delete


class AIUsageLog(Base):
    """Log de uso de IA por petición."""
    __tablename__ = "ai_usage_logs"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    provider_id  = Column(String(36), ForeignKey("ai_providers.id", ondelete="SET NULL"), nullable=True)
    user_id      = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    module       = Column(String(50),  nullable=False)   # nexusagent, oracle, sprint, meetings...
    model        = Column(String(100), nullable=True)
    tokens_in    = Column(Integer, default=0)
    tokens_out   = Column(Integer, default=0)
    cost_usd     = Column(Float, default=0.0)
    latency_ms   = Column(Integer, nullable=True)
    success      = Column(Boolean, default=True)
    error_msg    = Column(Text, nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
