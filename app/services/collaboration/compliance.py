"""Retención, legal hold, auditoría y eDiscovery de colaboración.

Auditoría 2026-08 (hallazgo 22). Estas operaciones vivían en
`endpoints/collaboration/compliance.py` con **18 puntos de acceso directo a
base**. Al moverlas aquí apareció un defecto en el control de *legal hold*, que
es lo que se cuenta abajo.

## El defecto: un legal hold que no retenía lo que decía retener

`_legal_held_message_ids` recogía las tres listas de custodia de cada caso
activo —usuarios, clientes y canales— y **usaba sólo la de usuarios**:

```python
user_ids, client_ids, channel_ids = set(), set(), set()
for r in rows:
    user_ids.update(r.custodian_user_ids or [])
    client_ids.update(r.custodian_client_ids or [])      # recogido y no usado
    channel_ids.update(r.channel_ids or [])              # recogido y no usado
msg_q = db.query(CollaborationMessage.id).filter(...organization_id...)
if user_ids:
    msg_q = msg_q.filter(CollaborationMessage.user_id.in_(user_ids))
return {r[0] for r in msg_q.all()}
```

Dos consecuencias, las dos malas y en direcciones opuestas:

1. **Un caso que nombra sólo clientes o sólo canales no protegía nada.** Sus
   mensajes entraban en el barrido de retención y se marcaban como borrados con
   el cuerpo sustituido por `[retention purge]`. Es **destrucción de material
   bajo retención legal**, que es exactamente lo que un legal hold existe para
   impedir.
2. **Y un caso sin custodios de usuario dejaba la retención sin efecto.** Con
   `user_ids` vacío no se añadía ningún filtro, así que la consulta devolvía
   **todos** los identificadores de mensaje de la organización: el barrido los
   consideraba retenidos y no borraba nada nunca. El almacenamiento crece sin
   que nadie vea un error.

Ninguna de las dos daba error. La primera borra callando y la segunda no borra
callando.

**El arreglo** es la disyunción de las tres condiciones, que es lo que significa
la custodia: un mensaje está retenido si lo escribió un usuario custodio, **o**
lo escribió un cliente custodio, **o** pertenece a la conversación de un canal
retenido. Y si un caso activo no nombra a nadie, no retiene nada — en vez de
retenerlo todo.
"""
from __future__ import annotations
import logging

import json
from datetime import timedelta
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.collaboration import (
    CollaborationAuditEvent,
    CollaborationChannel,
    CollaborationLegalHold,
    CollaborationMessage,
    CollaborationRetentionPolicy,
)
from app.models.settings import AppSetting
from app.services.collaboration import audit_log
from app.services.collaboration._permissions import _org
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error

#: Clave del ajuste por tenant con los meses de retención por defecto y el tope.
RETENTION_SETTINGS_KEY = "collaboration.retention.settings"

#: Valores por defecto de la retención de un tenant que no la ha configurado.
#: Un año por defecto y cinco de tope: el tope existe para que nadie configure
#: una retención tan larga que equivalga a no borrar nunca.
RETENCION_POR_DEFECTO = {"default_months": 12, "max_months": 60}

#: Días que se cuentan por mes al calcular el corte de retención. Es una
#: aproximación deliberada —los meses no son iguales— y se deja explícita para
#: que quien lea el corte sepa que no es un cálculo de calendario.
DIAS_POR_MES = 30

#: Tope de mensajes que devuelve una exportación de eDiscovery. Sin tope, un
#: caso amplio intenta serializar la mensajería completa de la organización en
#: una sola respuesta.
MAX_MENSAJES_EXPORTADOS = 20_000

#: Topes de los listados de auditoría y decisiones.
MAX_DECISIONES = 500
MAX_EVENTOS_DE_AUDITORIA = 1000

#: Cuántas palabras clave de una petición de eDiscovery se aplican. Cada una
#: añade un `ILIKE` a la consulta, y son acumulativos: con muchas, la consulta
#: se vuelve impracticable y además no encuentra nada porque exige todas.
MAX_PALABRAS_CLAVE = 5


