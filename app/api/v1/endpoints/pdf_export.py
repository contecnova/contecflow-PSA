"""Exportacion a PDF.

Auditoria 2026-08 (hallazgo 22). Estas rutas vivian en
`app/api/v1/endpoints/mfa.py`, un fichero de 640 lineas con **38 rutas de ocho
dominios** —MFA, organizaciones, Slack, presupuestos, planificacion asistida,
escenarios, PDF y tokens de BI— servidas por un router llamado «mfa».

La mala ubicacion no fue solo desorden: el CRUD de organizaciones estaba
escondido ahi, y por eso nadie noto que a esos endpoints les faltaba la guarda de
superadministrador que su propio `summary` anunciaba. Fue la causa proxima del P0
numero 1 de la auditoria.

**Los paths no han cambiado.** ABAC y GRC derivan el modulo de la ruta, asi que
tocarlos alteraria los permisos en silencio.
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io
from app.db.session import get_db
from app.core.deps import get_current_user, require_internal_user
from app.models.user import User
from app.core.responses import APIListResponse
import app.services.pdf_export_service as _pdf
from app.schemas.auth_payloads import (
    ExportPdfIn,
)

router = APIRouter()


@router.post("/pdf/export", summary="Exportar informe o factura a PDF con logo")
def export_pdf(
    background_tasks: BackgroundTasks,
    payload: ExportPdfIn = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
):
    export_type = payload.export_type or "generic"
    source_id = payload.source_id
    params = {
        "company_name": payload.company_name or "Contecflow",
        "primary_color": payload.primary_color or "#1C2833",
        "logo_b64": payload.logo_b64,
    }

    try:
        pdf_bytes, filename = _pdf.create_and_run_pdf_export(
            export_type, source_id, params, current_user.id, db
        )
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/pdf/jobs", summary="Historial de exportaciones PDF")
def list_pdf_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIListResponse.ok(items=_pdf.list_pdf_jobs(current_user.id, db))
