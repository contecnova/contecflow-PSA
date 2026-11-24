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
    #: Columna de empresa del modelo (todas `organization_id` desde la migracion 200, B-MOD1).
    columna_empresa: str = "organization_id"

    def empresa(self, M):
        """La columna de empresa del modelo `M`."""
        return getattr(M, self.columna_empresa)


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


def _orden_de_voz():
    from app.models.ai_chat import AIVoiceCommand
    return AIVoiceCommand


def _chat_del_portal():
    from app.models.ai_chat import AIClientChatSession
    return AIClientChatSession


def _justificante_de_gasto():
    from app.models.expenses import ExpenseAttachment
    return ExpenseAttachment


def _documento_de_ausencia():
    from app.models.ausencias import DocumentoDeAusencia
    return DocumentoDeAusencia


def _actividad():
    from app.models.activity import ActivityEvent
    return ActivityEvent


# Rev. 193: clientes internos (docs/CLIENTES_INTERNOS.md §7).
def _satisfaccion_interna():
    from app.models.nps import ClientNPS
    return ClientNPS


# 24-11-2026 (salud del cliente): NPS de clientes externos (nombre de quien
# responde y comentario = datos personales) y fotos de salud (sin datos
# personales; histórico que crece con cada recálculo).
def _respuesta_nps():
    from app.models.nps import ClientNPS
    return ClientNPS


def _foto_de_salud():
    from app.models.nps import ClientHealthSnapshot
    return ClientHealthSnapshot


def _designacion_interna():
    from app.models.clientes_internos import InternalClientRole
    return InternalClientRole


def _cargo_interno():
    from app.models.clientes_internos import InternalCharge
    return InternalCharge


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


def _foto_de_riesgo():
    from app.models.cmdb_riesgo import RiskSnapshot
    return RiskSnapshot


def _intento_de_explotacion():
    from app.models.cmdb_riesgo import ExploitEvent
    return ExploitEvent


def _aviso_de_riesgo():
    from app.models.cmdb_riesgo import RiskAlertLog
    return RiskAlertLog


def _expediente_de_demanda():
    from app.models.demanda import DemandRequest
    return DemandRequest


# Auditoria 2026-11-22 (A-MOD3): tablas con datos personales (IP, correo,
# payloads) que no tenian retencion ni purga.

def _envio_de_formulario():
    from app.models.public_forms import PublicFormSubmission
    return PublicFormSubmission


def _sesion_de_usuario():
    from app.models.sessions import UserSession
    return UserSession


def _evento_de_seguridad():
    from app.models.security_observability import SecurityEvent
    return SecurityEvent


def _deteccion_de_seguridad():
    from app.models.security_observability import SecurityDetection
    return SecurityDetection


def _anomalia_de_acceso():
    from app.models.security_observability import LoginAnomaly
    return LoginAnomaly


def _acceso_a_documento():
    from app.models.documents import DocumentAccessLog
    return DocumentAccessLog


def _accion_de_ia():
    from app.models.ai_chat import AIActionLog
    return AIActionLog


def _auditoria_de_colaboracion():
    from app.models.collaboration import CollaborationAuditEvent
    return CollaborationAuditEvent


# 23-11-2026: políticas de cuenta (docs/seguridad/politicas_de_cuenta.md).
def _historial_de_contrasenas():
    from app.models.seguridad_de_cuentas import PasswordHistory
    return PasswordHistory


def _dispositivo_de_confianza():
    from app.models.seguridad_de_cuentas import TrustedDevice
    return TrustedDevice


def _solicitud_de_seguridad():
    from app.models.seguridad_de_cuentas import SecurityChangeRequest
    return SecurityChangeRequest


def _campana_de_recertificacion():
    from app.models.seguridad_de_cuentas import AccessReviewCampaign
    return AccessReviewCampaign


def _registro_de_jira():
    from app.models.jira_integration import JiraSyncLog
    return JiraSyncLog


def _sesion_de_voz():
    from app.models.service_desk.datos_propios import VoiceSession
    return VoiceSession


def _hueco_de_conocimiento():
    from app.models.service_desk.kb_calidad import KBGap
    return KBGap


# Migracion 202: «Mi cuaderno» (docs/CUADERNO.md §GRC).
def _cuaderno():
    from app.models.cuaderno import Notebook
    return Notebook