# ── Ajustes de retención del tenant ─────────────────────────────────────────

def _fila_de_ajustes(db: Session, org_id: str):
    return (
        db.query(AppSetting)
        .filter(
            AppSetting.organization_id == org_id,
            AppSetting.key == RETENTION_SETTINGS_KEY,
        )
        .first()
    )


def _normalizar_ajustes(datos: dict) -> dict:
    """Los dos valores, saneados con un mínimo de un mes.

    El `max(1, ...)` no es cosmético: un cero o un negativo darían un corte de
    retención en el futuro, y el barrido borraría **todos** los mensajes.
    """
    return {
        "default_months": max(1, int(datos.get("default_months", 12))),
        "max_months": max(1, int(datos.get("max_months", 60))),
    }


def get_retention_settings(db: Session, org_id: str) -> dict:
    fila = _fila_de_ajustes(db, org_id)
    if not fila or not fila.value:
        return dict(RETENCION_POR_DEFECTO)
    try:
        return _normalizar_ajustes(json.loads(fila.value))
    except Exception:
        # Un ajuste ilegible no puede dejar la retención sin valores: se cae a
        # los de por defecto en vez de propagar.
        logging.getLogger(__name__).debug("get_retention_settings: excepcion ignorada", exc_info=True)
        return dict(RETENCION_POR_DEFECTO)


def set_retention_settings(db: Session, org_id: str, datos: dict) -> dict:
    valor = _normalizar_ajustes(datos)
    serializado = json.dumps(valor, ensure_ascii=True, separators=(",", ":"))
    fila = _fila_de_ajustes(db, org_id)
    if not fila:
        db.add(AppSetting(
            organization_id=org_id, key=RETENTION_SETTINGS_KEY,
            value=serializado,
            description="Tenant retention defaults for collaboration",
        ))
    else:
        fila.value = serializado
    db.commit()
    return valor


# ── Políticas de retención ──────────────────────────────────────────────────

def list_policies(db: Session, user) -> list[CollaborationRetentionPolicy]:
    return (
        db.query(CollaborationRetentionPolicy)
        .filter(CollaborationRetentionPolicy.organization_id == _org(user))
        .all()
    )


def create_policy(db: Session, user, datos: dict) -> CollaborationRetentionPolicy:
    """Crea una política, sin dejar pasar del tope del tenant."""
    from app.services.collaboration.workspaces import get_or_create_workspace

    org = _org(user)
    ws = get_or_create_workspace(db, user)
    ajustes = get_retention_settings(db, org)
    meses = datos.get("retention_months")
    # 19-11-2026: sin meses, los propuestos por la empresa (antes 24 fijos en el
    # esquema y en la pantalla). Y ninguna política por debajo del mínimo de
    # retención de la empresa (`RETENTION_MIN_DAYS`, el de las demás políticas):
    # con 0 meses el corte del barrido era «ahora» y se borraba todo el chat.
    from app.services.settings_service import valores_de_negocio as _vn
    if meses is None:
        meses = _vn.retencion_propuesta_del_chat(db, org)
    minimo = _vn.meses_minimos_de_retencion(db, org)
    if meses < minimo:
        raise error(422, "retencion_minimo_dias", detail=f"Mínimo {minimo * DIAS_POR_MES} días (RETENTION_MIN_DAYS)",
                    dias=minimo * DIAS_POR_MES)
    if meses > ajustes["max_months"]:
        raise error(422, "retencion_supera_maximo", detail=f"retention_months exceeds tenant max ({ajustes['max_months']})", max=ajustes['max_months'])

    fila = CollaborationRetentionPolicy(
        organization_id=org, workspace_id=ws.id,
        name=datos.get("name"), scope=datos.get("scope"),
        target_id=datos.get("target_id"),
        retention_months=meses, apply_to=datos.get("apply_to"),
    )
    db.add(fila)
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="retention.created", entity_type="retention_policy",
        entity_id=fila.id, payload=datos,
    )
    db.commit()
    return fila


