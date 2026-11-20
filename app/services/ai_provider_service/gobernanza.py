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
        return "es"


def _prefijos_de_bloqueo_de_entrada() -> tuple[str, ...]:
    from app.services.textos_de_salida import TEXTOS
    return tuple(v.split("{", 1)[0] for v in TEXTOS["gobernanza.mensaje_bloqueado"].values())


def es_bloqueo_de_entrada(texto) -> bool:
    """Si `texto` es el aviso de «mensaje bloqueado por politica», en cualquier idioma."""
    return isinstance(texto, str) and texto.startswith(_prefijos_de_bloqueo_de_entrada())


def _resolver_usuario_de_gobernanza(db: Session, user_id, skip_guardrails: bool):
    """El usuario contra el que se evaluan las politicas, resuelto una sola vez.

    Se reutiliza para la entrada y para la salida: dos consultas para el mismo
    dato en la misma llamada no aportan nada.

    Devuelve None ante cualquier problema, y eso desactiva los guardrails de esa
    llamada. Es el comportamiento del original; queda anotado porque no es
    obvio: sin usuario no hay politicas que aplicar, asi que un fallo al
    cargarlo abre el paso en vez de cerrarlo.
    """
    if skip_guardrails or not user_id:
        return None
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
    return None


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