def _pagina_de_cuaderno():
    from app.models.cuaderno import NotebookPage
    return NotebookPage


def _adjunto_de_cuaderno():
    from app.models.cuaderno import NotebookAttachment
    return NotebookAttachment


# 23-11-2026: definidas ANTES de TIPOS (se usaban antes de existir: NameError al importar y 500 en cualquier borrado).
def _instancia_bpmn():
    from app.models.bpmn_process import BPMNInstance
    return BPMNInstance


def _ejecucion_ticket_pr():
    from app.models.ticket_a_pr import TicketPrRun
    return TicketPrRun


_ESTADOS_FINALES_TPR = ("rejected", "blocked", "failed", "cancelled", "cab_rejected", "merged", "closed")


# Migracion 206 (docs/PIR.md): definida ANTES de TIPOS, como las anteriores.
def _revision_pir():
    from app.models.pir import PirRevision
    return PirRevision

# Migracion 207 (Ask-the-Data con memoria): definida ANTES de TIPOS, como las anteriores.
def _conversacion_ask():
    from app.models.ai_chat import AskDataConversation
    return AskDataConversation


# Migracion 209 (chat del portal completo, docs/portal/CHAT_DEL_PORTAL.md):
# definidas ANTES de TIPOS, como las anteriores.
def _adjunto_del_chat_del_portal():
    from app.models.portal_conversations import PortalConversationAttachment
    return PortalConversationAttachment


def _version_de_mensaje_del_portal():
    from app.models.portal_conversations import PortalConversationMessageVersion
    return PortalConversationMessageVersion


def _llamada_del_portal():
    from app.models.portal_conversations import PortalConversationCall
    return PortalConversationCall


# Migracion 211 (chat en vivo de Soporte completo, docs/portal/CHAT_DEL_PORTAL.md §10).
def _adjunto_del_chat_en_vivo():
    from app.models.service_desk.mercado import ChannelAttachment
    return ChannelAttachment


def _version_de_mensaje_del_chat_en_vivo():
    from app.models.service_desk.mercado import ChannelMessageVersion
    return ChannelMessageVersion


def _llamada_del_chat_en_vivo():
    from app.models.service_desk.mercado import ChannelCall
    return ChannelCall


