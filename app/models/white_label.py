"""White-label / tenant branding model.

Each organization can configure its own branding (logo, colours, custom domain,
favicon, welcome message). This enables consultoras to deploy the platform under
their own brand for their clients.
"""
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
import uuid

from app.db.base import Base
from app.core.constantes import NOMBRE_DEL_PRODUCTO


class OrgBranding(Base):
    """Per-organization white-label branding configuration."""
    __tablename__ = "org_brandings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, unique=True, index=True)

    # Visual identity
    app_name          = Column(String(100), default=NOMBRE_DEL_PRODUCTO)
    tagline           = Column(String(255), nullable=True)
    logo_url          = Column(String(500), nullable=True)
    favicon_url       = Column(String(500), nullable=True)
    primary_color     = Column(String(20),  default="#6366f1")   # Indigo
    secondary_color   = Column(String(20),  default="#8b5cf6")   # Violet
    accent_color      = Column(String(20),  default="#06b6d4")   # Cyan
    background_color  = Column(String(20),  default="#0f172a")   # Dark slate
    text_color        = Column(String(20),  default="#f8fafc")

    # Domain and URLs
    custom_domain     = Column(String(255), nullable=True, index=True)  # e.g. pm.myconsulting.com
    support_email     = Column(String(255), nullable=True)
    privacy_url       = Column(String(500), nullable=True)
    terms_url         = Column(String(500), nullable=True)

    # Content customization
    welcome_message   = Column(Text, nullable=True)
    login_background_url = Column(String(500), nullable=True)
    footer_text       = Column(String(255), nullable=True)
    help_url          = Column(String(500), nullable=True)

    # Feature flags per tenant
    hide_powered_by   = Column(Boolean, default=False)
    enable_portal     = Column(Boolean, default=True)
    enable_ai         = Column(Boolean, default=True)

    # CSS override (safe subset — no scripts)
    custom_css_vars   = Column(Text, nullable=True)  # JSON: {"--color-primary": "#...", ...}

    # Traducciones personalizadas del portal, por idioma/módulo/clave.
    # JSON: { "<lang>": { "<module>": { "<key>": "<value>" } } }.
    # Persistido aquí (antes era un dict en memoria per-proceso que se perdía al
    # reiniciar y no se compartía entre workers).
    portal_translations = Column(Text, nullable=True)  # JSON

    is_active         = Column(Boolean, default=True)
    created_by        = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at        = Column(DateTime(timezone=True), server_default=func.now())
    updated_at        = Column(DateTime(timezone=True), onupdate=func.now())
