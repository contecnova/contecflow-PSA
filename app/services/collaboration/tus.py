"""Subidas reanudables TUS 1.0.0: sesión, trozos y materialización.

Spec: https://tus.io/protocols/resumable-upload

Auditoría 2026-08 (hallazgo 22). Esto vivía en `endpoints/collaboration/tus.py`,
y al bajarlo aquí quedó a la vista que **TUS era una puerta trasera a la
validación de subidas**:

* El tope estaba en duro a 500 MB, cinco veces `settings.MAX_FILE_SIZE_MB`, que
  es el valor que sí respeta la vía de `/attachments`.
* **No validaba el contenido en absoluto**: ni extensión, ni MIME declarado, ni
  bytes mágicos, ni la coherencia entre ellos. El endurecimiento que se aplicó a
  `/attachments` —donde basta renombrar un ejecutable para que se rechace— se
  saltaba entero subiendo por aquí. Mismo almacén, misma tabla, dos puertas y
  sólo una cerrada.
* Repetía la materialización del adjunto —fila, versión, cuarentena,
  auditoría— en lugar de usar `files.crear_adjunto`, así que cualquier arreglo
  en una vía no llegaba a la otra. Ahora es una sola función.
* El directorio temporal ignoraba `settings.UPLOAD_DIR` y se creaba al importar
  el módulo, un efecto de sistema de ficheros en tiempo de importación.
* Toda la parte de escaneo, almacenamiento y base corría **en el bucle de
  eventos** dentro de la corrutina del `PATCH`. Sólo la E/S de fichero se había
  movido a un hilo; el resto —AV, DLP, subida al almacén y los `commit`—
  seguía bloqueando el proceso entero.

Nota de comportamiento que se conserva: una subida TUS crea el adjunto pero no
publica mensaje en la conversación, al contrario que `/attachments`. No hay
cliente que use TUS todavía, así que no se cambia el contrato sin decidirlo.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutil import utcnow
from app.core.uploads import UploadProfile, max_bytes_for, validate_upload
from app.services.collaboration._permissions import _org, assert_conversation_access

_log = logging.getLogger(__name__)

#: Versión del protocolo y extensiones implementadas, tal como se anuncian en
#: las cabeceras `Tus-*`.
TUS_VERSION = "1.0.0"
TUS_EXTENSIONS = "creation,termination"

#: Perfil de validación. Es el mismo que usa `/attachments`, y ése es el punto:
#: las dos vías de subida tienen que aplicar exactamente el mismo catálogo.
PERFIL = UploadProfile.ATTACHMENT

#: Tipo de contenido que exige la especificación en el `PATCH`.
CONTENT_TYPE_DE_TROZO = "application/offset+octet-stream"


def tope_de_subida() -> int:
    """El tamaño máximo, en bytes, que se anuncia y se exige.

    Sale de `max_bytes_for`, que a su vez sale de `settings.MAX_FILE_SIZE_MB`:
    quien despliega ajusta un solo valor y las dos vías de subida lo respetan.
    """
    return max_bytes_for(PERFIL)


def _directorio() -> str:
    """El directorio de trabajo de TUS, creado si hace falta.

    Se resuelve y se crea al usarlo, no al importar el módulo: importar no debe
    tocar el sistema de ficheros.
    """
    ruta = os.path.join(settings.UPLOAD_DIR, "collaboration", ".tus")
    os.makedirs(ruta, exist_ok=True)
    return ruta


def _validar_uid(uid: str) -> str:
    """Comprueba que el identificador es un UUID antes de construir rutas.

    El `uid` llega en la URL y se concatena a un directorio. Aprovecharlo para
    salir del directorio exigía además acertar con un fichero JSON válido a
    nombre del propio usuario, pero construir rutas con texto de la petición no
    se sostiene: aquí se corta la clase entera de problema.
    """
    try:
        uuid.UUID(uid)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(404, "Upload no encontrado") from None
    return uid


def _ruta_meta(uid: str) -> str:
    return os.path.join(_directorio(), f"{uid}.meta")


def _ruta_datos(uid: str) -> str:
    return os.path.join(_directorio(), f"{uid}.bin")


def _leer_meta(uid: str) -> Optional[dict]:
    ruta = _ruta_meta(uid)
    if not os.path.exists(ruta):
        return None
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        _log.exception("Error leyendo metadata TUS del upload %s", uid)
        return None


def _escribir_meta(uid: str, datos: dict) -> None:
    with open(_ruta_meta(uid), "w", encoding="utf-8") as f:
        json.dump(datos, f)


def _borrar_temporales(uid: str) -> None:
    for ruta in (_ruta_datos(uid), _ruta_meta(uid)):
        try:
            os.remove(ruta)
        except FileNotFoundError:
            pass
        except OSError:
            _log.exception("Error eliminando el temporal TUS %s", ruta)


def parsear_metadata(cabecera: str) -> dict:
    """Descodifica la cabecera `Upload-Metadata` (pares `clave valor-en-base64`)."""
    salida: dict[str, str] = {}
    for parte in (cabecera or "").split(","):
        parte = parte.strip()
        if not parte:
            continue
        if " " in parte:
            clave, valor = parte.split(" ", 1)
            try:
                salida[clave] = base64.b64decode(valor).decode("utf-8")
            except Exception:
                salida[clave] = ""
        else:
            salida[parte] = ""
    return salida


def _nombre(propuesto: Optional[str]) -> str:
    """El mismo saneado que usa `/attachments`, no una copia con otras reglas."""
    from app.services.collaboration.files import nombre_para_clave_de_objeto

    return nombre_para_clave_de_objeto(propuesto)


# ── Ciclo de vida de la subida ──────────────────────────────────────────────

def crear_sesion(db: Session, user, *, upload_length: int, upload_metadata: str) -> str:
    """Abre una sesión de subida y devuelve su identificador.

    El tamaño se comprueba aquí, contra el valor declarado en `Upload-Length`,
    antes de aceptar un solo byte.
    """
    tope = tope_de_subida()
    if upload_length <= 0 or upload_length > tope:
        raise HTTPException(
            413, f"Tamaño no permitido: el máximo es {tope // (1024 * 1024)} MB")

    meta = parsear_metadata(upload_metadata)
    conversation_id = meta.get("conversationId") or meta.get("conversation_id")
    if not conversation_id:
        raise HTTPException(400, "Upload-Metadata debe incluir 'conversationId'")
    assert_conversation_access(db, user, conversation_id)

    uid = str(uuid.uuid4())
    _escribir_meta(uid, {
        "user_id": user.id,
        "organization_id": _org(user),
        "conversation_id": conversation_id,
        "name": _nombre(meta.get("filename") or meta.get("name")),
        "mime_type": meta.get("filetype") or meta.get("mime_type") or None,
        "size": upload_length,
        "offset": 0,
        "created_at": utcnow().isoformat(),
    })
    # Crea el fichero de datos vacío para que el primer `PATCH` en modo append
    # no dependa de su existencia.
    open(_ruta_datos(uid), "wb").close()
    return uid


def meta_propia(uid: str, user) -> dict:
    """La metadata de esa subida, si es de este usuario.

    Una subida ajena y una inexistente dan **el mismo 404**: distinguirlas
    convertiría el endpoint en un oráculo de identificadores válidos.
    """
    _validar_uid(uid)
    meta = _leer_meta(uid)
    if not meta or meta.get("user_id") != user.id:
        raise HTTPException(404, "Upload no encontrado")
    return meta


def escribir_trozo(uid: str, user, *, upload_offset: int, cuerpo: bytes) -> dict:
    """Añade un trozo al final del fichero y devuelve la metadata actualizada."""
    meta = meta_propia(uid, user)
    if upload_offset != meta["offset"]:
        raise HTTPException(409, "Offset no coincide")
    if meta["offset"] + len(cuerpo) > meta["size"]:
        raise HTTPException(413, "Excede tamaño declarado")

    with open(_ruta_datos(uid), "ab") as f:
        f.write(cuerpo)
    meta["offset"] += len(cuerpo)
    _escribir_meta(uid, meta)
    return meta


def materializar(db: Session, user, uid: str, meta: dict) -> Optional[str]:
    """Convierte la subida completa en un adjunto. Devuelve su id.

    Valida el contenido con el mismo perfil que `/attachments` —extensión, MIME
    declarado, bytes mágicos y coherencia entre ellos— y sólo entonces delega en
    `files.crear_adjunto`, que es la única vía de materialización. Si la
    validación rechaza el fichero se limpian los temporales y no queda nada: no
    tiene sentido conservar en disco algo que no se va a poder crear.
    """
    from app.services.collaboration.files import crear_adjunto

    with open(_ruta_datos(uid), "rb") as f:
        datos = f.read()

    nombre = _nombre(meta.get("name"))
    try:
        validate_upload(nombre, meta.get("mime_type") or "", datos, PERFIL)
    except HTTPException:
        _borrar_temporales(uid)
        raise

    try:
        att, en_cuarentena = crear_adjunto(
            db, user,
            conversation_id=meta["conversation_id"],
            message_id=None,
            nombre_seguro=nombre,
            mime_type=meta.get("mime_type"),
            datos=datos,
            accion_de_auditoria="attachment.uploaded.tus",
        )
    except Exception:
        # Los temporales se quedan a propósito: la subida está completa en disco
        # y un fallo transitorio de base o de almacén no debe obligar al cliente
        # a volver a subirlo todo.
        _log.exception("No se pudo materializar la subida TUS %s", uid)
        raise

    if not en_cuarentena:
        from app.services.collaboration._queue import task_queue
        from app.services.collaboration._thumbnails import generate_for_attachment
        task_queue.enqueue(generate_for_attachment, att.id)

    _borrar_temporales(uid)
    return att.id


def abortar(uid: str, user) -> None:
    """Descarta una subida en curso. Idempotente y silenciosa.

    La especificación pide 204 tanto si había algo que borrar como si no, así
    que una subida ajena o inexistente no se distingue de una borrada.
    """
    try:
        _validar_uid(uid)
    except HTTPException:
        return
    meta = _leer_meta(uid)
    if meta and meta.get("user_id") == user.id:
        _borrar_temporales(uid)