# Migracion 212 (certificaciones, docs/CERTIFICACIONES.md §GRC): definidas ANTES de TIPOS.
def _cert_modelo(nombre: str):
    def _m():
        from app.models import certificaciones
        return getattr(certificaciones, nombre)
    return _m


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
    # M49 (auditoría 22-11-2026): transcripciones de voz y chats del portal con
    # la IA (datos personales): retención configurable y bloqueo legal, como las
    # conversaciones con la IA y las reuniones (antes sin purga).
    "ai_voice_commands": Tipo(_orden_de_voz, lambda M: M.created_at, None, ("id", "user_id")),
    "ai_client_chats": Tipo(_chat_del_portal, lambda M: M.created_at, None, ("id", "client_user_id")),
    # A33 (auditoría 22-11-2026): justificantes de gastos (registro contable y fiscal);
    # un bloqueo legal impide borrarlos, vengan de la pantalla o de una política.
    "expense_attachments": Tipo(_justificante_de_gasto, lambda M: M.created_at, None,
                                ("id", "expense_id", "uploaded_by")),
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
    # Rev. 193: clientes internos. Valoraciones de empleados en el portal interno
    # (dato personal, base legal laboral) desde la respuesta; designaciones
    # (usuario clave, finanzas, delegado) desde su alta; cargos internos (registro
    # contable) desde la emisión, solo los emitidos, exportados o anulados.
    "internal_satisfaction": Tipo(_satisfaccion_interna, lambda M: M.created_at,
                                  lambda M: M.respondent_user_id.isnot(None),
                                  ("id", "client_id", "respondent_user_id")),
    "client_nps_responses": Tipo(_respuesta_nps, lambda M: M.created_at,
                                 lambda M: M.respondent_user_id.is_(None), ("id", "client_id")),
    "client_health_snapshots": Tipo(_foto_de_salud, lambda M: M.snapshot_at, None, ("id", "client_id")),
    "internal_client_roles": Tipo(_designacion_interna, lambda M: M.created_at, None, ("id", "client_id", "user_id")),
    "internal_charges": Tipo(_cargo_interno, lambda M: func.coalesce(M.issued_at, M.cancelled_at, M.created_at),
                             lambda M: M.status.in_(("emitido", "exportado", "anulado")),
                             ("id", "client_id", "period")),
    # Migracion 194: índice de riesgo. Histórico diario (desde el día; además lo
    # poda el trabajo diario según `risk_settings.history_days`), intentos de
    # explotación importados (desde que se vieron) y avisos mandados.
    "sw_risk_snapshots": Tipo(_foto_de_riesgo, lambda M: M.day, None, ("id", "scope_type", "scope_id")),
    "sw_exploit_events": Tipo(_intento_de_explotacion, lambda M: M.observed_at, None,
                              ("id", "ci_id", "vuln_id", "source")),
    "sw_risk_alert_log": Tipo(_aviso_de_riesgo, lambda M: M.sent_at, None, ("id", "kind")),
    # Migración 195: expedientes del flujo de demanda cerrados (rechazados, retirados o
    # ejecutados), desde el cierre; con su log, versiones, documentos y comentarios en cascada.
    "demand_requests": Tipo(_expediente_de_demanda, lambda M: M.closed_at,
                            lambda M: M.status.in_(("rejected", "withdrawn", "done")) & M.closed_at.isnot(None),
                            ("id", "client_id", "project_id", "requester_user_id", "client_user_id")),
    # Auditoria 2026-11-22 (A-MOD3): datos personales que no tenian retencion.
    # Envios de formularios publicos (correo e IP del remitente), desde el envio.
    "public_form_submissions": Tipo(_envio_de_formulario, lambda M: M.submitted_at, None,
                                    ("id", "form_id", "submitter_email")),
    # Sesiones (IP, agente): solo las caducadas o revocadas, desde que acabaron.
    "user_sessions": Tipo(_sesion_de_usuario, lambda M: func.coalesce(M.revoked_at, M.expires_at),
                          lambda M: M.revoked_at.isnot(None) | (M.expires_at < func.now()),
                          ("id", "user_id")),
    # Seguridad (IP): eventos desde que ocurrieron, detecciones solo cerradas,
    # anomalias de acceso desde que ocurrieron. (B-MOD1, migracion 200: ya usan
    # `organization_id`, como el resto.)
    "security_events": Tipo(_evento_de_seguridad, lambda M: M.occurred_at, None,
                            ("id", "user_id", "ip_address")),
    "security_detections": Tipo(_deteccion_de_seguridad, lambda M: M.resolved_at,
                                lambda M: M.resolved_at.isnot(None), ("id", "user_id", "ip_address")),
    "login_anomalies": Tipo(_anomalia_de_acceso, lambda M: M.occurred_at, None,
                            ("id", "user_id", "ip_address")),
    # Accesos a documentos, acciones de la IA y auditoria de colaboracion (IP).
    "document_access_logs": Tipo(_acceso_a_documento, lambda M: M.accessed_at, None,
                                 ("id", "document_id", "user_id")),
    "ai_action_logs": Tipo(_accion_de_ia, lambda M: M.created_at, None, ("id", "user_id")),
    "collaboration_audit_events": Tipo(_auditoria_de_colaboracion, lambda M: M.created_at, None,
                                       ("id", "actor_user_id")),
    # Registro de sincronizacion con Jira (payloads con datos personales).
    "jira_sync_logs": Tipo(_registro_de_jira, lambda M: M.occurred_at, None, ("id", "ticket_id", "jira_issue_key")),
    # 23-11-2026: políticas de cuenta. Historial de contraseñas (hashes) desde el
    # alta; dispositivos de confianza revocados o caducados; solicitudes de
    # segundo administrador decididas; campañas de recertificación cerradas (sus
    # elementos, la evidencia, se van en cascada).
    "password_history": Tipo(_historial_de_contrasenas, lambda M: M.created_at, None, ("id", "user_id")),
    "trusted_devices": Tipo(_dispositivo_de_confianza, lambda M: func.coalesce(M.revoked_at, M.expires_at),
                            lambda M: M.revoked_at.isnot(None) | (M.expires_at < func.now()), ("id", "user_id")),
    "security_change_requests": Tipo(_solicitud_de_seguridad, lambda M: func.coalesce(M.decided_at, M.requested_at),
                                     lambda M: M.status != "pending", ("id", "target_user_id", "requested_by")),
    "access_review_campaigns": Tipo(_campana_de_recertificacion, lambda M: M.closed_at,
                                    lambda M: M.status == "closed", ("id",)),
    # Migracion 200 (A-MOD3): datos personales que vivian en `AppSetting`.
    # Sesiones de voz (numero y transcripcion, cifrados): desde el cierre o, si
    # no se cerraron, desde el alta; se bloquean por ticket o por la huella del
    # numero (`voice_agent_service.huella_del_numero`).
    "sd_voice_sessions": Tipo(_sesion_de_voz, lambda M: func.coalesce(M.closed_at, M.created_at), None,
                              ("id", "ticket_id", "caller_id_hash")),
    # Huecos de la base de conocimiento (preguntas literales de clientes): desde
    # la ultima vez que se pregunto, solo los cerrados.
    "sd_kb_gaps": Tipo(_hueco_de_conocimiento, lambda M: M.last_asked_at,
                       lambda M: M.status.in_(("answered", "dismissed")), ("id", "article_id", "owner_id", "task_id")),
    # Migracion 207: conversaciones de Ask-the-Data (preguntas y consultas de una
    # persona; sin filas de resultado). Desde la ultima pregunta; sus preguntas se
    # van en cascada. Se bloquean por conversacion o por persona.
    "ask_data_conversations": Tipo(_conversacion_ask, lambda M: func.coalesce(M.updated_at, M.created_at), None,
                                   ("id", "user_id")),
    # Migracion 202: «Mi cuaderno». Notas personales: la retención solo alcanza lo
    # que está en la papelera (desde que se tiró); el bloqueo legal por persona
    # (`owner_id`), cuaderno o página impide borrarlo venga de donde venga
    # (papelera, purga, supresión RGPD) y es lo que habilita el acceso excepcional.
    "notebooks": Tipo(_cuaderno, lambda M: M.deleted_at, lambda M: M.deleted_at.isnot(None),
                      ("id", "owner_id", "transferred_from")),
    "notebook_pages": Tipo(_pagina_de_cuaderno, lambda M: M.deleted_at, lambda M: M.deleted_at.isnot(None),
                           ("id", "owner_id", "notebook_id", "section_id", "created_by")),
    "notebook_attachments": Tipo(_adjunto_de_cuaderno, lambda M: M.created_at,
                                 lambda M: M.page_id.in_(_paginas_en_papelera()), ("id", "owner_id", "page_id")),
    # Migracion 203: «Del ticket al PR». Registro de cada ejecucion del agente con el log
    # del contenedor (datos personales ocultos). Cuenta desde que termina; solo las
    # terminadas. Se bloquea por ejecucion, por quien la lanzo, por ticket, tarea o proyecto.
    "ticket_pr_runs": Tipo(_ejecucion_ticket_pr, lambda M: M.finished_at, lambda M: M.status.in_(_ESTADOS_FINALES_TPR),
                           ("id", "launched_by", "ticket_id", "task_id", "project_id")),
    # Migracion 204: instancias de proceso BPM terminadas (con su historial de pasos en
    # cascada), desde que terminan. Se bloquean por instancia, proceso, quien la
    # arranco o clave de negocio (docs/BPM.md §GRC). Las en curso nunca se retienen.
    "bpmn_instances": Tipo(_instancia_bpmn, lambda M: M.ended_at,
                           lambda M: M.status.in_(("completed", "cancelled", "failed")) & M.ended_at.isnot(None),
                           ("id", "process_id", "started_by_user_id", "business_key")),
    # Migracion 206 (docs/PIR.md): revisiones posteriores a la implantacion terminadas
    # (aprobadas, cerradas o descartadas), con sus acciones en cascada, desde que se
    # cerraron o aprobaron. Se bloquean por revision, cambio, proyecto o responsable.
    "pir_reviews": Tipo(_revision_pir,
                        lambda M: func.coalesce(M.cerrado_en, M.aprobado_en, M.updated_at, M.created_at),
                        lambda M: M.estado.in_(("aprobado", "cerrado", "descartado")),
                        ("id", "change_id", "project_id", "responsable_id")),
    # Migracion 209 (docs/portal/CHAT_DEL_PORTAL.md §GRC): chat del portal.
    # Adjuntos (imágenes y ficheros: datos personales), desde la subida; borrar
    # la fila borra el fichero del almacén al confirmar. Rastro de ediciones y
    # borrados (texto anterior), desde el cambio. Llamadas terminadas
    # (metadatos: quién, cuándo, cuánto; sin grabación), desde que acabaron.
    "portal_conversation_attachments": Tipo(_adjunto_del_chat_del_portal, lambda M: M.created_at, None,
                                            ("id", "conversation_id", "uploaded_by_client_id",
                                             "uploaded_by_user_id")),
    "portal_conversation_message_versions": Tipo(_version_de_mensaje_del_portal, lambda M: M.edited_at, None,
                                                 ("id", "message_id", "edited_by_client_id", "edited_by_user_id")),
    "portal_conversation_calls": Tipo(_llamada_del_portal, lambda M: func.coalesce(M.ended_at, M.created_at),
                                      lambda M: M.status.in_(("ended", "declined", "missed")),
                                      ("id", "conversation_id", "initiated_by_user_id", "answered_by_client_id")),
    # Migracion 211: lo mismo para el chat en vivo de Soporte (`sd_channel_*`).
    "sd_channel_attachments": Tipo(_adjunto_del_chat_en_vivo, lambda M: M.created_at, None,
                                   ("id", "conversation_id", "uploaded_by_client_id", "uploaded_by_user_id")),
    "sd_channel_message_versions": Tipo(_version_de_mensaje_del_chat_en_vivo, lambda M: M.edited_at, None,
                                        ("id", "conversation_id", "message_id", "edited_by_client_id",
                                         "edited_by_user_id")),
    "sd_channel_calls": Tipo(_llamada_del_chat_en_vivo, lambda M: func.coalesce(M.ended_at, M.created_at),
                             lambda M: M.status.in_(("ended", "declined", "missed")),
                             ("id", "conversation_id", "initiated_by_user_id", "answered_by_client_id")),
    # Migracion 212 (certificaciones): evidencias (desde su alta), auditorias cerradas
    # (con hallazgos y CAPA en cascada; desde el cierre), programas cerrados, incidentes
    # NIS2 cerrados o descartados (con sus comunicaciones), auditores externos (dato
    # personal; desde el fin de su periodo o su supresion) y lo que consultaron.
    "cert_evidencias": Tipo(_cert_modelo("CertEvidencia"), lambda M: M.created_at, None,
                            ("id", "programa_id", "control_id", "document_id")),
    "cert_auditorias": Tipo(_cert_modelo("CertAuditoria"), lambda M: func.coalesce(M.cerrada_en, M.created_at),
                            lambda M: M.estado == "cerrada", ("id", "programa_id", "entidad_id", "auditor_id")),
    "cert_programas": Tipo(_cert_modelo("CertPrograma"), lambda M: func.coalesce(M.updated_at, M.created_at),
                           lambda M: M.estado == "cerrado", ("id", "responsable_id")),
    "cert_incidentes": Tipo(_cert_modelo("CertIncidente"), lambda M: func.coalesce(M.cerrado_en, M.created_at),
                            lambda M: M.estado.in_(("cerrado", "descartado")), ("id", "ticket_id", "programa_id")),
    "cert_auditores": Tipo(_cert_modelo("CertAuditor"), lambda M: func.coalesce(M.suprimido_en, M.updated_at,
                                                                                M.created_at),
                           lambda M: M.activo.is_(False), ("id", "entidad_id", "email")),
    "cert_accesos_registro": Tipo(_cert_modelo("CertAccesoRegistro"), lambda M: M.en, None, ("id", "acceso_id")),
}



def _paginas_en_papelera():
    from sqlalchemy import select
    P = _pagina_de_cuaderno()
    return select(P.id).where(P.deleted_at.isnot(None))


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
        org = getattr(obj, TIPOS[clave].columna_empresa, None)
        if org not in por_org:
            por_org[org] = bloqueos_activos(session, org)
        b = _bloqueo_de(clave, obj, por_org[org])
        if b is not None:
            raise BloqueoLegalActivo(b.case_reference)
