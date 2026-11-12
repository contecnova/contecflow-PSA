"""Adjuntos de colaboración: alta, versionado, descarga firmada y cuarentena.

Auditoría 2026-08 (hallazgo 22). Estas operaciones vivían en
`endpoints/collaboration/files.py` con **11 puntos de acceso directo a base**.
Al moverlas apareció un valor configurado que no llegaba:

**El tiempo de vida de las URL firmadas estaba en duro a 3600 segundos, en
cuatro sitios**, mientras `S3_URL_EXPIRATION_HOURS` existe en la configuración,
está expuesto en la pantalla de ajustes y se puede cambiar **en caliente por
organización** (`get_runtime_int`). Un administrador que subiera el plazo a
cuatro horas seguía recibiendo enlaces de una hora para los adjuntos del chat.
Es la misma forma que el defecto de SMTP: el valor configurado no llega, el de
por defecto gana en silencio.

El endpoint sigue siendo `async` —hace falta para `await file.read()`— y lee el
fichero antes de llamar aquí: ninguna operación de base corre en el bucle de
eventos.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.collaboration import (
    CollaborationAttachment,
    CollaborationAttachmentVersion,
    CollaborationModerationCase,
)
from app.services.collaboration import audit_log
from app.services.collaboration._permissions import _org, assert_conversation_access
from app.services.collaboration._storage import scan_dlp, scan_with_av, storage
from app.core.errores import ErrorDeDominio

_log = logging.getLogger(__name__)

#: Para pasar de horas —que es la unidad del ajuste— a segundos, que es lo que
#: espera el firmador de URL.
SEGUNDOS_POR_HORA = 3600

#: Cuántos caracteres del fichero se pasan al escáner DLP. Es un tope de
#: memoria, no una decisión de seguridad: un fichero de 100 MB de texto no cabe
#: en un escaneo sincrónico, y los datos sensibles que busca el escáner
#: aparecen en la cabecera de un documento, no en su cola.
CARACTERES_ESCANEADOS_DLP = 200_000

#: Organización que se registra en la auditoría de una descarga por token cuando
#: el adjunto ya no existe. El token es válido —lo firmó el servidor— pero la
#: fila pudo borrarse entre la firma y la descarga, y el evento tiene que
#: quedar registrado igual. Este UUID de ceros significa «sin organización
#: conocida» y no pertenece a ningún tenant real.
ORG_DESCONOCIDA = "00000000-0000-0000-0000-000000000000"


def ttl_de_enlace_firmado(db: Session, organization_id: Optional[str]) -> int:
    """Segundos de vida de una URL firmada, de la configuración.

    Lee el ajuste **en caliente por organización** y cae al de despliegue. Antes
    esto era un `3600` escrito cuatro veces, así que subir el plazo desde la
    pantalla de ajustes no tenía efecto en los adjuntos del chat.
    """
    horas = settings.S3_URL_EXPIRATION_HOURS
    try:
        from app.services.settings_service import get_runtime_int

        horas = get_runtime_int(db, "S3_URL_EXPIRATION_HOURS", organization_id) or horas
    except Exception:
        # Sin ajustes en caliente disponibles se usa el de despliegue: el plazo
        # nunca queda sin valor. Se registra en `debug` y no mas alto porque
        # esto se evalua en cada enlace firmado.
        _log.debug(
            "no se pudo leer S3_URL_EXPIRATION_HOURS en caliente; se usa %s h",
            horas, exc_info=True,
        )
    return int(horas) * SEGUNDOS_POR_HORA


def _enlace(db: Session, key: Optional[str], organization_id: Optional[str]) -> Optional[str]:
    if not key:
        return None
    return storage.signed_url(key, ttl_seconds=ttl_de_enlace_firmado(db, organization_id))


def escanear(datos: bytes) -> tuple[str, list, str, list, bool]:
    """Pasa antivirus y DLP sobre el contenido.

    Devuelve `(estado_av, detalle_av, estado_dlp, hallazgos_dlp, en_cuarentena)`.
    Se pone en cuarentena si **cualquiera** de los dos lo rechaza.
    """
    av_status, av_details = scan_with_av(datos)
    dlp_status, dlp_findings = scan_dlp(
        datos.decode("utf-8", errors="ignore")[:CARACTERES_ESCANEADOS_DLP]
    )
    en_cuarentena = (av_status == "infected") or (dlp_status == "blocked")
    return av_status, av_details, dlp_status, dlp_findings, en_cuarentena


def _atajo_de_cuarentena(db: Session, org: str, att_id: str, *, av_status: str,
                         av_details, dlp_findings) -> None:
    db.add(CollaborationModerationCase(
        organization_id=org, attachment_id=att_id,
        reason="av" if av_status == "infected" else "dlp",
        findings={"av": av_details, "dlp": dlp_findings},
        verdict="quarantined",
    ))


#: Longitud del nombre que se conserva en la clave de objeto. Las claves viajan
#: en URL y en cabeceras: un nombre de 4 KB rompe intermediarios.
MAX_LONGITUD_DE_NOMBRE = 180

#: Caracteres que se conservan en una clave de objeto. Todo lo demás pasa a `_`.
#: Es más estricto que `core.uploads.safe_filename` —que sólo quita separadores
#: de ruta y caracteres de control— porque esto no es un nombre de fichero en
#: disco sino un tramo de clave de almacenamiento, donde un espacio o una `#`
#: sí rompen URL firmadas.
_CARACTERES_NO_VALIDOS_EN_CLAVE = re.compile(r"[^A-Za-z0-9._-]")


def nombre_para_clave_de_objeto(nombre: Optional[str]) -> str:
    """Un nombre seguro para usar como tramo de clave de objeto.

    Se queda con el último segmento —así una ruta con `../` no escapa— y
    sustituye todo lo que no sea alfanumérico, punto, guion o subrayado.

    Auditoría 2026-08: esto estaba escrito dos veces, en el endpoint de
    `/attachments` y en el de TUS, con reglas distintas, y las dos alimentaban
    la MISMA construcción de clave. Una sola definición para las dos vías.
    """
    crudo = (nombre or "upload").replace("\\", "/")
    base = crudo.split("/")[-1].strip().strip(".")
    if not base:
        return "upload"
    return _CARACTERES_NO_VALIDOS_EN_CLAVE.sub("_", base)[:MAX_LONGITUD_DE_NOMBRE] or "upload"


def crear_adjunto(
    db: Session, user, *, conversation_id: str, message_id: Optional[str],
    nombre_seguro: str, mime_type: Optional[str], datos: bytes,
    accion_de_auditoria: str = "attachment.uploaded",
) -> tuple[CollaborationAttachment, bool]:
    """Guarda el fichero y crea el adjunto con su primera versión.

    Devuelve `(adjunto, en_cuarentena)`. El acceso a la conversación se
    comprueba antes de escribir nada.

    `accion_de_auditoria` distingue la vía de subida en el registro —la subida
    reanudable de TUS usa `attachment.uploaded.tus`—. Es lo único que cambia
    entre las dos vías: el resto de la materialización es esta función, y por eso
    está aquí en vez de repetida. Antes había dos copias, y la de TUS no
    validaba el contenido ni respetaba el tope configurado.
    """
    assert_conversation_access(db, user, conversation_id)
    org = _org(user)
    av_status, av_details, dlp_status, dlp_findings, en_cuarentena = escanear(datos)

    # La clave lleva organización y conversación delante para que el
    # almacenamiento quede segmentado por tenant, y marca de tiempo para que dos
    # ficheros con el mismo nombre no se pisen.
    key = f"{org}/{conversation_id}/{utcnow().strftime('%Y%m%d%H%M%S')}_{nombre_seguro}"
    guardado = storage.save_bytes(key, datos)

    att = CollaborationAttachment(
        organization_id=org, conversation_id=conversation_id,
        message_id=message_id, uploaded_by_user_id=user.id,
        name=nombre_seguro, mime_type=mime_type,
        size_bytes=guardado.size_bytes,
        storage_provider=guardado.storage_provider,
        storage_key=guardado.storage_key, sha256=guardado.sha256,
        av_status=av_status, av_scanned_at=utcnow(),
        dlp_status=dlp_status, dlp_findings={"items": dlp_findings},
        is_quarantined=en_cuarentena,
    )
    db.add(att)
    db.flush()
    db.add(CollaborationAttachmentVersion(
        organization_id=org, attachment_id=att.id, version=1,
        storage_key=guardado.storage_key, size_bytes=guardado.size_bytes,
        sha256=guardado.sha256, uploaded_by_user_id=user.id,
    ))
    if en_cuarentena:
        _atajo_de_cuarentena(
            db, org, att.id, av_status=av_status,
            av_details=av_details, dlp_findings=dlp_findings,
        )
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action=accion_de_auditoria, entity_type="attachment", entity_id=att.id,
        payload={"size": guardado.size_bytes, "av": av_status, "dlp": dlp_status},
    )
    db.commit()
    return att, en_cuarentena


def publicar_mensaje_del_adjunto(
    db: Session, user, att: CollaborationAttachment, *, conversation_id: str,
    nombre_de_fichero: Optional[str], en_cuarentena: bool,
) -> None:
    """Crea el mensaje que hace visible el adjunto en el chat.

    Si el fichero está en cuarentena el mensaje es de tipo `system` y avisa, en
    vez de un mensaje de fichero que invitaría a descargarlo: el adjunto existe
    pero no se puede bajar.
    """
    from app.models.collaboration import CollaborationConversation, CollaborationMessage
    from app.services.collaboration._bus import conv_channel
    from app.services.collaboration.messages import _publish_async, _serialize_message

    org = _org(user)
    cuerpo = (
        f"⚠️ Archivo bloqueado: {nombre_de_fichero} "
        f"({'AV' if att.av_status == 'infected' else 'DLP'})"
        if en_cuarentena else nombre_de_fichero
    )
    mensaje = CollaborationMessage(
        organization_id=org, conversation_id=conversation_id, user_id=user.id,
        type="system" if en_cuarentena else "file",
        status="visible", body=cuerpo,
        metadata_json={"attachment_id": att.id, "quarantined": en_cuarentena},
        has_attachments=not en_cuarentena,
        sent_at=utcnow(),
    )
    db.add(mensaje)
    db.flush()
    # El adjunto se enlaza al mensaje ANTES de serializar: si no, el mensaje que
    # se publica en tiempo real sale sin su adjunto.
    att.message_id = mensaje.id

    conv = (
        db.query(CollaborationConversation)
        .filter(CollaborationConversation.id == conversation_id)
        .first()
    )
    if conv:
        conv.last_activity_at = utcnow()
        conv.last_message_id = mensaje.id
    db.commit()

    _publish_async(conv_channel(conversation_id), {
        "type": "message.created",
        "conversation_id": conversation_id,
        "message_id": mensaje.id,
        "payload": _serialize_message(db, mensaje),
    })


def indexar_texto(db: Session, att: CollaborationAttachment, datos: bytes,
                  nombre: str, mime_type: Optional[str]) -> None:
    """Extrae el texto del fichero para el índice de búsqueda, best-effort.

    El `rollback()` del `except` **no es cosmético**: si lo que falla es el
    `commit`, la sesión queda en transacción abortada y quien construya la
    respuesta después lee atributos que el commit anterior expiró
    (`expire_on_commit` está en su valor por defecto), SQLAlchemy intenta
    refrescarlos y lanza `PendingRollbackError`. Una subida **correcta** se
    convertiría en un 500 por un índice de texto que era opcional.
    """
    from app.services.collaboration._text_extract import extract_text

    try:
        texto = extract_text(datos, nombre, mime_type)
        if texto:
            att.text_index = texto
            db.commit()
    except Exception:
        db.rollback()
        _log.debug("indexar_texto: fallo best-effort ignorado", exc_info=True)


def _adjunto_accesible(db: Session, user, attachment_id: str) -> CollaborationAttachment:
    att = (
        db.query(CollaborationAttachment)
        .filter(
            CollaborationAttachment.id == attachment_id,
            CollaborationAttachment.organization_id == _org(user),
        )
        .first()
    )
    if not att:
        raise ErrorDeDominio(404, "Adjunto no encontrado")
    assert_conversation_access(db, user, att.conversation_id)
    return att


def subir_version(
    db: Session, user, attachment_id: str, *, datos: bytes, notas: Optional[str],
) -> tuple[CollaborationAttachment, bool]:
    """Añade una versión nueva y la deja como cabeza del adjunto."""
    org = _org(user)
    att = _adjunto_accesible(db, user, attachment_id)
    av_status, av_details, dlp_status, dlp_findings, en_cuarentena = escanear(datos)

    siguiente = (
        db.query(CollaborationAttachmentVersion)
        .filter(CollaborationAttachmentVersion.attachment_id == attachment_id)
        .count() or 0
    ) + 1
    guardado = storage.save_bytes(f"{att.storage_key}.v{siguiente}", datos)
    db.add(CollaborationAttachmentVersion(
        organization_id=org, attachment_id=attachment_id, version=siguiente,
        storage_key=guardado.storage_key, size_bytes=guardado.size_bytes,
        sha256=guardado.sha256, uploaded_by_user_id=user.id, notes=notas,
    ))
    # La cabeza pasa a apuntar a la versión nueva.
    att.storage_key = guardado.storage_key
    att.size_bytes = guardado.size_bytes
    att.sha256 = guardado.sha256
    att.av_status = av_status
    att.av_scanned_at = utcnow()
    att.dlp_status = dlp_status
    att.dlp_findings = {"items": dlp_findings}
    att.is_quarantined = en_cuarentena
    if en_cuarentena:
        _atajo_de_cuarentena(
            db, org, att.id, av_status=av_status,
            av_details=av_details, dlp_findings=dlp_findings,
        )
    audit_log.write(
        db, organization_id=org, actor_user_id=user.id, actor_client_id=None,
        action="attachment.versioned", entity_type="attachment", entity_id=att.id,
        payload={"version": siguiente},
    )
    db.commit()
    return att, en_cuarentena


def datos_de_adjunto(db: Session, user, attachment_id: str) -> dict:
    """El adjunto con sus enlaces firmados, si no está en cuarentena."""
    att = _adjunto_accesible(db, user, attachment_id)
    return salida_de_adjunto(db, att, con_vista_previa=True)


def salida_de_adjunto(db: Session, att: CollaborationAttachment, *,
                      con_vista_previa: bool = False) -> dict:
    """Los campos de `AttachmentOut`.

    **Un adjunto en cuarentena no lleva enlace de descarga.** Es la regla que
    hace que la cuarentena signifique algo: el fichero existe, se ve en el chat
    y no se puede bajar.
    """
    vista_previa = None
    if con_vista_previa and att.preview_status == "ready":
        vista_previa = _enlace(db, att.preview_key, att.organization_id)
    return {
        "id": att.id, "name": att.name, "mime_type": att.mime_type,
        "size_bytes": att.size_bytes, "storage_provider": att.storage_provider,
        "av_status": att.av_status, "dlp_status": att.dlp_status,
        "is_quarantined": att.is_quarantined,
        "download_url": (
            None if att.is_quarantined
            else _enlace(db, att.storage_key, att.organization_id)
        ),
        "preview_url": vista_previa,
        "created_at": att.created_at,
    }


def registrar_descarga_por_token(db: Session, key: str) -> tuple[bytes, Optional[str]]:
    """Lee el fichero de un token ya validado y deja el evento en auditoría.

    Devuelve `(contenido, mime)`. Si el adjunto ya no existe se registra igual
    con `ORG_DESCONOCIDA`: el token lo firmó el servidor y la descarga ocurrió,
    así que tiene que quedar constancia aunque la fila se haya borrado.
    """
    datos = storage.read(key)
    att = (
        db.query(CollaborationAttachment)
        .filter(CollaborationAttachment.storage_key == key)
        .first()
    )
    audit_log.write(
        db,
        organization_id=att.organization_id if att else ORG_DESCONOCIDA,
        actor_user_id=None, actor_client_id=None,
        action="attachment.downloaded", entity_type="attachment",
        entity_id=att.id if att else None,
        payload={"key": key},
    )
    db.commit()
    return datos, (att.mime_type if att else None)
