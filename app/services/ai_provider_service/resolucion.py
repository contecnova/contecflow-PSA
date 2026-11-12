"""Resolucion del proveedor por defecto: base de datos (empresa, global), `.env` y credencial; pausa tras error.

Parte de `app.services.ai_provider_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.encryption import encrypt_value
from app.models.ai_providers import AIProvider
from app.services.ai_provider_service.catalogo import PROVIDER_CATALOG

_logger = logging.getLogger("ai_provider_service")


class ProveedorDeEntorno:
    """El proveedor que describe el `.env`, sin pasar por la base de datos.

    Es el último escalón de la resolución y existe para que un despliegue de un
    solo cliente se configure entero por fichero, sin abrir la aplicación.

    No hereda de `AIProvider` a propósito: no es una fila, no se persiste y no
    debe poder acabar en la sesión por accidente. Lleva los mismos atributos que
    `call_provider` y el registro de uso necesitan —`id` a `None`, que
    `_registrar_uso` ya contempla— y los contadores en cero, que se mueven en
    memoria y se descartan al acabar la petición.
    """

    __slots__ = ("id", "name", "provider", "status", "api_key", "api_base_url",
                 "default_model", "max_tokens", "temperature", "total_requests",
                 "total_tokens_in", "total_tokens_out", "total_cost_usd",
                 "last_used_at", "last_error", "last_error_at", "organization_id",
                 "is_default", "is_active")

    def __init__(self, *, proveedor: str, api_key: str, modelo: str, base_url: str):
        self.id = None
        self.name = f"{proveedor} (.env)"
        self.provider = proveedor
        self.status = "active"
        # Cifrada, porque `call_provider` descifra siempre. Así el camino de
        # llamada es EL MISMO que el de un proveedor de base de datos: un solo
        # sitio que descifra, y no dos ramas que puedan divergir.
        self.api_key = encrypt_value(api_key) if api_key else None
        self.api_base_url = base_url or None
        self.default_model = modelo or None
        self.max_tokens = 2000
        self.temperature = 0.7
        self.total_requests = 0
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.total_cost_usd = 0.0
        self.last_used_at = None
        self.last_error = None
        self.last_error_at = None
        self.organization_id = None
        self.is_default = True
        self.is_active = True


#: Proveedores que no necesitan clave porque corren en la propia máquina.
_SIN_CLAVE = {"ollama"}


def proveedor_desde_entorno():
    """El proveedor descrito por `.env`, o `None` si no hay ninguno.

    `AI_PROVIDER` + `AI_API_KEY` es la forma agnóstica. `ANTHROPIC_API_KEY` se
    sigue aceptando como alias heredado —era la única que existía— para que
    ningún `.env` deje de funcionar por este cambio.
    """
    proveedor = (settings.AI_PROVIDER or "").strip().lower()
    api_key = (settings.AI_API_KEY or "").strip()

    if not proveedor and (settings.ANTHROPIC_API_KEY or "").strip():
        proveedor, api_key = "anthropic", settings.ANTHROPIC_API_KEY.strip()

    if not proveedor:
        return None
    if proveedor not in PROVIDER_CATALOG:
        _logger.warning(
            "AI_PROVIDER='%s' no es un proveedor conocido. Opciones: %s",
            proveedor, ", ".join(sorted(PROVIDER_CATALOG)))
        return None
    if not api_key and proveedor not in _SIN_CLAVE:
        _logger.warning("AI_PROVIDER='%s' sin AI_API_KEY: no se usa.", proveedor)
        return None

    return ProveedorDeEntorno(
        proveedor=proveedor,
        api_key=api_key,
        modelo=(settings.AI_MODEL or "").strip(),
        base_url=(settings.AI_BASE_URL or "").strip(),
    )


def proveedor_de_credencial(db: Session, organization_id=None):
    """La clave de Anthropic guardada en Credenciales → AI provider keys, como último escalón.

    Revisión 2026-11: esa credencial sólo la leían los caminos que llamaban a
    Anthropic directamente, sin gobernanza ni tope de gasto. Al quitarlos, quien
    la tuviera configurada no puede quedarse sin IA: aquí entra en la puerta común.
    """
    try:
        from app.services.integration_credentials_service import get_credential
        clave = (get_credential(db, "ai_providers", "anthropic_api_key", org_id=organization_id) or "").strip()
    except Exception:
        _logger.debug("proveedor_de_credencial: sin credencial legible", exc_info=True)
        return None
    if not clave:
        return None
    return ProveedorDeEntorno(proveedor="anthropic", api_key=clave,
                              modelo=(settings.CONTECFLOW_AI_MODEL or "").strip(), base_url="")


def _disponible(db: Session = None):
    """Proveedor elegible: no en error, o con el error ya enfriado.

    Revision 2026-11: un fallo dejaba el proveedor en «error» para siempre
    (fuera de la seleccion y del respaldo hasta que alguien lo editaba). Ahora
    se aparta `AI_PROVIDER_ERROR_COOLDOWN_SECONDS` y vuelve a probarse solo.
    """
    from datetime import timedelta
    from sqlalchemy import or_
    # Revisión 2026-11 (medido: el ajuste estaba en Admin y no tenía efecto): se
    # lee en tiempo real, con el valor de `.env` como respaldo.
    segundos = None
    if db is not None:
        from app.services.settings_service import get_runtime_int
        segundos = get_runtime_int(db, "AI_PROVIDER_ERROR_COOLDOWN_SECONDS")
    limite = datetime.now(timezone.utc) - timedelta(
        seconds=int(segundos if segundos is not None else (settings.AI_PROVIDER_ERROR_COOLDOWN_SECONDS or 300)))
    return or_(AIProvider.status != "error", AIProvider.last_error_at.is_(None), AIProvider.last_error_at < limite)


def get_default_provider(
    db: Session,
    *,
    is_superadmin: bool = True,
    organization_id=None,
):
    """Return default (or first active) provider with tenant-aware fallback.

    Resolution order for non-superadmin users:
    1) Org-specific provider
    2) Global shared provider (organization_id is NULL)
    3) El proveedor del `.env` (ver `proveedor_desde_entorno`)

    El tercer escalón es el mismo patrón que ya usaba el motor de voz en
    `app/services/stt/__init__.py`: organización → global → entorno. La base de
    datos no sobra —un despliegue multi-empresa necesita un proveedor por
    organización, y eso un fichero de entorno no lo puede expresar—, pero uno de
    un solo cliente tiene que poder configurarse sin abrir la aplicación.
    """
    base_q = db.query(AIProvider).filter(
        _disponible(db),
        AIProvider.is_active == True,  # audit #36 soft-delete
    )

    def _pick(q):
        # Determinism: si hay default explícito, gana. Si no, orden estable por
        # (status='active' primero, created_at asc, id asc) para evitar que dos
        # providers idénticos elijan uno u otro arbitrariamente entre requests.
        p = q.filter(AIProvider.is_default == True).order_by(
            AIProvider.created_at.asc(), AIProvider.id.asc()
        ).first()
        if not p:
            # active > otros estados; luego más antiguo primero, id como tie-breaker
            from sqlalchemy import case as sql_case
            order_status = sql_case((AIProvider.status == "active", 0), else_=1)
            p = q.order_by(order_status, AIProvider.created_at.asc(), AIProvider.id.asc()).first()
        return p

    if is_superadmin:
        return _pick(base_q) or proveedor_desde_entorno() or proveedor_de_credencial(db, organization_id)

    if organization_id:
        org_q = base_q.filter(AIProvider.organization_id == organization_id)
        p = _pick(org_q)
        if p:
            return p

    shared_q = base_q.filter(AIProvider.organization_id.is_(None))
    return _pick(shared_q) or proveedor_desde_entorno() or proveedor_de_credencial(db, organization_id)