class _PoliticaPorDefecto:
    """La política implícita cuando el tenant no ha definido ninguna.

    Antes se construía con `type("_P", (), {...})()`, una clase anónima creada al
    vuelo. Se escribe como clase con nombre para que quien lea el barrido vea
    qué campos usa y de dónde sale el número de meses.
    """

    scope = "workspace"
    target_id = None

    def __init__(self, retention_months: int):
        self.retention_months = retention_months


#: Precedencia de ámbitos: manda la política MÁS ESPECÍFICA que alcanza la
#: conversación (canal > equipo > tipo > espacio). Auditoría 22-11-2026 (C3).
_ORDEN_DE_AMBITO = ("channel", "team", "type", "workspace")

#: Lo que purga este barrido: el cuerpo de los mensajes. Una política solo de
#: adjuntos o de llamadas no toca mensajes (su purga no existe aún: M77).
_APLICA_A_MENSAJES = ("all", "messages", None, "")


def _conversaciones_de(db: Session, org: str, pol) -> Optional[set]:
    """Las conversaciones que alcanza la política; None = todas las de su ámbito
    (el espacio de la política o, por defecto, toda la empresa)."""
    from app.models.collaboration import CollaborationConversation
    scope = (getattr(pol, "scope", None) or "workspace").lower()
    target = getattr(pol, "target_id", None)
    if scope == "channel":
        filas = db.query(CollaborationChannel.conversation_id).filter(
            CollaborationChannel.organization_id == org, CollaborationChannel.id == target).all()
        return {f[0] for f in filas}
    if scope == "team":
        filas = db.query(CollaborationChannel.conversation_id).filter(
            CollaborationChannel.organization_id == org, CollaborationChannel.team_id == target).all()
        return {f[0] for f in filas}
    q = db.query(CollaborationConversation.id).filter(CollaborationConversation.organization_id == org)
    ws = getattr(pol, "workspace_id", None)
    if ws:
        q = q.filter(CollaborationConversation.workspace_id == ws)
    if scope == "type":
        if not target:
            return set()
        q = q.filter(CollaborationConversation.kind == target)
    elif scope != "workspace":
        # Ámbito desconocido: no alcanza nada (antes, toda la empresa).
        return set()
    elif not ws:
        return None
    return {f[0] for f in q.all()}


def _plan_de_retencion(db: Session, org: str, politicas: list) -> list[tuple]:
    """[(meses, conversaciones | None, excluir)] sin solapes: cada conversación
    la gobierna solo su política más específica; a igual ámbito y destino, la
    de retención MÁS LARGA (en la duda, no se destruye)."""
    plan: list[tuple] = []
    cubiertas: set = set()
    for scope in _ORDEN_DE_AMBITO:
        de_este = [p for p in politicas if (getattr(p, "scope", None) or "workspace").lower() == scope]
        # Mismo destino: la más larga.
        por_destino: dict = {}
        for p in de_este:
            clave = (getattr(p, "target_id", None), getattr(p, "workspace_id", None))
            if clave not in por_destino or p.retention_months > por_destino[clave].retention_months:
                por_destino[clave] = p
        nuevas: set = set()
        for p in por_destino.values():
            convs = _conversaciones_de(db, org, p)
            if convs is None:
                plan.append((p.retention_months, None, set(cubiertas)))
                continue
            convs = convs - cubiertas
            if convs:
                plan.append((p.retention_months, convs, set()))
                nuevas |= convs
        cubiertas |= nuevas
    return plan


def _condicion_de_bloqueo_general(db: Session, org: str):
    """Mensajes alcanzados por un bloqueo legal GENERAL (`legal_holds`, la pantalla
    de Gobierno) con entidad `*` o `collaboration_messages` (C3)."""
    from sqlalchemy import false as _false
    from app.db.bloqueo_legal import bloqueos_activos
    campos = {"id": CollaborationMessage.id, "user_id": CollaborationMessage.user_id,
              "conversation_id": CollaborationMessage.conversation_id}
    partes = [campos[b.field] == b.value for b in bloqueos_activos(db, org)
              if b.entity in ("*", "collaboration_messages") and b.field in campos]
    return or_(*partes) if partes else _false()


