"""Clarive v19 — Wiki, Épicas, NQL, CFD, Menciones"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from app.schemas.epics import (
    WikiSpaceIn, WikiPageIn, WikiTemplateIn, WikiCommentIn, EpicIn, NQLIn, SavedFilterIn, ThreadedCommentIn
)

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_pm
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



@router.get("/wiki/spaces")
def list_spaces(project_id: Optional[str] = None,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return list_wiki_spaces(project_id, db)


@router.post("/wiki/spaces")
def create_space(p: WikiSpaceIn, db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return create_wiki_space(p.model_dump(), cu.id, db)


@router.patch("/wiki/spaces/{space_id}")
def update_space(space_id: str, p: WikiSpaceIn,
                 db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return update_wiki_space(space_id, p.model_dump(exclude_unset=True), db)


@router.delete("/wiki/spaces/{space_id}")
def delete_space(space_id: str, db: Session = Depends(get_db),
                 cu: User = Depends(require_admin_or_pm)):
    return delete_wiki_space(space_id, db)


# ══════════════════════════════════════════════════════════════════════
# 2. WIKI — PÁGINAS
# ══════════════════════════════════════════════════════════════════════



@router.get("/wiki/spaces/{space_id}/pages")
def list_pages(space_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return list_wiki_pages(space_id, db)


@router.post("/wiki/spaces/{space_id}/pages")
def create_page(space_id: str, p: WikiPageIn,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return create_wiki_page(space_id, p.title, p.slug, p.content,
                            p.parent_id, p.is_published, p.sort_order, cu.id, db)


@router.get("/wiki/pages/{page_id}")
def get_page(page_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return get_wiki_page(page_id, db)


@router.patch("/wiki/pages/{page_id}")
def update_page(page_id: str, p: WikiPageIn,
                db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return update_wiki_page(page_id, p.title, p.slug, p.content,
                            p.parent_id, p.sort_order, p.is_published, p.change_note, cu.id, db)


@router.delete("/wiki/pages/{page_id}")
def delete_page(page_id: str, db: Session = Depends(get_db),
                cu: User = Depends(require_admin_or_pm)):
    return delete_wiki_page(page_id, db)


@router.get("/wiki/pages/{page_id}/versions")
def page_versions(page_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return list_page_versions(page_id, db)


@router.post("/wiki/pages/{page_id}/restore/{version_num}")
def restore_version(page_id: str, version_num: int,
                    db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return restore_wiki_version(page_id, version_num, cu.id, db)


@router.get("/wiki/search")
def search_wiki(q: str, space_id: Optional[str] = None,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return search_wiki_pages(q, space_id, db)


# ── Wiki templates ─────────────────────────────────────────────────────────────

@router.get("/wiki/templates")
def list_templates(db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return list_wiki_templates(db)




@router.post("/wiki/templates")
def create_template(p: WikiTemplateIn, db: Session = Depends(get_db),
                    cu: User = Depends(require_admin_or_pm)):
    return create_wiki_template(p.name, p.description, p.icon, p.content, cu.id, db)


# ── Wiki comments ──────────────────────────────────────────────────────────────



@router.get("/wiki/pages/{page_id}/comments")
def page_comments(page_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return list_wiki_page_comments(page_id, db)


@router.post("/wiki/pages/{page_id}/comments")
def add_wiki_comment(page_id: str, p: WikiCommentIn,
                     db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return add_wiki_page_comment(page_id, p.content, p.parent_id, cu.id, db)


@router.patch("/wiki/comments/{comment_id}/resolve")
def resolve_wiki_comment(comment_id: str, db: Session = Depends(get_db),
                         cu: User = Depends(get_current_user)):
    return resolve_wiki_page_comment(comment_id, db)


# ══════════════════════════════════════════════════════════════════════
# 3. ÉPICAS Y ROADMAP
# ══════════════════════════════════════════════════════════════════════



@router.get("/epics")
def list_epics(project_id: str,
               db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return list_epics_records(project_id, db)


@router.post("/epics")
def create_epic(p: EpicIn, project_id: str,
                db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return create_epic_record(p.model_dump(), project_id, cu.id, db)


@router.get("/epics/{epic_id}")
def get_epic(epic_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return get_epic_record(epic_id, db)


@router.patch("/epics/{epic_id}")
def update_epic(epic_id: str, p: EpicIn,
                db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return update_epic_record(epic_id, p.model_dump(exclude_unset=True), db)


@router.delete("/epics/{epic_id}")
def delete_epic(epic_id: str, db: Session = Depends(get_db),
                cu: User = Depends(require_admin_or_pm)):
    return delete_epic_record(epic_id, db)


@router.post("/epics/{epic_id}/tasks/{task_id}")
def add_task_to_epic(epic_id: str, task_id: str,
                     db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return add_task_to_epic_record(epic_id, task_id, db)


@router.delete("/epics/{epic_id}/tasks/{task_id}")
def remove_task_from_epic(epic_id: str, task_id: str,
                          db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return remove_task_from_epic_record(epic_id, task_id, db)


@router.post("/epics/{epic_id}/dependencies/{depends_on_id}")
def add_dependency(epic_id: str, depends_on_id: str,
                   db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return add_epic_dependency(epic_id, depends_on_id, db)


@router.delete("/epics/{epic_id}/dependencies/{depends_on_id}")
def remove_dependency(epic_id: str, depends_on_id: str,
                      db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return remove_epic_dependency(epic_id, depends_on_id, db)


@router.get("/roadmap")
def get_roadmap(project_id: str,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return get_roadmap_data(project_id, db)


# ══════════════════════════════════════════════════════════════════════
# 4. NQL — BÚSQUEDA AVANZADA
# ══════════════════════════════════════════════════════════════════════



@router.post("/nql/search")
def nql_search(p: NQLIn, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return execute_nql_search(p.entity_type, p.query, p.limit, db)


@router.get("/filters")
def list_filters(entity_type: Optional[str] = None,
                 db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return list_saved_filters(entity_type, cu.id, db)




@router.post("/filters")
def save_filter(p: SavedFilterIn, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return create_saved_filter(p.model_dump(), cu.id, db)


@router.delete("/filters/{filter_id}")
def delete_filter(filter_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return delete_saved_filter(filter_id, cu.id, db)


# ══════════════════════════════════════════════════════════════════════
# 5. CUMULATIVE FLOW DIAGRAM
# ══════════════════════════════════════════════════════════════════════

@router.post("/cfd/snapshot")
def take_snapshot(project_id: str, sprint_id: Optional[str] = None,
                  db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    return take_cfd_snapshot(project_id, sprint_id, db)


@router.get("/cfd")
def get_cfd(project_id: str, sprint_id: Optional[str] = None, days: int = 30,
            db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return get_cfd_data(project_id, sprint_id, days, db)


# ══════════════════════════════════════════════════════════════════════
# 6. @MENCIONES
# ══════════════════════════════════════════════════════════════════════

@router.get("/mentions")
def my_mentions(only_unread: bool = True,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return get_my_mentions(cu.id, only_unread, db)


@router.post("/mentions/read-all")
def mark_all_read(db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return mark_all_mentions_read(cu.id, db)


# ══════════════════════════════════════════════════════════════════════
# 7. COMENTARIOS THREADED
# ══════════════════════════════════════════════════════════════════════



@router.get("/comments")
def get_comments(entity_type: str, entity_id: str,
                 db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return list_threaded_comments(entity_type, entity_id, db)


@router.post("/comments")
def add_comment(entity_type: str, entity_id: str, p: ThreadedCommentIn,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return add_threaded_comment(entity_type, entity_id, p.content, p.parent_id, cu.id, db)


@router.patch("/comments/{comment_id}")
def edit_comment(comment_id: str, p: ThreadedCommentIn,
                 db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return edit_threaded_comment(comment_id, p.content, cu.id, db)


@router.patch("/comments/{comment_id}/resolve")
def resolve_comment(comment_id: str, db: Session = Depends(get_db),
                    cu: User = Depends(get_current_user)):
    return resolve_threaded_comment(comment_id, db)


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: str, db: Session = Depends(get_db),
                   cu: User = Depends(get_current_user)):
    return delete_threaded_comment(comment_id, cu.id, db)
