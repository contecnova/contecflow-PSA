"""TUS 1.0.0 resumable uploads para adjuntos del chat.

Spec: https://tus.io/protocols/resumable-upload

  POST    /collaboration/tus           — crear upload (Upload-Length, Upload-Metadata)
  PATCH   /collaboration/tus/{id}      — subir chunk (Upload-Offset, Content-Type: application/offset+octet-stream)
  HEAD    /collaboration/tus/{id}      — estado actual (Upload-Offset, Upload-Length)
  DELETE  /collaboration/tus/{id}      — abortar
  OPTIONS /collaboration/tus           — capabilities

Auditoria 2026-08 (hallazgo 22). La logica esta en
`app/services/collaboration/tus.py`, y al bajarla quedo a la vista que esta via
se saltaba entera la validacion de subidas de `/attachments`: tope en duro de
500 MB y CERO validacion de contenido. Ver el modulo de servicio.

Cuando Upload-Offset alcanza Upload-Length, el fichero se materializa como
adjunto por la misma funcion que usa `/attachments` (`files.crear_adjunto`), que
dispara AV/DLP/thumbnail. Toda esa parte va al pool de hilos: es sincrona y no
puede correr en el bucle de eventos.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.abac_enforce import enforce_abac
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.collaboration import tus as svc

router = APIRouter()


def _cabeceras(**extra: str) -> dict:
    """Cabeceras de respuesta con `Tus-Resumable`, que va en todas."""
    return {"Tus-Resumable": svc.TUS_VERSION, **extra}


@router.options("/tus")
def tus_options() -> Response:
    return Response(
        status_code=204,
        headers=_cabeceras(
            **{
                "Tus-Version": svc.TUS_VERSION,
                "Tus-Extension": svc.TUS_EXTENSIONS,
                # Se anuncia el tope real y configurado, no un 500 MB fijo que
                # el servidor iba a rechazar de todas formas.
                "Tus-Max-Size": str(svc.tope_de_subida()),
            }
        ),
    )


@router.post("/tus")
async def tus_create(
    request: Request,
    upload_length: int = Header(..., alias="Upload-Length"),
    upload_metadata: str = Header("", alias="Upload-Metadata"),
    tus_resumable: str = Header(svc.TUS_VERSION, alias="Tus-Resumable"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = await run_in_threadpool(
        svc.crear_sesion, db, current_user,
        upload_length=upload_length, upload_metadata=upload_metadata,
    )
    base = str(request.base_url).rstrip("/")
    return Response(
        status_code=201,
        headers=_cabeceras(Location=f"{base}/api/v1/collaboration/tus/{uid}"),
    )


@router.head("/tus/{uid}")
async def tus_head(uid: str, current_user: User = Depends(get_current_user)) -> Response:
    meta = await run_in_threadpool(svc.meta_propia, uid, current_user)
    return Response(
        status_code=200,
        headers=_cabeceras(**{
            "Upload-Offset": str(meta["offset"]),
            "Upload-Length": str(meta["size"]),
            "Cache-Control": "no-store",
        }),
    )


@router.patch("/tus/{uid}")
async def tus_patch(
    uid: str,
    request: Request,
    upload_offset: int = Header(..., alias="Upload-Offset"),
    content_type: str = Header(..., alias="Content-Type"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Añade un trozo y, si completa la subida, materializa el adjunto.

    El cuerpo es `async` porque hace falta para `await request.body()`; todo lo
    demás —escritura en disco, escaneo AV/DLP, almacenamiento y base— va al pool
    de hilos.
    """
    if content_type != svc.CONTENT_TYPE_DE_TROZO:
        raise HTTPException(415, "Content-Type inválido")

    cuerpo = await request.body()
    meta = await run_in_threadpool(
        svc.escribir_trozo, uid, current_user,
        upload_offset=upload_offset, cuerpo=cuerpo,
    )

    if meta["offset"] == meta["size"]:
        await run_in_threadpool(svc.materializar, db, current_user, uid, meta)

    return Response(
        status_code=204,
        headers=_cabeceras(**{"Upload-Offset": str(meta["offset"])}),
    )


@router.delete("/tus/{uid}")
async def tus_delete(
    uid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    enforce_abac(db, current_user, "collaboration_file", uid, action="delete")
    await run_in_threadpool(svc.abortar, uid, current_user)
    return Response(status_code=204, headers=_cabeceras())