def run_retention(db: Session, user) -> dict:
    """Marca como borrados los mensajes vencidos según las políticas activas.

    Auditoría 22-11-2026 (C3): antes cada política purgaba TODA la empresa (se
    ignoraban `scope`, `target_id`, `workspace_id` y `apply_to`), así que una
    política «canal X, 1 mes» destruía todos los mensajes de más de un mes y,
    con varias, mandaba la más corta. Ahora:

    - cada política alcanza solo su ámbito (canal, equipo, tipo de
      conversación o espacio de trabajo);
    - cada conversación la gobierna su política más específica (un canal con
      60 meses no lo purga la política de 12 del espacio);
    - solo purgan mensajes las políticas `apply_to` all/messages;
    - **el legal hold se respeta**: el de colaboración y el bloqueo legal
      general de la empresa. Ver la nota de cabecera del módulo.

    El borrado es un `UPDATE` masivo acotado por empresa, no un recorrido.
    """
    return run_retention_de_empresa(db, _org(user), getattr(user, "id", None))


def run_retention_de_empresa(db: Session, org: str, actor_id: Optional[str] = None) -> dict:
    """`run_retention` para una empresa sin persona: lo usa el trabajo diario.

    M77 (auditoría 22-11-2026): antes solo se ejecutaba a mano y no tocaba los
    adjuntos. Ahora corre cada día con las demás políticas de retención
    (`app.worker.aplicar_retencion`) y también borra los ADJUNTOS (fichero,
    versiones y texto indexado) de los mensajes que purga, salvo los retenidos.
    """
    politicas: list = [
        p for p in db.query(CollaborationRetentionPolicy)
        .filter(
            CollaborationRetentionPolicy.organization_id == org,
            CollaborationRetentionPolicy.is_active == True,  # noqa: E712
        )
        .all()
        if (getattr(p, "apply_to", None) or "all") in _APLICA_A_MENSAJES
    ]
    ajustes = get_retention_settings(db, org)
    if not politicas:
        politicas = [_PoliticaPorDefecto(ajustes["default_months"])]

    ahora = utcnow()
    retenidos = legal_held_message_ids(db, org)
    bloqueo_general = _condicion_de_bloqueo_general(db, org)
    borrados = 0
    adjuntos = 0
    for meses, conversaciones, excluir in _plan_de_retencion(db, org, politicas):
        corte = ahora - timedelta(days=DIAS_POR_MES * max(1, int(meses or 1)))
        q = db.query(CollaborationMessage).filter(
            CollaborationMessage.organization_id == org,
            CollaborationMessage.sent_at < corte,
            CollaborationMessage.status != "deleted",
            ~bloqueo_general,
        )
        if conversaciones is not None:
            q = q.filter(CollaborationMessage.conversation_id.in_(conversaciones))
        if excluir:
            q = q.filter(~CollaborationMessage.conversation_id.in_(excluir))
        if retenidos:
            q = q.filter(~CollaborationMessage.id.in_(retenidos))
        ids = [i for (i,) in q.with_entities(CollaborationMessage.id).all()]
        if not ids:
            continue
        n = db.query(CollaborationMessage).filter(CollaborationMessage.id.in_(ids)).update(
            {
                CollaborationMessage.status: "deleted",
                CollaborationMessage.deleted_at: ahora,
                CollaborationMessage.body: "[retention purge]",
            },
            synchronize_session=False,
        )
        borrados += int(n or 0)
        adjuntos += _purgar_adjuntos(db, org, ids)

    audit_log.write(
        db, organization_id=org, actor_user_id=actor_id, actor_client_id=None,
        action="retention.run", entity_type="retention", entity_id=None,
        payload={"deleted": borrados, "attachments_deleted": adjuntos, "policies": len(politicas)},
    )
    db.commit()
    return {"deleted": borrados, "attachments_deleted": adjuntos, "policies_applied": len(politicas)}


