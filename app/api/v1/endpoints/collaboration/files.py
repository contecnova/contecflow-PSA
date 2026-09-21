"""Attachment endpoints — upload, AV/DLP, signed download, preview.

Auditoria 2026-08 (hallazgo 22). Los 11 puntos de acceso a base de este fichero
estan en `app/services/collaboration/files.py`, y con ellos se corrigio un valor
configurado que no llegaba: el plazo de las URL firmadas estaba en duro a 3600 s
en cuatro sitios, ignorando `S3_URL_EXPIRATION_HOURS`, que es configurable en
caliente por organizacion.

Auditoria 2026-08 (P1-8): aqui habia ademas un `MAX_FILE_BYTES` propio de 500 MB
muy por encima de `settings.MAX_FILE_SIZE_MB` (100), que este modulo ignoraba, y
se comprobaba DESPUES de `await file.read()` — para rechazar 499 MB habia que
metérselos antes en memoria. El tope y la validacion de contenido salen ahora de
`app/core/uploads.py`, que lee por trozos y aborta al pasarse.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_internal_user
from app.core.responses import APIResponse
from app.core.uploads import UploadProfile, read_and_validate_upload
from app.db.session import get_db
from app.models.user import User
from app.schemas.collaboration import AttachmentOut
from app.services.collaboration import files as svc
from app.services.collaboration._storage import FileStorage

router = APIRouter()

@router.post("/attachments", response_model=AttachmentOut, summary="Subir adjunto (multipart)")
async def upload_attachment(
    conversation_id: str = Form(...),
    message_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    # Lectura acotada + validación de tipo (extensión, MIME declarado, bytes
    # mágicos y coherencia entre ellos). Antes esto no validaba NADA del
    # contenido: bastaba renombrar un ejecutable para subirlo.
    datos = await read_and_validate_upload(file, UploadProfile.ATTACHMENT)
    nombre = svc.nombre_para_clave_de_objeto(file.filename)

    att, en_cuarentena = svc.crear_adjunto(
        db, current_user,
        conversation_id=conversation_id, message_id=message_id,
        nombre_seguro=nombre, mime_type=file.content_type, datos=datos,
    )

    # Si el adjunto no viene asociado a un mensaje existente se crea uno para
    # que aparezca en el chat.
    if not message_id:
        svc.publicar_mensaje_del_adjunto(
            db, current_user, att, conversation_id=conversation_id,
            nombre_de_fichero=file.filename, en_cuarentena=en_cuarentena,
        )

    if not en_cuarentena:
        from app.services.collaboration._queue import task_queue
        from app.services.collaboration._thumbnails import generate_for_attachment

        task_queue.enqueue(generate_for_attachment, att.id)
        svc.indexar_texto(db, att, datos, nombre, file.content_type)

    return AttachmentOut(**svc.salida_de_adjunto(db, att))


@router.post("/attachments/{attachment_id}/versions", response_model=AttachmentOut, summary="Subir nueva versión")
async def upload_new_version(
    attachment_id: str,
    notes: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    # Esta vía no tenía ni el tope de 500 MB que sí tenía la de creación: era un
    # `await file.read()` sin límite.
    datos = await read_and_validate_upload(file, UploadProfile.ATTACHMENT)
    att, _ = svc.subir_version(
        db, current_user, attachment_id, datos=datos, notas=notes)
    return AttachmentOut(**svc.salida_de_adjunto(db, att))


@router.get("/attachments/{attachment_id}", response_model=APIResponse[AttachmentOut], summary="Datos del adjunto")
def get_attachment(attachment_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return APIResponse.ok(
        data=AttachmentOut(**svc.datos_de_adjunto(db, current_user, attachment_id)))


@router.get("/files/by-token/{token}", summary="Descargar archivo por token firmado")
def download_by_token(token: str, db: Session = Depends(get_db)):
    rec = FileStorage.resolve_token(token)
    if not rec:
        raise HTTPException(404, "Token inválido o caducado")
    datos, mime = svc.registrar_descarga_por_token(db, rec["key"])
    return Response(content=datos, media_type=mime or "application/octet-stream")
