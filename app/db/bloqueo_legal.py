"""Bloqueo legal en la capa de persistencia (auditoria 2026-11).

Lo que coincide con un bloqueo legal activo no se borra, venga de donde venga:
lo impide un `before_flush` registrado en `app/models/governance.py`. Vivia en
`app/services/retencion.py`, asi que un modelo importaba un servicio (capa
invertida). Aqui solo depende de modelos y de `app.db`; las politicas de
retencion (`app/services/retencion.py`) lo importan de aqui.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy import false, func, or_

from app.core.errores import ErrorDeDominio


@dataclass(frozen=True)
class Tipo:
    modelo: Callable                  # devuelve la clase (import diferido)
    fecha: Callable                   # (Modelo) -> expresión de la fecha que cuenta
    condicion: Optional[Callable]     # (Modelo) -> filtro extra (p. ej. sólo cerrados)
    campos: tuple[str, ...]           # campos por los que se puede bloquear


def _ticket():
    from app.models.service_desk.tickets import Ticket
    return Ticket


def _documento():
    from app.models.documents import Document
    return Document


def _conversacion():
    from app.models.ai_chat import AIConversation
    return AIConversation


def _uso_ia():
    from app.models.ai_providers import AIUsageLog
    return AIUsageLog


def _aviso():
    from app.models.enterprise import Notification
    return Notification


# Segunda auditoría 2026-11: registros técnicos con datos personales que
# también tienen que poder retenerse (y bloquearse).
def _llamada_conector():
    from app.models.conectores import ConectorLlamada
    return ConectorLlamada


def _entrega_webhook():
    from app.models.enterprise import WebhookDelivery
    return WebhookDelivery


def _correo():
    from app.models.cab import EmailLog
    return EmailLog


def _documento_de_ausencia():
    from app.models.ausencias import DocumentoDeAusencia
    return DocumentoDeAusencia


def _actividad():
    from app.models.activity import ActivityEvent
    return ActivityEvent


def _contacto_de_cliente():
    from app.models.clients import ClientContact
    return ClientContact


def _horas_extra():
    from app.models.horas_extra import PeticionDeHorasExtra
    return PeticionDeHorasExtra


def _reunion():
    from app.models.ai_chat import AIMeeting
    return AIMeeting


def _documento_de_proveedor():
    from app.models.proveedores import SupplierDocument
    return SupplierDocument


def _acceso_de_proveedor():
    from app.models.proveedores import SupplierAccessGrant
    return SupplierAccessGrant


def _foto_de_configuracion():
    from app.models.cmdb_software import SoftwareConfigSnapshot
    return SoftwareConfigSnapshot


def _hallazgo():
    from app.models.cmdb_software import VulnerabilityFinding
    return VulnerabilityFinding


TIPOS: dict[str, Tipo] = {
    # Sólo tickets cerrados, contando desde el cierre.
    "tickets": Tipo(_ticket, lambda M: M.closed_at, lambda M: M.closed_at.isnot(None),
                    ("id", "client_id", "project_id", "requester_user_id", "created_by_user_id")),
    # Sólo documentos archivados, desde su último cambio.
    "documents": Tipo(_documento, lambda M: func.coalesce(M.updated_at, M.created_at), lambda M: M.is_archived.is_(True),
                      ("id", "client_id", "project_id", "created_by")),
    "ai_conversations": Tipo(_conversacion, lambda M: func.coalesce(M.updated_at, M.created_at), None, ("id", "user_id")),
    "ai_usage_logs": Tipo(_uso_ia, lambda M: M.created_at, None, ("id", "user_id")),
    "notifications": Tipo(_aviso, lambda M: M.created_at, None, ("id", "user_id")),
    # Segunda auditoría 2026-11.
    "connector_calls": Tipo(_llamada_conector, lambda M: M.created_at, None, ("id", "user_id", "producto")),
    "webhook_deliveries": Tipo(_entrega_webhook, lambda M: M.created_at, None, ("id", "webhook_id", "event")),
    # Desde el envío; si no llegó a enviarse, desde que se encoló.
    "email_logs": Tipo(_correo, lambda M: func.coalesce(M.sent_at, M.created_at), None,
                       ("id", "to_address", "source", "source_id")),
    # Tarea #25: documentos de ausencias (partes médicos: categoría especial),
    # desde que se subieron. Borrar la fila borra el documento del almacén.
    "absence_documents": Tipo(_documento_de_ausencia, lambda M: M.subido_en, None, ("id", "absence_id", "user_id")),
    "activity_events": Tipo(_actividad, lambda M: M.created_at, None,
                            ("id", "actor_id", "entity_type", "entity_id", "target_id")),
    # 18-11-2026: personas de un cliente (datos personales). Sólo las
    # desactivadas, desde que se desactivaron; las activas son el cliente vivo.
    "client_contacts": Tipo(_contacto_de_cliente, lambda M: func.coalesce(M.deactivated_at, M.created_at),
                            lambda M: M.is_active.is_(False), ("id", "client_id", "email")),
    # 18-11-2026: peticiones de horas extra (registro de jornada y nómina). Sólo
    # las cerradas (decididas o canceladas), desde su último cambio; con su
    # línea de tiempo (se borra en cascada).
    "overtime_requests": Tipo(_horas_extra, lambda M: func.coalesce(M.updated_at, M.created_at),
                              lambda M: M.estado.in_(("aprobada", "rechazada", "cancelada")),
                              ("id", "user_id", "project_id")),
    # 19-11-2026: reuniones del asistente (transcripción, audio, participantes en
    # cascada), desde su alta. Su audio y su transcripción tienen además su propia
    # retención corta (`app/services/reuniones/trabajos.py`), que respeta esto.
    "meetings": Tipo(_reunion, lambda M: M.created_at, None, ("id", "project_id", "client_id", "created_by")),
    # Migracion 189: GRC de terceros. Documentos de proveedor caducados (desde la
    # caducidad) y accesos revocados (desde la revocacion).
    "supplier_documents": Tipo(_documento_de_proveedor, lambda M: M.expires_at, lambda M: M.expires_at.isnot(None),
                               ("id", "subcontractor_id", "doc_type")),
    "supplier_access_grants": Tipo(_acceso_de_proveedor, lambda M: M.revoked_at, lambda M: M.revoked_at.isnot(None),
                                   ("id", "subcontractor_id", "worker_id")),
    # Migracion 190: CMDB de software. Fotos de configuración (desde la foto) y
    # hallazgos cerrados (resueltos o falsos positivos, desde el cierre).
    "sw_config_snapshots": Tipo(_foto_de_configuracion, lambda M: M.created_at, None, ("id", "instance_id")),
    "sw_findings": Tipo(_hallazgo, lambda M: M.closed_at,
                        lambda M: M.status.in_(("resolved", "false_positive")) & M.closed_at.isnot(None),
                        ("id", "product_id", "instance_id", "vulnerability_id")),
}


class BloqueoLegalActivo(ErrorDeDominio):
    def __init__(self, caso: str):
        super().__init__(409, f"Este registro está bajo bloqueo legal ({caso}) y no se puede borrar")


# ── Bloqueos ──────────────────────────────────────────────────────────────────

def _sin_filtro(db):
    from app.db.session import sin_filtro_de_tenant
    return sin_filtro_de_tenant(db)


def bloqueos_activos(db, org) -> list:
    from app.models.governance import LegalHold
    with _sin_filtro(db):
        return db.query(LegalHold).filter(LegalHold.organization_id == org, LegalHold.is_active.is_(True)).all()


def _condicion_bloqueada(clave: str, M, bloqueos: list):
    """Expresión SQL: el registro coincide con algún bloqueo activo de su tipo."""
    tipo = TIPOS[clave]
    # COALESCE: con un campo vacío (NULL) la comparación da NULL, y su negación
    # también; sin él, «no bloqueado» excluía todo lo que no tenía ese campo.
    partes = [func.coalesce(getattr(M, b.field) == b.value, false()) for b in bloqueos
              if b.entity in ("*", clave) and b.field in tipo.campos]
    return or_(*partes) if partes else false()


def _bloqueo_de(clave: str, objeto, bloqueos: list):
    tipo = TIPOS[clave]
    for b in bloqueos:
        if b.entity in ("*", clave) and b.field in tipo.campos and str(getattr(objeto, b.field, None)) == b.value:
            return b
    return None


# ── Bloqueo del borrado manual ────────────────────────────────────────────────

def comprobar_borrados(session) -> None:
    """`before_flush`: ningún registro bloqueado se borra, venga de donde venga (ORM)."""
    if not session.deleted:
        return
    clases = {TIPOS[c].modelo(): c for c in TIPOS}
    por_org: dict = {}
    for obj in list(session.deleted):
        clave = clases.get(type(obj))
        if clave is None:
            continue
        org = getattr(obj, "organization_id", None)
        if org not in por_org:
            por_org[org] = bloqueos_activos(session, org)
        b = _bloqueo_de(clave, obj, por_org[org])
        if b is not None:
            raise BloqueoLegalActivo(b.case_reference)