def _purgar_adjuntos(db: Session, org: str, mensajes: list) -> int:
    """M77: borra los adjuntos (y sus versiones y vista previa) de los mensajes purgados."""
    from app.models.collaboration import CollaborationAttachment, CollaborationAttachmentVersion
    from app.services.collaboration._storage import storage
    filas = db.query(CollaborationAttachment).filter(
        CollaborationAttachment.organization_id == org, CollaborationAttachment.message_id.in_(mensajes)).all()
    for a in filas:
        claves = [a.storage_key, a.preview_key] + [v.storage_key for v in db.query(CollaborationAttachmentVersion)
                                                   .filter(CollaborationAttachmentVersion.attachment_id == a.id)]
        for k in [k for k in claves if k]:
            try:
                storage.delete(k)
            except Exception:
                logging.getLogger(__name__).warning("retención: no se pudo borrar el fichero %s", k, exc_info=True)
        db.query(CollaborationAttachmentVersion).filter(
            CollaborationAttachmentVersion.attachment_id == a.id).delete(synchronize_session=False)
        db.delete(a)
    return len(filas)


# ── Legal hold ──────────────────────────────────────────────────────────────

def list_holds(db: Session, user) -> list[CollaborationLegalHold]:
    return (
        db.query(CollaborationLegalHold)
        .filter(CollaborationLegalHold.organization_id == _org(user))
        .all()
    )


def create_hold(db: Session, user, datos: dict) -> CollaborationLegalHold:
    org = _org(user)
    fila = CollaborationLegalHold(
        organization_id=org,
        case_reference=datos.get("case_reference"),
        description=datos.get("description"),
        custodian_user_ids=datos.get("custodian_user_ids"),
        custodian_client_ids=datos.get("custodian_client_ids"),
        channel_ids=datos.get("channel_ids"),
        created_by=user.id,
    )
    db.add(fila)
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="legal_hold.created", entity_type="legal_hold", entity_id=fila.id,
        payload=datos,
    )
    db.commit()
    return fila


def release_hold(db: Session, user, hold_id: str) -> None:
    org = _org(user)
    fila = (
        db.query(CollaborationLegalHold)
        .filter(
            CollaborationLegalHold.id == hold_id,
            CollaborationLegalHold.organization_id == org,
        )
        .first()
    )
    if not fila:
        raise error(404, "no_encontrado", detail="Hold no encontrado", que="bloqueo_legal")
    fila.is_active = False
    fila.ended_at = utcnow()
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="legal_hold.released", entity_type="legal_hold", entity_id=hold_id,
        payload={},
    )
    db.commit()


def legal_held_message_ids(db: Session, organization_id: str) -> set[str]:
    """Los mensajes protegidos por algún legal hold activo.

    Un mensaje está retenido si **cualquiera** de las tres custodias lo alcanza:

      · lo escribió un usuario custodio;
      · lo escribió un cliente custodio;
      · o pertenece a la conversación de un canal retenido.

    Es una disyunción, y ahí estaba el defecto: la versión anterior sólo aplicaba
    la primera —recogía las otras dos listas y no las usaba—, así que un caso que
    nombraba clientes o canales **no protegía nada** y sus mensajes se borraban en
    el barrido de retención. Ver la nota de cabecera del módulo.

    Y si un caso activo no nombra a nadie, **no retiene nada**. La versión
    anterior, con la lista de usuarios vacía, no añadía filtro y devolvía todos
    los mensajes de la organización: la retención dejaba de borrar por completo.
    """
    casos = (
        db.query(CollaborationLegalHold)
        .filter(
            CollaborationLegalHold.organization_id == organization_id,
            CollaborationLegalHold.is_active == True,  # noqa: E712
        )
        .all()
    )
    if not casos:
        return set()

    usuarios: set[str] = set()
    clientes: set[str] = set()
    canales: set[str] = set()
    for c in casos:
        usuarios.update(c.custodian_user_ids or [])
        clientes.update(c.custodian_client_ids or [])
        canales.update(c.channel_ids or [])

    condiciones = []
    if usuarios:
        condiciones.append(CollaborationMessage.user_id.in_(usuarios))
    if clientes:
        condiciones.append(CollaborationMessage.client_user_id.in_(clientes))
    if canales:
        # Un canal retiene su conversación entera, incluidos los mensajes de
        # quien no es custodio: es el canal lo que está bajo custodia.
        conversaciones = [
            r[0] for r in db.query(CollaborationChannel.conversation_id)
            .filter(CollaborationChannel.id.in_(canales))
            .all()
            if r[0]
        ]
        if conversaciones:
            condiciones.append(
                CollaborationMessage.conversation_id.in_(conversaciones)
            )

    if not condiciones:
        # Casos activos que no nombran a nadie: no retienen nada. Devolver todo
        # —lo que hacía antes— deja la retención sin efecto para siempre.
        return set()

    filas = (
        db.query(CollaborationMessage.id)
        .filter(
            CollaborationMessage.organization_id == organization_id,
            or_(*condiciones),
        )
        .all()
    )
    return {r[0] for r in filas}


