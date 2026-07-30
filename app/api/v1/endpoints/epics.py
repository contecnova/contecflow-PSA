"""Contecflow v19 — Wiki, Épicas, NQL, CFD, Menciones"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.schemas.epics import (
    WikiSpaceIn, WikiPageIn, WikiTemplateIn, WikiCommentIn, EpicIn, NQLIn, SavedFilterIn, ThreadedCommentIn
)

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_pm
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIResponse, APIListResponse
from app.models.user import User
from app.services.epics_service import (
    list_wiki_spaces, create_wiki_space, update_wiki_space, delete_wiki_space,
    list_wiki_pages, create_wiki_page, get_wiki_page, update_wiki_page,
    delete_wiki_page, list_page_versions, restore_wiki_version, search_wiki_pages,
    list_wiki_templates, create_wiki_template,
    list_wiki_page_comments, add_wiki_page_comment, resolve_wiki_page_comment,
    list_epics_records, create_epic_record, get_epic_record, update_epic_record,
    delete_epic_record, add_task_to_epic_record, remove_task_from_epic_record,
    add_epic_dependency, remove_epic_dependency, get_roadmap_data,
    execute_nql_search, list_saved_filters, create_saved_filter, delete_saved_filter,
    take_cfd_snapshot, get_cfd_data,
    get_my_mentions, mark_all_mentions_read,
    list_threaded_comments, add_threaded_comment, edit_threaded_comment,
    resolve_threaded_comment, delete_threaded_comment,
)

router = APIRouter()


# ══════════════════════════════════════════════════════════════════════
# 1. WIKI — ESPACIOS
# ══════════════════════════════════════════════════════════════════════



@router.get("/wiki/spaces", summary="Listar espacios de wiki")
def list_spaces(project_id: Optional[str] = None,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIListResponse.ok(items=list_wiki_spaces(project_id, db))


@router.post("/wiki/spaces", summary="Crear espacio de wiki")
def create_space(p: WikiSpaceIn, db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=create_wiki_space(p.model_dump(), cu.id, db))


@router.patch("/wiki/spaces/{space_id}", summary="Actualizar espacio de wiki")
def update_space(space_id: str, p: WikiSpaceIn,
                 db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=update_wiki_space(space_id, p.model_dump(exclude_unset=True), db))


@router.delete("/wiki/spaces/{space_id}", summary="Eliminar espacio de wiki")
def delete_space(space_id: str, db: Session = Depends(get_db),
                 cu: User = Depends(require_admin_or_pm)):
    enforce_abac(db, cu, "wiki_space", space_id, action="delete")
    return APIResponse.ok(data=delete_wiki_space(space_id, db))


# ══════════════════════════════════════════════════════════════════════
# 2. WIKI — PÁGINAS
# ══════════════════════════════════════════════════════════════════════



@router.get("/wiki/spaces/{space_id}/pages", summary="Listar páginas del espacio de wiki")
def list_pages(space_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIListResponse.ok(items=list_wiki_pages(space_id, db))


@router.post("/wiki/spaces/{space_id}/pages", summary="Crear página de wiki")
def create_page(space_id: str, p: WikiPageIn,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=create_wiki_page(space_id, p.title, p.slug, p.content,
                                                p.parent_id, p.is_published, p.sort_order, cu.id, db))


@router.get("/wiki/pages/{page_id}", summary="Obtener página de wiki")
def get_page(page_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=get_wiki_page(page_id, db))


@router.patch("/wiki/pages/{page_id}", summary="Actualizar página de wiki")
def update_page(page_id: str, p: WikiPageIn,
                db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=update_wiki_page(page_id, p.title, p.slug, p.content,
                                                p.parent_id, p.sort_order, p.is_published, p.change_note, cu.id, db))


@router.delete("/wiki/pages/{page_id}", summary="Eliminar página de wiki")
def delete_page(page_id: str, db: Session = Depends(get_db),
                cu: User = Depends(require_admin_or_pm)):
    enforce_abac(db, cu, "wiki_page", page_id, action="delete")
    return APIResponse.ok(data=delete_wiki_page(page_id, db))


@router.get("/wiki/pages/{page_id}/versions", summary="Listar versiones de la página")
def page_versions(page_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIListResponse.ok(items=list_page_versions(page_id, db))


@router.post("/wiki/pages/{page_id}/restore/{version_num}", summary="Restaurar versión de página")
def restore_version(page_id: str, version_num: int,
                    db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=restore_wiki_version(page_id, version_num, cu.id, db))


@router.get("/wiki/search", summary="Buscar páginas en la wiki")
def search_wiki(q: str, space_id: Optional[str] = None,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIListResponse.ok(items=search_wiki_pages(q, space_id, db))


# ── Wiki templates ─────────────────────────────────────────────────────────────

@router.get("/wiki/templates", summary="Listar plantillas de wiki")
def list_templates(db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIListResponse.ok(items=list_wiki_templates(db))




@router.post("/wiki/templates", summary="Crear plantilla de wiki")
def create_template(p: WikiTemplateIn, db: Session = Depends(get_db),
                    cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=create_wiki_template(p.name, p.description, p.icon, p.content, cu.id, db))


# ── Wiki comments ──────────────────────────────────────────────────────────────



@router.get("/wiki/pages/{page_id}/comments")
def page_comments(page_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIListResponse.ok(items=list_wiki_page_comments(page_id, db))


@router.post("/wiki/pages/{page_id}/comments")
def add_wiki_comment(page_id: str, p: WikiCommentIn,
                     db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=add_wiki_page_comment(page_id, p.content, p.parent_id, cu.id, db))


@router.patch("/wiki/comments/{comment_id}/resolve")
def resolve_wiki_comment(comment_id: str, db: Session = Depends(get_db),
                         cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=resolve_wiki_page_comment(comment_id, db))


# ══════════════════════════════════════════════════════════════════════
# 3. ÉPICAS Y ROADMAP
# ══════════════════════════════════════════════════════════════════════



@router.get("")
def list_epics(project_id: str = Query(...),
               db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIListResponse.ok(items=list_epics_records(project_id, db))


@router.post("")
def create_epic(p: EpicIn, project_id: str = Query(...),
                db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=create_epic_record(p.model_dump(), project_id, cu.id, db))


# ── static sub-paths must be declared BEFORE /{epic_id} to avoid shadowing ──

@router.get("/roadmap")
def get_roadmap(project_id: str = Query(...),
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=get_roadmap_data(project_id, db))


@router.post("/nql/search")
def nql_search(p: NQLIn, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=execute_nql_search(p.entity_type, p.query, p.limit, db))


@router.get("/filters")
def list_filters(entity_type: Optional[str] = None,
                 db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIListResponse.ok(items=list_saved_filters(entity_type, cu.id, db))


@router.post("/filters")
def save_filter(p: SavedFilterIn, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=create_saved_filter(p.model_dump(), cu.id, db))


@router.delete("/filters/{filter_id}")
def delete_filter(filter_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    enforce_abac(db, cu, "saved_filter", filter_id, action="delete")
    return APIResponse.ok(data=delete_saved_filter(filter_id, cu.id, db))


@router.post("/cfd/snapshot")
def take_snapshot(project_id: str = Query(...), sprint_id: Optional[str] = Query(None),
                  db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=take_cfd_snapshot(project_id, sprint_id, db))


@router.get("/cfd")
def get_cfd(project_id: str = Query(...), sprint_id: Optional[str] = Query(None), days: int = Query(30),
            db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=get_cfd_data(project_id, sprint_id, days, db))


# ══════════════════════════════════════════════════════════════════════
# 4–6. MENCIONES, COMMENTS, THREADS
# ══════════════════════════════════════════════════════════════════════

@router.get("/mentions")
def my_mentions(only_unread: bool = True,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIListResponse.ok(items=get_my_mentions(cu.id, only_unread, db))


@router.post("/mentions/read-all")
def mark_all_read(db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=mark_all_mentions_read(cu.id, db))


# ══════════════════════════════════════════════════════════════════════
# 7. COMENTARIOS THREADED
# ══════════════════════════════════════════════════════════════════════



@router.get("/comments")
def get_comments(entity_type: str, entity_id: str,
                 db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIListResponse.ok(items=list_threaded_comments(entity_type, entity_id, db))


@router.post("/comments")
def add_comment(entity_type: str, entity_id: str, p: ThreadedCommentIn,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=add_threaded_comment(entity_type, entity_id, p.content, p.parent_id, cu.id, db))


@router.patch("/comments/{comment_id}")
def edit_comment(comment_id: str, p: ThreadedCommentIn,
                 db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=edit_threaded_comment(comment_id, p.content, cu.id, db))


@router.patch("/comments/{comment_id}/resolve")
def resolve_comment(comment_id: str, db: Session = Depends(get_db),
                    cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=resolve_threaded_comment(comment_id, db))


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: str, db: Session = Depends(get_db),
                   cu: User = Depends(get_current_user)):
    enforce_abac(db, cu, "threaded_comment", comment_id, action="delete")
    return APIResponse.ok(data=delete_threaded_comment(comment_id, cu.id, db))


# ── dynamic /{epic_id} routes ────────────────────────────────────────────────

@router.get("/{epic_id}")
def get_epic(epic_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=get_epic_record(epic_id, db))


@router.patch("/{epic_id}")
def update_epic(epic_id: str, p: EpicIn,
                db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=update_epic_record(epic_id, p.model_dump(exclude_unset=True), db))


@router.delete("/{epic_id}")
def delete_epic(epic_id: str, db: Session = Depends(get_db),
                cu: User = Depends(require_admin_or_pm)):
    enforce_abac(db, cu, "epic", epic_id, action="delete")
    return APIResponse.ok(data=delete_epic_record(epic_id, db))


@router.post("/{epic_id}/tasks/{task_id}")
def add_task_to_epic(epic_id: str, task_id: str,
                     db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return APIResponse.ok(data=add_task_to_epic_record(epic_id, task_id, db))


@router.delete("/{epic_id}/tasks/{task_id}")
def remove_task_from_epic(epic_id: str, task_id: str,
                          db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    enforce_abac(db, cu, "epic", epic_id, action="delete")
    return APIResponse.ok(data=remove_task_from_epic_record(epic_id, task_id, db))


@router.post("/{epic_id}/dependencies/{depends_on_id}")
def add_dependency(epic_id: str, depends_on_id: str,
                   db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return APIResponse.ok(data=add_epic_dependency(epic_id, depends_on_id, db))


@router.delete("/{epic_id}/dependencies/{depends_on_id}")
def remove_dependency(epic_id: str, depends_on_id: str,
                      db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    enforce_abac(db, cu, "epic", epic_id, action="delete")
    return APIResponse.ok(data=remove_epic_dependency(epic_id, depends_on_id, db))
