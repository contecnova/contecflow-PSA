"""Administración de colaboración: Web Push, OAuth de integraciones y calendario.

Auditoría 2026-08 (hallazgo 22). Estas operaciones vivían en
`endpoints/collaboration/admin.py` con **8 puntos de acceso directo a base**.

Al bajarlas aquí salieron tres cosas que el endpoint no dejaba ver:

1. **El parámetro `days` del calendario no se usaba.** El endpoint lo declaraba
   con rango `1..60` y lo ignoraba: pedía 20 eventos a cada proveedor sin acotar
   nada. Peor, ambos proveedores se consultaban ordenando por fecha de inicio
   ascendente y sin límite inferior, así que lo que se devolvía como «eventos
   próximos» eran los eventos **más antiguos** del calendario. La ventana se
   aplica ahora de verdad (ver `_integrations_clients`).

2. **Un proveedor que falla desaparecía sin rastro.** El bucle tenía un
   `except Exception: continue` mudo, y los clientes devuelven `{"error": ...}`
   en vez de lanzar, así que una integración con el token caducado aportaba cero
   eventos mientras seguía anunciándose como conectada. Ahora cada proveedor
   informa de su estado y el fallo se registra.

3. **El alta de suscripción push reasigna la fila a quien llama.** Se conserva
   —es lo que hace falta en un equipo compartido, donde el mismo navegador pasa
   de un usuario a otro— pero se acota a la organización de forma explícita y el
   cambio de dueño se audita, porque desde el servidor no se puede distinguir un
   relevo legítimo de alguien que reutiliza un endpoint ajeno.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.collaboration import (
    CollaborationIntegration,
    CollaborationPushSubscription,
)
from app.services.collaboration import _audit
from app.services.collaboration._integrations import (
    PROVIDERS,
    auth_url_for,
    encrypt,
)
from app.services.collaboration._permissions import _org

_log = logging.getLogger(__name__)

#: Longitud que se conserva del `User-Agent` de la suscripción. La columna es
#: `String(255)`; recortar aquí evita un error de base por un agente largo.
MAX_LONGITUD_USER_AGENT = 255

#: Clases de integración que aportan eventos a la vista de calendario agregada.
PROVEEDORES_DE_CALENDARIO = ("google_calendar", "microsoft_365")

#: Claves del cuerpo del token que se guardan en `config` porque el proveedor
#: las necesita en llamadas posteriores (`cloud_id` de Jira, por ejemplo) y no
#: caben en las columnas de token.
CLAVES_DE_TOKEN_A_CONFIG = ("cloud_id", "scope", "token_type", "id_token")


# ── Web Push ────────────────────────────────────────────────────────────────

def _suscripcion_por_endpoint(db: Session, endpoint: str):
    """La fila de ese endpoint, sea de la organización que sea.

    La columna `endpoint` es **única global**, así que hay que poder ver una fila
    de otra organización: sin eso, el alta choca contra la restricción única y
    devuelve un 500. Es una consulta de tres columnas sobre una tabla, no una vía
    de lectura de datos de otro tenant, y por eso se declara el salto en vez de
    disimularlo.

    **Corrección de auditoría 2026-08.** Aquí decía que ir «por Core y no por el
    ORM» bastaba, porque «el filtro global de tenant sólo actúa sobre sentencias
    ORM». **Era falso.** `TenantSession.execute()` intercepta cualquier `Select`
    y `_extract_models_from_select` **resuelve la `Table` de vuelta a su clase
    mapeada** por el registro de SQLAlchemy — para eso se escribió—, así que esta
    consulta salía filtrada igual y la fila ajena seguía siendo invisible. Es
    decir: el 500 que este ayudante existe para evitar **seguía ocurriendo en
    producción**.

    No lo vio nadie porque el test que lo cubre enganchaba el filtro a mano sobre
    una sesión de pruebas que no era una `TenantSession`, y esa sí deja pasar el
    Core. Se descubrió al hacer que la suite use la factoría de producción.

    Ahora se usa `sin_filtro_de_tenant`, que es el único mecanismo que respetan
    las tres capas.
    """
    from sqlalchemy import select

    from app.db.session import sin_filtro_de_tenant

    tabla = CollaborationPushSubscription.__table__
    with sin_filtro_de_tenant(db):
        return db.execute(
            select(tabla.c.id, tabla.c.organization_id, tabla.c.user_id)
            .where(tabla.c.endpoint == endpoint)
        ).first()


def guardar_suscripcion_push(db: Session, user, payload: dict) -> dict:
    """Da de alta —o actualiza— la suscripción Web Push de este navegador.

    Devuelve `{"ok": True, "reasignada": bool}`. `reasignada` es cierto cuando
    la fila estaba a nombre de otro usuario: una suscripción Web Push pertenece
    al registro del service worker —al navegador—, no a la sesión, así que el
    mismo endpoint reaparece cuando otra persona entra en ese equipo. Es el caso
    normal del puesto compartido, y puede cruzar organizaciones (un consultor
    con dos cuentas). Sólo eso se audita: renovar la propia suscripción, que es
    lo habitual, no genera ruido.
    """
    sub = payload.get("subscription") or payload
    endpoint = sub.get("endpoint")
    claves = sub.get("keys") or {}
    p256dh = claves.get("p256dh")
    auth = claves.get("auth")
    if not (endpoint and p256dh and auth):
        raise HTTPException(
            400, "subscription.endpoint + keys.p256dh + keys.auth requeridos")

    org = _org(user)
    existente = _suscripcion_por_endpoint(db, endpoint)
    reasignada = False
    org_anterior = None
    fila_id = None

    if existente:
        fila_id = existente.id
        reasignada = existente.user_id != user.id or existente.organization_id != org
        if existente.organization_id != org:
            org_anterior = existente.organization_id
        # UPDATE por clave primaria sobre una fila que puede ser de otra
        # organización — la que provocaba el choque de unicidad.
        #
        # **Corrección de auditoría 2026-08.** Aquí decía que «el filtro global
        # de tenant no toca las sentencias de escritura», y eso es verdad de
        # `do_orm_execute` y **falso de lo que hace esta línea**:
        # `TenantSession.query()` añade el filtro a la consulta, y `.update()`
        # hereda ese `WHERE`. Resultado: el UPDATE no encontraba la fila ajena y
        # **actualizaba cero filas en silencio**, así que el traspaso que este
        # código anuncia —y que audita a continuación— no llegaba a ocurrir.
        #
        # Es el mismo error de fondo que en `_suscripcion_por_endpoint`: suponer
        # que el aislamiento es una sola capa. Son tres, y la única bandera que
        # respetan las tres es `bypass_tenant_filter`.
        from app.db.session import sin_filtro_de_tenant

        with sin_filtro_de_tenant(db):
            db.query(CollaborationPushSubscription).filter(
                CollaborationPushSubscription.id == fila_id
            ).update({
                "organization_id": org,
                "user_id": user.id,
                "client_user_id": None,
                "p256dh_key": p256dh,
                "auth_key": auth,
                "is_active": True,
                "user_agent": (payload.get("user_agent") or "")[:MAX_LONGITUD_USER_AGENT],
            }, synchronize_session=False)
    else:
        fila = CollaborationPushSubscription(
            organization_id=org,
            user_id=user.id,
            endpoint=endpoint,
            p256dh_key=p256dh,
            auth_key=auth,
            user_agent=(payload.get("user_agent") or "")[:MAX_LONGITUD_USER_AGENT],
        )
        db.add(fila)
        db.flush()
        fila_id = fila.id

    if reasignada:
        # Un endpoint sólo lo conoce el navegador al que lo emitió el servicio
        # de push; desde el servidor no hay forma de distinguir un relevo
        # legítimo de alguien que reutiliza un endpoint ajeno. Se conserva el
        # comportamiento —sin él el puesto compartido no funciona— y se deja
        # constancia. Si cruza organizaciones se anota **en las dos**: la que
        # pierde las notificaciones tiene que poder verlo en su propia
        # auditoría, no sólo la que las gana.
        datos = {
            "endpoint_suffix": endpoint[-12:],
            "organizacion_anterior": org_anterior,
        }
        _audit.write(
            db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
            action="push.subscription.reassigned",
            entity_type="collaboration_push_subscription",
            entity_id=fila_id, payload=datos,
        )
        if org_anterior:
            _audit.write(
                db, organization_id=org_anterior, actor_user_id=None,
                actor_client_id=None,
                action="push.subscription.released",
                entity_type="collaboration_push_subscription",
                entity_id=fila_id, payload=datos,
            )

    # Un solo `commit` al final: `_audit.write` sólo hace `add` y deja la
    # confirmación a quien llama, así que auditar despues de confirmar dejaba
    # los registros sin guardar. Además hace el cambio atómico: o se traspasa la
    # suscripción y queda constancia, o no pasa ninguna de las dos cosas.
    db.commit()
    return {"ok": True, "reasignada": reasignada}


def borrar_suscripcion_push(db: Session, user, endpoint: str) -> int:
    """Borra la suscripción de este endpoint que pertenezca a este usuario."""
    borradas = (
        db.query(CollaborationPushSubscription)
        .filter(
            CollaborationPushSubscription.endpoint == endpoint,
            CollaborationPushSubscription.user_id == user.id,
        )
        .delete()
    )
    db.commit()
    return int(borradas)


# ── OAuth de integraciones ──────────────────────────────────────────────────

def url_de_oauth(db: Session, user, integration_id: str) -> str:
    """La URL de autorización del proveedor de esa integración.

    Las tres condiciones dan errores distintos a propósito: la integración no
    existe (404), existe pero su clase no habla OAuth (400) y habla OAuth pero
    el despliegue no tiene credenciales (503). Son tres problemas de tres
    responsables distintos —el usuario, el producto y quien despliega— y
    colapsarlos en uno haría el segundo indiagnosticable.
    """
    fila = (
        db.query(CollaborationIntegration)
        .filter(
            CollaborationIntegration.id == integration_id,
            CollaborationIntegration.organization_id == _org(user),
        )
        .first()
    )
    if not fila:
        raise HTTPException(404, "Integración no encontrada")
    if fila.kind not in PROVIDERS:
        raise HTTPException(400, "Proveedor sin OAuth")
    url = auth_url_for(fila.kind, fila.id)
    if not url:
        raise HTTPException(503, f"Faltan credenciales OAuth para {fila.kind}")
    return url


def guardar_tokens_de_oauth(
    db: Session, integration_id: str, token_data: dict,
) -> Optional[str]:
    """Cifra y guarda los tokens del callback. Devuelve la clase, o `None`.

    `None` significa que la integración ya no existe —se borró entre el inicio
    del flujo y el retorno del proveedor—, no que el guardado fallara.

    Esta función NO acota por organización, y es correcto: la ejecuta el
    callback de OAuth, que llega sin sesión de usuario. Lo que autoriza la
    escritura es el `state` firmado que `handle_callback` ya validó antes de
    entregar el `integration_id`.
    """
    fila = (
        db.query(CollaborationIntegration)
        .filter(CollaborationIntegration.id == integration_id)
        .first()
    )
    if not fila:
        return None

    fila.access_token_enc = encrypt(token_data.get("access_token"))
    fila.refresh_token_enc = encrypt(token_data.get("refresh_token"))
    caduca_en = token_data.get("expires_in")
    if caduca_en:
        fila.token_expires_at = utcnow() + timedelta(seconds=int(caduca_en))
    config = dict(fila.config or {})
    for clave in CLAVES_DE_TOKEN_A_CONFIG:
        if clave in token_data:
            config[clave] = token_data[clave]
    fila.config = config
    fila.is_enabled = True
    db.commit()
    return fila.kind


# ── Calendario agregado ─────────────────────────────────────────────────────

def integraciones_de_calendario(db: Session, user) -> list[CollaborationIntegration]:
    return (
        db.query(CollaborationIntegration)
        .filter(
            CollaborationIntegration.organization_id == _org(user),
            CollaborationIntegration.is_enabled == True,  # noqa: E712
            CollaborationIntegration.kind.in_(PROVEEDORES_DE_CALENDARIO),
        )
        .all()
    )


def _evento_de_google(ev: dict) -> dict:
    inicio = ev.get("start") or {}
    fin = ev.get("end") or {}
    return {
        "id": ev.get("id"),
        "title": ev.get("summary"),
        # Un evento de día completo trae `date` y no `dateTime`.
        "start": inicio.get("dateTime") or inicio.get("date"),
        "end": fin.get("dateTime") or fin.get("date"),
        "source": "google",
        "link": ev.get("htmlLink"),
    }


def _evento_de_m365(ev: dict) -> dict:
    return {
        "id": ev.get("id"),
        "title": ev.get("subject"),
        "start": (ev.get("start") or {}).get("dateTime"),
        "end": (ev.get("end") or {}).get("dateTime"),
        "source": "m365",
        "link": ev.get("webLink"),
    }


async def eventos_de_calendario(db: Session, user, dias: int) -> dict:
    """Eventos de los próximos `dias` días, de todos los proveedores activos.

    Devuelve también el estado por proveedor. Antes se devolvía sólo
    `providers_connected` con las integraciones habilitadas, que es una promesa
    que la lista de eventos no respalda: una integración habilitada con el token
    caducado figuraba como conectada y aportaba cero eventos, sin que ni el
    cliente ni el log dijeran nada.
    """
    from app.core.async_db import run_db
    from app.services.collaboration._integrations_clients import (
        google_calendar_list,
        m365_calendar_list,
    )

    integraciones = await run_db(integraciones_de_calendario, db, user)

    ahora = utcnow()
    desde_iso = ahora.isoformat()
    hasta_iso = (ahora + timedelta(days=dias)).isoformat()
    tope = settings.COLLAB_CALENDAR_MAX_EVENTS

    eventos: list[dict] = []
    proveedores: list[dict] = []
    for integracion in integraciones:
        estado = {"kind": integracion.kind, "id": integracion.id, "ok": True, "error": None}
        try:
            if integracion.kind == "google_calendar":
                respuesta = await google_calendar_list(
                    integracion, max_results=tope,
                    desde_iso=desde_iso, hasta_iso=hasta_iso)
                crudos = (respuesta.get("body") or {}).get("items") or []
                nuevos = [_evento_de_google(ev) for ev in crudos]
            else:
                respuesta = await m365_calendar_list(
                    integracion, top=tope,
                    desde_iso=desde_iso, hasta_iso=hasta_iso)
                crudos = (respuesta.get("body") or {}).get("value") or []
                nuevos = [_evento_de_m365(ev) for ev in crudos]
        except Exception as exc:  # el cliente ya captura lo suyo; esto es el resto
            _log.warning(
                "calendario: la integración %s (%s) no se pudo consultar",
                integracion.id, integracion.kind, exc_info=True)
            estado.update(ok=False, error=str(exc))
        else:
            # Los clientes no lanzan: devuelven `{"error": ...}`. Sin esto, un
            # token caducado era indistinguible de una agenda vacía.
            if respuesta.get("error"):
                _log.warning(
                    "calendario: la integración %s (%s) respondió con error: %s",
                    integracion.id, integracion.kind, respuesta["error"])
                estado.update(ok=False, error=respuesta["error"])
            else:
                eventos.extend(nuevos)
        proveedores.append(estado)

    # Orden por inicio. Los que vienen sin fecha van primero con la cadena
    # vacía; son datos incompletos del proveedor y es mejor verlos que perderlos.
    eventos.sort(key=lambda e: e.get("start") or "")
    return {
        "events": eventos,
        "window_days": dias,
        "providers": proveedores,
        # Se mantiene por compatibilidad con el cliente actual: ahora son los
        # proveedores que han respondido, no los que están habilitados.
        "providers_connected": [p["kind"] for p in proveedores if p["ok"]],
    }
