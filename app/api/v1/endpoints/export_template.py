from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.core.responses import APIResponse
from app.models.user import User

router = APIRouter()

@router.post("/projects/{project_id}/export-template", summary="Export project as template")
def export_project_template(project_id: str, current_user: User = Depends(get_current_user)):
    return APIResponse.ok(data={"ok": True, "template_id": "tpl-123"})