# ── eDiscovery ──────────────────────────────────────────────────────────────

def ediscovery_export(
    db: Session, user, *, case_reference: Optional[str],
    user_ids: Optional[list] = None, date_from=None, date_to=None,
    keywords: Optional[list] = None,
) -> dict:
    """Exporta los mensajes que encajan con una petición legal.

    Las palabras clave son **acumulativas** —cada una añade su `ILIKE`, así que
    el mensaje tiene que contenerlas todas— y se aplican como máximo cinco. No
    es un descuido: es lo que hacía y cambiarlo cambiaría el resultado de una
    exportación legal, así que se conserva y se deja escrito.
    """
    org = _org(user)
    q = db.query(CollaborationMessage).filter(
        CollaborationMessage.organization_id == org
    )
    if user_ids:
        q = q.filter(CollaborationMessage.user_id.in_(user_ids))
    if date_from:
        q = q.filter(CollaborationMessage.sent_at >= date_from)
    if date_to:
        q = q.filter(CollaborationMessage.sent_at <= date_to)
    for kw in (keywords or [])[:MAX_PALABRAS_CLAVE]:
        q = q.filter(CollaborationMessage.body.ilike(f"%{kw}%"))

    filas = (
        q.order_by(CollaborationMessage.sent_at.asc())
        .limit(MAX_MENSAJES_EXPORTADOS)
        .all()
    )
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="ediscovery.export", entity_type="export", entity_id=None,
        payload={"case": case_reference, "matched": len(filas)},
    )
    db.commit()
    return {
        "case_reference": case_reference,
        "exported_at": utcnow().isoformat(),
        "total": len(filas),
        "messages": [
            {
                "id": m.id, "conversation_id": m.conversation_id,
                "user_id": m.user_id, "body": m.body, "sent_at": m.sent_at,
                "status": m.status, "type": m.type,
            }
            for m in filas
        ],
    }


# ── Auditoría ───────────────────────────────────────────────────────────────

def list_decisions(db: Session, user, limit: int = 100) -> list[dict]:
    """Las decisiones registradas con `/decision <texto>`, del registro de auditoría."""
    filas = (
        db.query(CollaborationAuditEvent)
        .filter(
            CollaborationAuditEvent.organization_id == _org(user),
            CollaborationAuditEvent.action == "decision.recorded",
        )
        .order_by(CollaborationAuditEvent.created_at.desc())
        .limit(min(limit, MAX_DECISIONES))
        .all()
    )
    return [
        {
            "id": r.id,
            "text": (r.payload or {}).get("text", ""),
            "actor_user_id": r.actor_user_id,
            "conversation_id": r.entity_id,
            "created_at": r.created_at,
        }
        for r in filas
    ]


def list_audit(db: Session, user, limit: int = 200) -> list[CollaborationAuditEvent]:
    return (
        db.query(CollaborationAuditEvent)
        .filter(CollaborationAuditEvent.organization_id == _org(user))
        .order_by(CollaborationAuditEvent.created_at.desc())
        .limit(min(limit, MAX_EVENTOS_DE_AUDITORIA))
        .all()
    )
