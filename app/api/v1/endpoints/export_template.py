from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.core.responses import APIResponse
from app.models.user import User
from app.core.deps import require_admin_or_pm

router = APIRouter()

@router.post("/projects/{project_id}/export-template", summary="Export project as template")
def export_project_template(project_id: str, current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin_or_pm),  # auditoria 2026-09: dominio: estructura de proyecto
):
    return APIResponse.ok(data={"ok": True, "template_id": "tpl-123"})
