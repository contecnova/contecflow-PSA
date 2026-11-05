"""
AI provider endpoints, fallback keys, models and cost alerting thresholds.

These fields are referenced by:
  - app/services/ai/* (provider clients, fallback chain)
  - app/services/semantic_classifier* (model selection)
  - app/services/billing/ai_cost_tracker (cost alerting)

NOTE: This is a *mixin* — it must not inherit from BaseSettings. It is merged
into the main `Settings` class via multiple inheritance (see `app.core.config`).
"""
from pydantic import Field


class AISettingsMixin:
    # ── El proveedor de IA del despliegue, AGNÓSTICO ──────────────────────────
    #
    # Auditoría 2026-09. Antes la única credencial de IA que admitía `.env` era
    # `ANTHROPIC_API_KEY`. Quien trabajara con Gemini, OpenAI o un Ollama local
    # no tenía forma de configurar el despliegue por fichero: o pasaba por la
    # interfaz, o no había IA. Y la aplicación soporta ocho proveedores.
    #
    # Estas cuatro variables son el ÚLTIMO escalón de la resolución
    #
    #     proveedor de la organización (BD) → proveedor global (BD) → .env
    #
    # que es el mismo patrón que ya usaba el motor de voz en
    # `app/services/stt/__init__.py`. La base no sobra: un despliegue
    # multi-empresa necesita un proveedor por organización, y eso un fichero de
    # entorno no lo puede expresar. Lo que sí resuelve `.env` es el caso de un
    # solo cliente: se configura entero sin abrir la aplicación.
    #
    #     AI_PROVIDER=gemini
    #     AI_API_KEY=...
    #     AI_MODEL=gemini-2.0-flash        (opcional)
    #     AI_BASE_URL=http://localhost:11434   (sólo Ollama / Azure)
    AI_PROVIDER: str = Field(default="", env="AI_PROVIDER")
    AI_API_KEY: str = Field(default="", env="AI_API_KEY")
    AI_MODEL: str = Field(default="", env="AI_MODEL")
    AI_BASE_URL: str = Field(default="", env="AI_BASE_URL")

    # Tiempos de espera de las llamadas a los proveedores (revision 2026-11:
    # antes 60, 120 y 30 s escritos en `ai_provider_service`, 90 en el agente).
    # Editables en Admin → Ajustes → Timeouts. El de la nube es el ya existente
    # `OUTBOUND_AI_TIMEOUT_SECONDS`. Ollama y los modelos locales tardan mas.
    AI_LOCAL_HTTP_TIMEOUT_SECONDS: int = Field(default=120, env="AI_LOCAL_HTTP_TIMEOUT_SECONDS")
    # Un proveedor que falla se aparta durante este tiempo y luego se reintenta
    # solo (antes quedaba en «error» hasta que alguien lo editaba).
    AI_PROVIDER_ERROR_COOLDOWN_SECONDS: int = Field(default=300, env="AI_PROVIDER_ERROR_COOLDOWN_SECONDS")
    # MCP (revisión 2026-11): qué pasa cuando un agente externo usa una
    # herramienta que escribe. off: no la ve. approval: se abre una aprobación
    # (tipo «mcp_action») y se ejecuta solo si se aprueba. direct: se ejecuta.
    MCP_WRITE_MODE: str = Field(default="off", env="MCP_WRITE_MODE")
    # Tope diario de gasto en IA por empresa, en USD (0: sin tope). Al
    # alcanzarlo las llamadas se cortan hasta las 00:00 UTC (revisión 2026-11).
    AI_DAILY_BUDGET_USD: float = Field(default=0.0, env="AI_DAILY_BUDGET_USD")
    # Porcentaje del tope a partir del cual el Hub de IA avisa.
    AI_DAILY_BUDGET_WARN_PCT: float = Field(default=80.0, env="AI_DAILY_BUDGET_WARN_PCT")
    # Revisión 2026-11 (Ask-the-Data): valores reales cuando un filtro no encuentra nada.
    ASK_DATA_HINT_MAX_VALUES: int = Field(default=10, env="ASK_DATA_HINT_MAX_VALUES")
    ASK_DATA_HINT_MIN_SIMILARITY: float = Field(default=0.5, env="ASK_DATA_HINT_MIN_SIMILARITY")
    ASK_DATA_RETRY_WITH_REAL_VALUES: bool = Field(default=True, env="ASK_DATA_RETRY_WITH_REAL_VALUES")
    # Revisión 2026-11 (Ask-the-Data): banco de preguntas validadas.
    ASK_DATA_REUSE_EXACT_EXAMPLE: bool = Field(default=True, env="ASK_DATA_REUSE_EXACT_EXAMPLE")
    ASK_DATA_EXAMPLES_IN_PROMPT: int = Field(default=3, env="ASK_DATA_EXAMPLES_IN_PROMPT")
    ASK_DATA_EXAMPLE_MIN_SIMILARITY: float = Field(default=0.3, env="ASK_DATA_EXAMPLE_MIN_SIMILARITY")
    # Tope de la llamada de «Probar»: con 10, los modelos que razonan (Gemini 2.5,
    # o-series) gastaban todo en pensar y la prueba fallaba con el proveedor sano.
    AI_TEST_MAX_TOKENS: int = Field(default=256, env="AI_TEST_MAX_TOKENS")
    # Tope de las preguntas de respuesta corta (clasificar, elegir un id): el
    # razonamiento de los modelos 2.5 / o-series tambien cuenta.
    AI_SHORT_ANSWER_MAX_TOKENS: int = Field(default=256, env="AI_SHORT_ANSWER_MAX_TOKENS")
    AI_AGENT_TURN_TIMEOUT_SECONDS: int = Field(default=90, env="AI_AGENT_TURN_TIMEOUT_SECONDS")
    AI_MODELS_LIST_TIMEOUT_SECONDS: int = Field(default=30, env="AI_MODELS_LIST_TIMEOUT_SECONDS")

    # ── AI providers (opcionales) ─────────────────────────────────────────────
    # Fallback API keys — used only when no provider is configured in the database.
    # Prefer configuring providers via the AI Providers admin panel in the UI.
    #
    # `ANTHROPIC_API_KEY` se mantiene como ALIAS HEREDADO: si no hay
    # `AI_PROVIDER` y sí esta clave, el despliegue resuelve a Anthropic como
    # antes. Ningún `.env` existente deja de funcionar por este cambio.
    ANTHROPIC_API_KEY: str = Field(default="", env="ANTHROPIC_API_KEY")
    ANTHROPIC_API_URL: str = Field(default="https://api.anthropic.com/v1", env="ANTHROPIC_API_URL")
    ANTHROPIC_DOCS_URL: str = Field(default="https://www.anthropic.com/docs", env="ANTHROPIC_DOCS_URL")
    OPENAI_API_URL: str = Field(default="https://api.openai.com/v1", env="OPENAI_API_URL")
    OPENAI_DOCS_URL: str = Field(default="https://platform.openai.com/docs", env="OPENAI_DOCS_URL")
    GEMINI_API_URL: str = Field(default="https://generativelanguage.googleapis.com/v1beta", env="GEMINI_API_URL")  # v1beta soporta todos los modelos Gemini 2.x
    GEMINI_DOCS_URL: str = Field(default="https://developers.google.com/ai", env="GEMINI_DOCS_URL")
    DEEPSEEK_API_URL: str = Field(default="https://api.deepseek.com/v1", env="DEEPSEEK_API_URL")
    DEEPSEEK_DOCS_URL: str = Field(default="https://docs.deepseek.ai", env="DEEPSEEK_DOCS_URL")
    GROQ_API_URL: str = Field(default="https://api.groq.com/openai/v1", env="GROQ_API_URL")
    GROQ_DOCS_URL: str = Field(default="https://docs.groq.com", env="GROQ_DOCS_URL")
    MISTRAL_API_URL: str = Field(default="https://api.mistral.ai/v1", env="MISTRAL_API_URL")
    MISTRAL_DOCS_URL: str = Field(default="https://docs.mistral.ai", env="MISTRAL_DOCS_URL")
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")
    OLLAMA_DOCS_URL: str = Field(default="https://ollama.com/docs", env="OLLAMA_DOCS_URL")
    # AZURE_OPENAI_API_URL must be set to your resource endpoint (e.g. https://<resource>.openai.azure.com/openai)
    AZURE_OPENAI_API_URL: str = Field(default="", env="AZURE_OPENAI_API_URL")
    AZURE_OPENAI_DOCS_URL: str = Field(default="https://oai.azure.com", env="AZURE_OPENAI_DOCS_URL")

    # Modelo IA de fallback (usado cuando no hay proveedor configurado en BD)
    CONTECFLOW_AI_MODEL: str = Field(default="claude-haiku-4-5", env="CONTECFLOW_AI_MODEL")
    # Semantic classifier backend: keep HTTP API lean by default.
    # "tfidf" avoids loading heavy torch/transformers dependencies in API pods.
    SEMANTIC_EMBEDDINGS_BACKEND: str = Field(default="tfidf", env="SEMANTIC_EMBEDDINGS_BACKEND")

    # ── OpenAI (fallback key — prefer DB-configured provider) ────────────────
    OPENAI_API_KEY: str = Field(default="", env="OPENAI_API_KEY")
    # OpenAI Speech-to-Text model (gpt-4o-mini-transcribe es el sucesor de whisper-1)
    OPENAI_STT_MODEL: str = Field(default="gpt-4o-mini-transcribe", env="OPENAI_STT_MODEL")

    # ── AI cost alerting ──────────────────────────────────────────────────────
    AI_COST_ALERT_USD_PER_DAY: float = Field(default=10.0, env="AI_COST_ALERT_USD_PER_DAY")
