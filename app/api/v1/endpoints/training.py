"""Training & Certificaciones."""
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_hr, require_any_manager, require_internal_user
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User, UserRole
from app.services import training_service
from app.services.training_service import (
    serialize_course as _ser_course,
    serialize_enrollment as _ser_enrollment,
    serialize_certification as _ser_cert,
)
from app.schemas.training import CourseIn, EnrollmentIn, CertificationIn
from app.core.constantes import MAX_TAMANO_DE_PAGINA

router = APIRouter(tags=["Training"])


@router.get("/courses", response_model=APIListResponse[dict], summary="Listar cursos")
def list_courses(category: Optional[str] = None,
                 page: int = Query(1, ge=1),
                 page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
                 db: Session = Depends(get_db),
                 cu: User = Depends(get_current_user), response: Response = None):
    items = [_ser_course(c) for c in training_service.list_courses(db, category=category)]
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


@router.post("/courses", summary="Crear curso", status_code=201)
def create_course(payload: CourseIn, db: Session = Depends(get_db),
                  cu: User = Depends(require_admin_or_hr), response: Response = None):
    c = training_service.create_course(db, payload.model_dump())
    return APIResponse.ok(data={"id": c.id, "title": c.title})


@router.patch("/courses/{course_id}", summary="Actualizar curso")
def update_course(course_id: str, payload: CourseIn, db: Session = Depends(get_db),
                  cu: User = Depends(require_admin_or_hr), response: Response = None):
    c = training_service.get_course(db, course_id)
    if not c:
        raise HTTPException(404, "Curso no encontrado")
    training_service.update_course(db, c, payload.model_dump(exclude_unset=True))
    return APIResponse.ok(data={"id": c.id})


@router.delete("/courses/{course_id}", summary="Eliminar curso")
def delete_course(course_id: str, db: Session = Depends(get_db),
                  cu: User = Depends(require_admin_or_hr), response: Response = None):
    c = training_service.get_course(db, course_id)
    if not c:
        raise HTTPException(404, "Curso no encontrado")
    enforce_abac(db, cu, "training_course", course_id, action="delete")
    training_service.soft_delete_course(db, c)
    return APIResponse.ok(data={"ok": True, "message": "Curso eliminado correctamente"})


@router.get("/enrollments", response_model=APIListResponse[dict], summary="Listar inscripciones")
def list_enrollments(user_id: Optional[str] = None, course_id: Optional[str] = None,
                     status: Optional[str] = None,
                     page: int = Query(1, ge=1),
                     page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
                     db: Session = Depends(get_db),
                     cu: User = Depends(get_current_user), response: Response = None):
    items = [_ser_enrollment(e) for e in training_service.list_enrollments(
        db, user_id=user_id, course_id=course_id, status=status)]
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


@router.post("/enrollments", summary="Crear inscripción", status_code=201)
def create_enrollment(payload: EnrollmentIn, db: Session = Depends(get_db),
                      cu: User = Depends(require_any_manager), response: Response = None):
    e = training_service.create_enrollment(db, payload.model_dump())
    return APIResponse.ok(data={"id": e.id})


@router.patch("/enrollments/{enroll_id}", summary="Actualizar inscripción")
def update_enrollment(enroll_id: str, payload: EnrollmentIn, db: Session = Depends(get_db),
                      cu: User = Depends(require_any_manager), response: Response = None):
    e = training_service.get_enrollment(db, enroll_id)
    if not e:
        raise HTTPException(404, "Inscripción no encontrada")
    training_service.update_enrollment(db, e, payload.model_dump(exclude_unset=True))
    return APIResponse.ok(data={"id": e.id})


@router.delete("/enrollments/{enroll_id}", summary="Eliminar inscripción")
def delete_enrollment(enroll_id: str, db: Session = Depends(get_db),
                      cu: User = Depends(require_any_manager), response: Response = None):
    e = training_service.get_enrollment(db, enroll_id)
    if not e:
        raise HTTPException(404, "Inscripción no encontrada")
    enforce_abac(db, cu, "training_enrollment", enroll_id, action="delete")
    training_service.delete_enrollment(db, e)
    return APIResponse.ok(data={"ok": True, "message": "Inscripción eliminada correctamente"})


@router.get("/certifications", response_model=APIListResponse[dict], summary="Certificaciones de usuarios")
def list_certifications(user_id: Optional[str] = None, expiring_days: Optional[int] = None,
                        page: int = Query(1, ge=1),
                        page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
                        db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    # Revisión 2026-11: fuera de los gestores, cada uno ve sólo las suyas.
    if getattr(cu.role, "value", cu.role) not in ("admin", "hr", "pm", "team_lead"):
        user_id = cu.id
    certs = [_ser_cert(c) for c in training_service.list_certifications(db, user_id=user_id)]
    if expiring_days is not None:
        certs = [c for c in certs if c["days_until_expiry"] is not None
                 and 0 <= c["days_until_expiry"] <= expiring_days]
    return APIListResponse.ok(items=certs, page=page, page_size=page_size)


@router.post("/certifications", summary="Crear certificación", status_code=201)
def create_certification(payload: CertificationIn, db: Session = Depends(get_db),
    _rol: User = Depends(require_internal_user),
                         cu: User = Depends(get_current_user), response: Response = None):
    # Revisión 2026-11: cada uno registra los suyos (ya podía editarlos y borrarlos); admin y RRHH,
    # los de cualquiera. Antes crear era sólo de admin y RRHH.
    datos = payload.model_dump()
    if cu.role not in (UserRole.admin, UserRole.hr):
        datos["user_id"] = cu.id
    c = training_service.create_certification(db, datos)
    return APIResponse.ok(data={"id": c.id})


# Auditoria 2026-08 (hallazgo 37). Estos dos manejadores estaban escritos,
# completos y con su comprobacion de permisos —solo el dueno de la
# certificacion, o admin/RRHH— y **sin decorador de ruta**. No eran endpoints
# que faltaran: eran endpoints que no se registraron, asi que la interfaz podia
# crear una certificacion y no editarla ni borrarla.
#
# Un barrido por AST sobre `app/api/` entera dice que son **los dos unicos**
# casos: las otras funciones sin decorador son dependencias
# (`get_current_client`, `require_admin_or_pm`) y estan bien asi.
@router.patch("/certifications/{cert_id}", summary="Actualizar certificación")
def update_certification(cert_id: str, payload: CertificationIn, db: Session = Depends(get_db),
                         cu: User = Depends(get_current_user), response: Response = None):
    c = training_service.get_certification(db, cert_id)
    if not c:
        raise HTTPException(404, "Certificación no encontrada")
    if c.user_id != cu.id and cu.role not in (UserRole.admin, UserRole.hr):
        raise HTTPException(403, "Solo puedes editar tus propias certificaciones")
    training_service.update_certification(db, c, payload.model_dump(exclude_unset=True))
    return {"id": c.id}


@router.delete("/certifications/{cert_id}", summary="Eliminar certificación")
def delete_certification(cert_id: str, db: Session = Depends(get_db),
                         cu: User = Depends(get_current_user), response: Response = None):
    c = training_service.get_certification(db, cert_id)
    if not c:
        raise HTTPException(404, "Certificación no encontrada")
    if c.user_id != cu.id and cu.role not in (UserRole.admin, UserRole.hr):
        raise HTTPException(403, "Solo puedes eliminar tus propias certificaciones")
    training_service.delete_certification(db, c)
    return {"deleted": True}
