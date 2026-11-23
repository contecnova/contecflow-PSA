"""Guardarrailes de gobernanza de entrada y salida (de `call_ai` y del agente).

Parte de `app.services.ai_provider_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.user import User

_logger = logging.getLogger("ai_provider_service")


# 19-11-2026: los textos de bloqueo los escribe el sistema: salen en el idioma
# del usuario gobernado (`gobernanza.*` en `textos_de_salida`). El nombre de la
# politica (`blocked_by`) lo puso la empresa y sale tal cual.

def _idioma_del_gobernado(db: Session, usuario) -> str:
    from app.services.formato_regional import idioma_de_salida
    try:
        return idioma_de_salida(db, user_id=getattr(usuario, "id", None),
                                org_id=getattr(usuario, "organization_id", None))
    except Exception:  # noqa: BLE001 - un bloqueo nunca deja de salir por el idioma
        _logger.debug("gobernanza: idioma no legible", exc_info=True)
        from app.services.textos_de_salida import IDIOMA_DE_RESPALDO
        return IDIOMA_DE_RESPALDO


def _prefijos_de_bloqueo_de_entrada() -> tuple[str, ...]:
    from app.services.textos_de_salida import TEXTOS
    return tuple(v.split("{", 1)[0] for v in TEXTOS["gobernanza.mensaje_bloqueado"].values())


def es_bloqueo_de_entrada(texto) -> bool:
    """Si `texto` es el aviso de «mensaje bloqueado por politica», en cualquier idioma."""
    return isinstance(texto, str) and texto.startswith(_prefijos_de_bloqueo_de_entrada())


class SujetoDeSistema:
    """Sujeto de las politicas en una llamada sin usuario (trabajo de fondo,
    auto-resolucion de tickets, canales).

    Auditoria 2026-11-22 (C-SD2, arquitectura #7): sin `user_id`, `call_ai` no
    aplicaba guardarrailes ni redaccion de datos personales. Ahora, si la
    llamada tiene empresa, se evaluan sus politicas con este sujeto: rol
    `ROL`, sin id de usuario (el registro de guardarrailes queda con
    `user_id` NULL, que es lo que es).
    """

    ROL = "system"

    def __init__(self, organization_id) -> None:
        self.id = None
        self.organization_id = organization_id
        self.role = self.ROL


def _resolver_usuario_de_gobernanza(db: Session, user_id, skip_guardrails: bool,
                                    organization_id=None):
    """El usuario contra el que se evaluan las politicas, resuelto una sola vez.

    Se reutiliza para la entrada y para la salida: dos consultas para el mismo
    dato en la misma llamada no aportan nada.

    Sin usuario pero con empresa, el sujeto de sistema de esa empresa
    (`SujetoDeSistema`). Sin ninguno de los dos (o con `skip_guardrails`),
    None: no hay politicas que aplicar. Un fallo al cargar el usuario tambien
    devuelve None y abre el paso, como el original.
    """
    if skip_guardrails:
        return None
    if not user_id:
        return SujetoDeSistema(organization_id) if organization_id else None
    try:
        return db.query(User).filter(User.id == user_id).first()
    except Exception:
        _logger.warning(
            "Failed to load governance_user for user_id=%s", user_id, exc_info=True
        )
        return None


def _aplicar_guardrail_de_entrada(db: Session, messages: list, governance_user,
                                  module: str, skip_guardrails: bool):
    """Evalua las politicas sobre el ultimo mensaje del usuario.

    Devuelve un texto de bloqueo si hay que cortar, o None para seguir. Cuando
    la politica redacta, ESCRIBE el texto redactado en `messages` — a proposito:
    lo que se manda al modelo tiene que ser el texto ya redactado, no el
    original.
    """
    if skip_guardrails or not governance_user or not messages:
        return None

    last_user_msg = next(
        (m for m in reversed(messages) if m.get("role") == "user"), None
    )
    if not last_user_msg or not isinstance(last_user_msg.get("content"), str):
        return None

    try:
        from app.services.ai_governance import check_prompt as _gr_check_prompt
        gr = _gr_check_prompt(last_user_msg["content"], governance_user, module, db)
    except Exception as gr_exc:
        # Se sigue a proposito: un fallo del motor de politicas no puede dejar
        # la aplicacion sin IA. Queda en el log.
        _logger.warning("Guardrail prompt check failed (continuing): %s", gr_exc)
        return None

    if not gr.allowed:
        from app.services.textos_de_salida import texto
        return texto("gobernanza.mensaje_bloqueado", _idioma_del_gobernado(db, governance_user),
                     politica=gr.blocked_by or "policy")
    if gr.redacted_text:
        last_user_msg["content"] = gr.redacted_text
    # A8 (auditoría 22-11-2026): las políticas de redacción se aplican también
    # al RESTO de la conversación (turnos anteriores y resultados de
    # herramientas), no solo al último mensaje: un dato personal de la base que
    # una herramienta devuelve ya no viaja en claro al proveedor. Solo redacta
    # (no bloquea por el contexto: bloquear es por lo que pide la persona).
    for m in messages:
        if m is last_user_msg or not isinstance(m.get("content"), str) or not m.get("content"):
            continue
        m["content"] = redactar_contexto(db, m["content"], governance_user, module)
    return None


def redactar_contexto(db: Session, texto: Optional[str], governance_user, module: str) -> Optional[str]:
    """A8: el texto con la redacción de las políticas de la empresa (contexto del
    sistema, turnos y resultados de herramientas). Si falla el motor, el texto
    sin cambios (igual que la entrada: un fallo del motor no deja sin IA)."""
    if not texto or not governance_user:
        return texto
    try:
        from app.services.ai_governance import check_prompt as _gr_check_prompt
        gr = _gr_check_prompt(texto, governance_user, module, db)
    except Exception:
        _logger.warning("redacción del contexto de IA: fallo del motor (sigue sin redactar)", exc_info=True)
        return texto
    return gr.redacted_text or texto


def _aplicar_guardrail_de_salida(db: Session, texto: str, governance_user,
                                 module: str, skip_guardrails: bool, error_msg) -> str:
    """Evalua las politicas sobre la respuesta del modelo.

    No se evalua cuando la llamada fallo: no hay respuesta que revisar y el
    texto que se devuelve es el mensaje de error del proveedor.
    """
    if skip_guardrails or not governance_user or not texto or error_msg is not None:
        return texto
    try:
        from app.services.ai_governance import check_output as _gr_check_output
        gr_out = _gr_check_output(texto, governance_user, module, db)
    except Exception as gr_exc:
        _logger.warning("Guardrail output check failed (continuing): %s", gr_exc)
        return texto

    if not gr_out.allowed:
        from app.services.textos_de_salida import texto
        return texto("gobernanza.respuesta_bloqueada", _idioma_del_gobernado(db, governance_user))
    if gr_out.redacted_text:
        return gr_out.redacted_text
    return texto


def guardrail_de_instruccion(db: Session, usuario, instruccion: str, module: str = "nexusagent") -> tuple:
    """(instrucción, bloqueo) con las políticas de entrada de `call_ai`.

    Revisión 2026-11: los turnos del agente no pasan por `call_ai`, así que sus
    guardarraíles no se aplicaban (sólo una lista de palabras). Si la política
    redacta, devuelve la instrucción redactada; si bloquea, el texto de bloqueo.
    """
    gobernado = _resolver_usuario_de_gobernanza(db, getattr(usuario, "id", None), False)
    mensajes = [{"role": "user", "content": instruccion}]
    bloqueo = _aplicar_guardrail_de_entrada(db, mensajes, gobernado, module, False)
    return mensajes[0]["content"], bloqueo


def guardrail_de_respuesta(db: Session, usuario, texto: str, module: str = "nexusagent") -> str:
    """La respuesta final del agente con las políticas de salida de `call_ai`."""
    gobernado = _resolver_usuario_de_gobernanza(db, getattr(usuario, "id", None), False)
    return _aplicar_guardrail_de_salida(db, texto, gobernado, module, False, None)
