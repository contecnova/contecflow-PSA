"""
user_service.py — Lógica de negocio para usuarios y recursos.

Funciones exportadas:
  scope_users_query(q, current_user) -> Query
  ensure_same_org_user_access(target_user, current_user)
  get_load_map_payload(db, current_user, week_start) -> list
  get_org_chart_payload(db, current_user) -> dict
  approval_chain_for_user(user, db, requesting_user) -> list
  create_user_record(payload, current_user, db) -> User
  update_user_record(user_id, payload, current_user, db) -> User
  get_user_productivity_payload(user_id, date_from, date_to, current_user, db) -> dict
  set_manager_record(user_id, manager_id, current_user, db) -> dict
  get_preferences_payload(user_id, db) -> dict
  update_preferences_record(user_id, payload, db) -> dict
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db.session import sin_filtro_de_tenant

from app.core.config import settings
from app.core.security import get_password_hash, validate_password_policy
from app.models.imputation import Imputation
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.models.user import UserStatus
from app.models.user import UserRole
from app.models.user import UserPreference
from app.models.user import UserOrganizationMembership
from app.models.mfa import Organization
from app.schemas import UserLoad, UserPublic
from fastapi import HTTPException
from app.core import timeutil


# ── Query helpers ──────────────────────────────────────────────────────────────

def scope_users_query(q, current_user):
    if current_user.organization_id:
        q = q.outerjoin(
            UserOrganizationMembership,
            UserOrganizationMembership.user_id == User.id,
        ).filter(
            or_(
                User.organization_id == current_user.organization_id,
                UserOrganizationMembership.organization_id == current_user.organization_id,
            )
        ).distinct()
    return q


def ensure_same_org_user_access(target_user, current_user) -> None:
    if not current_user.organization_id:
        return
    if not target_user.belongs_to_organization(current_user.organization_id):
        raise HTTPException(status_code=404, detail="Usuario no encontrado")


def _normalize_org_ids(org_ids: Optional[list[str]]) -> list[str]:
    if not org_ids:
        return []
    return sorted({str(v).strip() for v in org_ids if str(v).strip()})


def _validate_org_ids(org_ids: list[str], db: Session) -> list[str]:
    if not org_ids:
        return []
    found = {
        str(o.id)
        for o in db.query(Organization).filter(Organization.id.in_(org_ids)).all()
    }
    missing = [org_id for org_id in org_ids if org_id not in found]
    if missing:
        raise HTTPException(status_code=400, detail=f"Organizaciones no encontradas: {', '.join(missing)}")
    return org_ids


def _sync_user_memberships(user: User, org_ids: list[str], db: Session) -> None:
    current = {
        str(m.organization_id): m
        for m in (user.organization_memberships or [])
        if m.organization_id
    }

    for org_id in org_ids:
        if org_id not in current:
            db.add(UserOrganizationMembership(user_id=user.id, organization_id=org_id))

    for org_id, membership in current.items():
        if org_id not in org_ids:
            db.delete(membership)


# ── Load map ───────────────────────────────────────────────────────────────────

def get_load_map_payload(db: Session, current_user, week_start: Optional[date] = None) -> list:

    if not week_start:
        today = timeutil.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    month_start = week_start.replace(day=1)

    users = scope_users_query(
        db.query(User).filter(User.is_active == True, User.status == UserStatus.active),
        current_user,
    ).all()
    if not users:
        return []

    user_ids = [u.id for u in users]

    week_hours_rows = (
        db.query(Imputation.user_id, func.sum(Imputation.hours).label("total"))
        .filter(Imputation.user_id.in_(user_ids), Imputation.date >= week_start, Imputation.date <= week_end)
        .group_by(Imputation.user_id).all()
    )
    week_hours = {row.user_id: float(row.total) for row in week_hours_rows}

    month_hours_rows = (
        db.query(Imputation.user_id, func.sum(Imputation.hours).label("total"))
        .filter(Imputation.user_id.in_(user_ids), Imputation.date >= month_start, Imputation.date <= week_end)
        .group_by(Imputation.user_id).all()
    )
    month_hours = {row.user_id: float(row.total) for row in month_hours_rows}

    active_tasks_rows = (
        db.query(Task.assignee_id, func.count(Task.id).label("cnt"))
        .filter(Task.assignee_id.in_(user_ids), Task.status.in_([TaskStatus.in_progress, TaskStatus.todo]))
        .group_by(Task.assignee_id).all()
    )
    active_tasks_map = {row.assignee_id: row.cnt for row in active_tasks_rows}

    active_projects_rows = (
        db.query(Imputation.user_id, func.count(func.distinct(Imputation.project_id)).label("cnt"))
        .filter(Imputation.user_id.in_(user_ids), Imputation.date >= week_start, Imputation.date <= week_end)
        .group_by(Imputation.user_id).all()
    )
    active_projects_map = {row.user_id: row.cnt for row in active_projects_rows}

    result = []
    for user in users:
        hours_week   = week_hours.get(user.id, 0.0)
        hours_month  = month_hours.get(user.id, 0.0)
        active_tasks = active_tasks_map.get(user.id, 0)
        active_proj  = active_projects_map.get(user.id, 0)
        capacity = user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS
        load_pct = round((hours_week / capacity) * 100, 1) if capacity > 0 else 0
        result.append(UserLoad(
            user=UserPublic.model_validate(user),
            current_load_pct=load_pct,
            hours_this_week=hours_week,
            hours_this_month=hours_month,
            active_tasks=active_tasks,
            active_projects=active_proj,
            hourly_rate=user.hourly_rate if getattr(current_user, 'role', None) in ('admin', 'hr') else None,
        ))

    result.sort(key=lambda x: x.current_load_pct, reverse=True)
    return result


# ── Org chart ──────────────────────────────────────────────────────────────────

def get_org_chart_payload(db: Session, current_user) -> dict:
    users = scope_users_query(db.query(User).filter(User.is_active == True), current_user).all()
    user_map = {u.id: {
        "id": u.id, "full_name": u.full_name, "job_title": u.job_title,
        "department": u.department, "role": u.role, "email": u.email,
        "manager_id": u.manager_id, "avatar_url": u.avatar_url,
        "children": []
    } for u in users}
    roots = []
    for uid, node in user_map.items():  # noqa: B007
        mid = node["manager_id"]
        if mid and mid in user_map:
            user_map[mid]["children"].append(node)
        else:
            roots.append(node)
    return {"nodes": roots, "total": len(user_map)}


# ── Approval chain ─────────────────────────────────────────────────────────────

def approval_chain_for_user(user, db: Session, requesting_user) -> list:
    """Walk the manager hierarchy for `user`, returning list of manager dicts."""
    chain = []
    current = user
    visited = set()
    while current.manager_id and current.manager_id not in visited:
        visited.add(current.id)
        manager = db.query(User).filter(User.id == current.manager_id).first()
        if not manager:
            break
        ensure_same_org_user_access(manager, requesting_user)
        chain.append({
            "id": manager.id,
            "full_name": manager.full_name,
            "job_title": manager.job_title,
            "department": manager.department,
            "role": manager.role,
            "level": len(chain) + 1,
        })
        current = manager
        if len(chain) >= 5:
            break
    return chain


# ── Create user ────────────────────────────────────────────────────────────────

def _resolver_organizaciones_del_alta(user_data: dict, requested_org_ids: list,
                                      current_user, db: Session) -> list:
    """Decide en qué organizaciones se da de alta al usuario, y comprueba que se puede.

    Dos caminos que no se parecen:

      · **Administrador de cliente**: no puede dar de alta fuera de su propia
        organización, ni como principal ni como pertenencia adicional. Si lo
        intenta es un 403, no un silencio: pedir una organización ajena y que
        el alta salga en la propia sería peor que fallar.
      · **Superadmin**: puede elegir, así que las organizaciones pedidas se
        validan contra las que existen. Si da pertenencias pero no principal, la
        primera pasa a ser la principal — un usuario sin organización principal
        no se puede listar en ningún sitio.

    Devuelve la lista de pertenencias y deja `organization_id` puesto en
    `user_data`.
    """
    principal = user_data.get("organization_id")

    # Revisión 2026-11: un admin de empresa podía dar de alta usuarios en
    # cualquier otra (sólo se limitaba a quien no era admin). Fuera del
    # superadmin, sólo las empresas a las que pertenece quien da el alta.
    permitidas = _empresas_permitidas(current_user)
    if permitidas is not None:
        pedidas = {str(o) for o in requested_org_ids} | ({str(principal)} if principal else set())
        if pedidas - permitidas:
            raise HTTPException(403, "No puedes crear usuarios en otra organización")
        if not pedidas:
            propia = current_user.organization_id
            user_data["organization_id"] = propia
            return [str(propia)] if propia else []

    pertenencias = _validate_org_ids(requested_org_ids, db)
    if principal:
        principal = str(principal)
        _validate_org_ids([principal], db)
        if principal not in pertenencias:
            pertenencias.append(principal)
    elif pertenencias:
        principal = pertenencias[0]
    user_data["organization_id"] = principal
    return pertenencias


def _empresas_permitidas(current_user):
    """Empresas en las que puede dar de alta o mover usuarios; None = todas (superadmin)."""
    if getattr(current_user, "is_superadmin", False):
        return None
    propias = {str(m.organization_id) for m in (getattr(current_user, "organization_memberships", None) or [])
               if m.organization_id}
    if current_user.organization_id:
        propias.add(str(current_user.organization_id))
    return propias


def create_user_record(payload, current_user, db: Session):
    """Da de alta un usuario, con sus pertenencias a organizaciones."""
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username ya existe")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email ya registrado")

    if payload.password:
        ok, err = validate_password_policy(
            payload.password, db=db,
            org_id=getattr(current_user, "organization_id", None),
        )
        if not ok:
            raise HTTPException(status_code=400, detail=err)

    user_data = payload.model_dump(exclude={"password"})
    pertenencias = _resolver_organizaciones_del_alta(
        user_data,
        _normalize_org_ids(user_data.pop("organization_ids", None)),
        current_user, db,
    )

    # Revision multitenant 2026-11: el limite de usuarios del plan.
    from app.services.organizations_service import exigir_cupo
    # Sin empresa explicita, el alta queda en la de quien la hace (el sellado).
    destino = {user_data.get("organization_id"), *(pertenencias or [])} - {None}
    for org_id in destino or {getattr(current_user, "organization_id", None)} - {None}:
        exigir_cupo(db, org_id, "users")

    user = User(**user_data)
    if payload.password:
        user.hashed_password = get_password_hash(payload.password)

    db.add(user)
    db.flush()
    if pertenencias:
        _sync_user_memberships(user, pertenencias, db)
    db.commit()

    # Mismo caso que en `update_user_record`: si el alta crea al usuario en otra
    # organizacion —un superadmin dando de alta al primer administrador de un
    # cliente nuevo—, la sesion de quien llama no puede releer la fila. El
    # porque, largo, esta en `sin_filtro_de_tenant`.
    with sin_filtro_de_tenant(db):
        db.refresh(user)
        # Y las pertenencias **dentro** del bloque, no fuera: son una relacion
        # perezosa, asi que si se cargan al serializar la respuesta lo hacen ya
        # con el filtro puesto y el alta responde con las organizaciones del que
        # llama en vez de las del usuario recien creado. Tocarlas aqui las deja
        # cargadas.
        _ = list(user.organization_memberships or [])
    return user


# ── Update user ────────────────────────────────────────────────────────────────

# ── Edicion de un usuario ────────────────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18 + defecto de autorizacion encontrado de paso).
# `update_user_record` era complejidad 23 en cuatro fases: autorizar, validar el
# cambio de organizacion, comprobar el correo y aplicar los campos.
#
# ── El defecto ────────────────────────────────────────────────────────────────
#
# `PATCH /users/{user_id}` usa `get_current_user`, no `require_admin`: una
# persona puede editar su PROPIA ficha por ahi, con el esquema ANCHO
# (`UserUpdate`). Y los campos se aplicaban con un bucle generico:
#
#     for field, value in payload.model_dump(exclude_unset=True).items():
#         setattr(user, field, value)
#
# La guarda que habia solo protegia `role` y `hourly_rate`. Se dejaba fuera
# `manager_id`, y `manager_id` ES UNA ENTRADA DE AUTORIZACION: un paso de
# aprobacion con `approver_type == "manager"` autoriza a quien sea
# `requester.manager_id` (ver `approval_engine/_base.py`). La plantilla de flujo
# por defecto trae ese paso como el primero, llamado «Direct Manager».
#
# Es decir: un empleado podia hacer `PATCH /users/{su_propio_id}` con
# `{"manager_id": "..."}` y ELEGIR QUIEN APRUEBA SUS PROPIAS SOLICITUDES.
#
# Y por esa via se saltaban ademas las tres validaciones del endpoint dedicado
# `PATCH /users/{id}/manager` -> `set_manager_record()`, que si comprueba que el
# manager existe, que es de la misma organizacion y que no se forma un ciclo en
# la jerarquia. Tambien quedaba libre `status`.
#
# Mismo patron que atraviesa la auditoria: el control cuidadoso existe, y hay
# una segunda via que lo salta entera.
#
# ── El arreglo ────────────────────────────────────────────────────────────────
#
# Quien no es administrador solo puede cambiar de su propia ficha los campos que
# la propia aplicacion declara como autoeditables: los de `UserSelfUpdate`, el
# esquema del endpoint `/users/me`. Se leen de ahi en vez de repetirlos, para
# que las dos listas no puedan separarse.


def _campos_de_autoedicion() -> frozenset[str]:
    """Los campos que una persona puede cambiar de su propia ficha.

    Se derivan de `UserSelfUpdate` —el esquema que el endpoint `/users/me` ya
    usa— y no de una lista escrita aqui: una lista paralela se separaria de la
    otra al primer campo nuevo, y el que se olvidara quedaria abierto sin que
    nada fallara.
    """
    from app.schemas.users import UserSelfUpdate

    return frozenset(UserSelfUpdate.model_fields)


def _autorizar_edicion(user: User, payload, current_user) -> None:
    """Decide si `current_user` puede aplicar este `payload` sobre `user`.

    Un administrador puede todo. El resto solo su propia ficha, y solo los
    campos autoeditables — ver la nota de cabecera para por que eso importa.
    """
    es_admin = current_user.role == UserRole.admin

    if current_user.id != user.id and not es_admin:
        raise HTTPException(
            status_code=403, detail="No tienes permiso para editar este usuario"
        )
    if es_admin:
        return

    enviados = set(payload.model_dump(exclude_unset=True))
    reservados = sorted(enviados - _campos_de_autoedicion())
    if reservados:
        raise HTTPException(
            status_code=403,
            detail=(
                "Solo un administrador puede cambiar estos campos: "
                + ", ".join(reservados)
            ),
        )


def _autorizar_y_validar_organizaciones(payload, current_user, db: Session):
    """Comprueba el cambio de organizacion y devuelve (org_id, org_ids).

    Devuelve None en cada hueco que el payload no traiga. Solo un administrador
    puede mover a alguien de organizacion, y `_autorizar_edicion` ya lo impide
    antes de llegar aqui; estas comprobaciones se conservan como segunda capa
    porque son las que validan que las organizaciones existen.
    """
    payload_org_id = getattr(payload, "organization_id", None)
    payload_org_ids_raw = getattr(payload, "organization_ids", None)
    payload_org_ids = (
        _normalize_org_ids(payload_org_ids_raw)
        if payload_org_ids_raw is not None else None
    )

    permitidas = _empresas_permitidas(current_user)
    if permitidas is not None:
        pedidas = set(map(str, payload_org_ids or [])) | ({str(payload_org_id)} if payload_org_id else set())
        if pedidas - permitidas:
            raise HTTPException(
                status_code=403, detail="No puedes mover usuarios a otra organización"
            )

    if (payload_org_id is not None or payload_org_ids is not None) and current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=403, detail="Solo admin puede cambiar organizaciones"
        )

    if payload_org_ids is not None:
        _validate_org_ids(payload_org_ids, db)

    if payload_org_id is not None:
        payload_org_id = str(payload_org_id) if payload_org_id else None
        if payload_org_id:
            _validate_org_ids([payload_org_id], db)

    return payload_org_id, payload_org_ids


def _validar_correo_unico(payload, user: User, db: Session) -> None:
    """El correo identifica a la persona al iniciar sesion: no puede repetirse.

    La comparacion es sin distinguir mayusculas porque el correo se guarda
    normalizado a minusculas.
    """
    incoming_email = getattr(payload, "email", None)
    if incoming_email is None:
        return
    normalizado = incoming_email.strip().lower()
    existente = (db.query(User)
                   .filter(func.lower(User.email) == normalizado, User.id != user.id)
                   .first())
    if existente:
        raise HTTPException(status_code=400, detail="Email ya registrado")


def _validar_rol(payload, user: User, db: Session) -> None:
    """Rol base valido y rol personalizado de la misma organizacion.

    Auditoria 2026-11: la pantalla ofrecia los roles personalizados en el
    selector del rol base, y guardar uno daba error (no es un `UserRole`).
    """
    enviados = payload.model_dump(exclude_unset=True)
    if enviados.get("role") is not None and enviados["role"] not in {r.value for r in UserRole}:
        raise HTTPException(422, f"Rol base desconocido: {enviados['role']}")
    if "custom_role_id" not in enviados:
        return
    if not enviados["custom_role_id"]:
        payload.custom_role_id = None
        return
    from app.models.advanced_config import CustomRole
    rol = db.query(CustomRole).filter(CustomRole.id == enviados["custom_role_id"],
                                      CustomRole.is_active.is_(True),
                                      CustomRole.organization_id == user.organization_id).first()
    if rol is None or rol.is_system:
        raise HTTPException(422, "Rol personalizado no encontrado en la organización del usuario")


def _aplicar_campos(payload, user: User) -> None:
    """Copia al usuario los campos enviados.

    `organization_ids` se salta: no es una columna sino una pertenencia, y la
    sincroniza `_sincronizar_organizaciones`.
    """
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "organization_ids":
            continue
        if field == "email" and isinstance(value, str):
            value = value.strip().lower()
        setattr(user, field, value)


def _sincronizar_organizaciones(user: User, payload_org_id, payload_org_ids, db: Session) -> None:
    """Ajusta las pertenencias y deja la organizacion principal coherente.

    El ultimo bloque existe para que nadie quede con una organizacion principal
    a la que ya no pertenece: eso lo dejaria sin ver nada, porque el filtro de
    tenant usa ese campo.
    """
    target_org_ids = payload_org_ids
    if target_org_ids is None:
        target_org_ids = user.organization_ids
    if payload_org_id and payload_org_id not in target_org_ids:
        target_org_ids.append(payload_org_id)
    target_org_ids = _normalize_org_ids(target_org_ids)
    _sync_user_memberships(user, target_org_ids, db)

    if payload_org_id is not None:
        user.organization_id = payload_org_id
    elif user.organization_id and str(user.organization_id) not in target_org_ids:
        user.organization_id = target_org_ids[0] if target_org_ids else None
    elif not user.organization_id and target_org_ids:
        user.organization_id = target_org_ids[0]


def update_user_record(user_id: str, payload, current_user, db: Session):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    ensure_same_org_user_access(user, current_user)

    _autorizar_edicion(user, payload, current_user)
    payload_org_id, payload_org_ids = _autorizar_y_validar_organizaciones(
        payload, current_user, db
    )
    _validar_correo_unico(payload, user, db)
    _validar_rol(payload, user, db)
    _aplicar_campos(payload, user)

    cambia_de_organizacion = payload_org_ids is not None or payload_org_id is not None
    if cambia_de_organizacion:
        _sincronizar_organizaciones(user, payload_org_id, payload_org_ids, db)

    db.commit()
    # Auditoria 2026-08. Si el `PATCH` ha movido al usuario a otra organizacion,
    # este `refresh` **no lo encuentra**: la sesion sigue acotada a la
    # organizacion de quien llamo y la fila ya no esta ahi. SQLAlchemy responde
    # `InvalidRequestError: Could not refresh instance`, que sale como 500 —
    # **con el cambio ya cometido**. Salio al registrar el filtro de tenant en
    # la suite; antes ningun test corria con el filtro puesto.
    #
    # Releer una fila que uno mismo acaba de mover es el caso legitimo de
    # `sin_filtro_de_tenant`, y se declara solo cuando hace falta: si el `PATCH`
    # no toca organizaciones, el `refresh` va acotado como siempre.
    if cambia_de_organizacion:
        with sin_filtro_de_tenant(db):
            db.refresh(user)
            # Ver la nota de `create_user_record`: la relacion es perezosa y hay
            # que cargarla aqui dentro o vuelve filtrada.
            _ = list(user.organization_memberships or [])
    else:
        db.refresh(user)
    return user


# ── Productivity ───────────────────────────────────────────────────────────────

def get_user_productivity_payload(
    user_id: str,
    date_from: Optional[date],
    date_to: Optional[date],
    current_user,
    db: Session,
) -> dict:

    if current_user.role == UserRole.employee and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    ensure_same_org_user_access(user, current_user)

    if not date_from:
        date_from = timeutil.today().replace(day=1)
    if not date_to:
        date_to = timeutil.today()

    total_logged = db.query(func.sum(Imputation.hours)).filter(
        Imputation.user_id == user_id,
        Imputation.date.between(date_from, date_to),
    ).scalar() or 0.0

    tasks_done = db.query(func.count(Task.id)).filter(
        Task.assignee_id == user_id,
        Task.status == TaskStatus.done,
        Task.completed_at >= date_from,
        Task.completed_at <= date_to,
    ).scalar() or 0

    by_project = db.query(
        Imputation.project_id,
        func.sum(Imputation.hours).label("hours"),
    ).filter(
        Imputation.user_id == user_id,
        Imputation.date.between(date_from, date_to),
    ).group_by(Imputation.project_id).all()

    return {
        "user_id": user_id,
        "user_name": user.full_name,
        "period_start": date_from,
        "period_end": date_to,
        "total_hours_logged": total_logged,
        "tasks_completed": tasks_done,
        "by_project": [{"project_id": r[0], "hours": r[1]} for r in by_project],
    }


# ── Set manager ────────────────────────────────────────────────────────────────

def set_manager_record(user_id: str, manager_id: Optional[str], current_user, db: Session) -> dict:

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    ensure_same_org_user_access(user, current_user)

    if manager_id:
        manager = db.query(User).filter(User.id == manager_id).first()
        if not manager:
            raise HTTPException(404, "Manager no encontrado")
        ensure_same_org_user_access(manager, current_user)
        # Detect cycles
        check = manager
        while check.manager_id:
            if check.manager_id == user_id:
                raise HTTPException(400, "Ciclo detectado en la jerarquía")
            check = db.query(User).filter(User.id == check.manager_id).first()
            if not check:
                break
            ensure_same_org_user_access(check, current_user)

    user.manager_id = manager_id
    db.commit()
    return {"ok": True, "manager_id": manager_id}


# ── Preferences ────────────────────────────────────────────────────────────────

#: Los temas de `index.css` (`dark` es el de `:root`) y `system`, que sigue al
#: sistema operativo. Auditoria 2026-11: la columna era `String(10)` y en
#: Postgres `high-contrast` y la densidad `comfortable` no se podian guardar.
TEMAS = ("freight", "dark", "light", "high-contrast", "midnight", "slate", "system")
DENSIDADES = ("compact", "normal", "comfortable")

def get_preferences_payload(user_id: str, db: Session) -> dict:
    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if not pref:
        return {
            "dashboard_widgets": None, "accent_color": None,
            "theme_mode": "freight", "sidebar_collapsed": False,
            "language": settings.DEFAULT_LANGUAGE, "ui_density": "normal", "extra": None,
        }
    return {
        "dashboard_widgets": json.loads(pref.dashboard_widgets) if pref.dashboard_widgets else None,
        # Vacio: el acento del tema. Auditoria 2026-11: se devolvia #4f8ef7 y
        # tapaba siempre el acento propio de cada tema (el dorado de freight).
        "accent_color":      pref.accent_color,
        "theme_mode":        pref.theme_mode or "freight",
        "sidebar_collapsed": pref.sidebar_collapsed or False,
        "language":          pref.language or settings.DEFAULT_LANGUAGE,
        "ui_density":        pref.ui_density or "normal",
        "extra":             json.loads(pref.extra) if pref.extra else None,
    }


# ── Paged user list ────────────────────────────────────────────────────────────

def list_users_paged(
    db: Session,
    current_user,
    department: Optional[str] = None,
    role=None,
    status=None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
):
    q = scope_users_query(db.query(User), current_user)
    if department:
        q = q.filter(User.department == department)
    if role:
        q = q.filter(User.role == role)
    if status:
        q = q.filter(User.status == status)
    if search:
        q = q.filter(
            (User.full_name.ilike(f"%{search}%"))
            | (User.username.ilike(f"%{search}%"))
            | (User.email.ilike(f"%{search}%"))
        )
    total = q.count()
    users = q.offset((page - 1) * page_size).limit(page_size).all()
    return users, total


def list_active_users_with_rates(db: Session, current_user):
    return scope_users_query(
        db.query(User).filter(User.is_active == True),
        current_user,
    ).all()


# ── Single user lookup ─────────────────────────────────────────────────────────

def get_user_by_id(db: Session, user_id: str):
    return db.query(User).filter(User.id == user_id).first()


# ── Self-profile update ────────────────────────────────────────────────────────

def update_self_profile(user, update_data: dict, db: Session):
    allowed_fields = {"email", "first_name", "last_name", "full_name", "phone", "job_title", "avatar_url"}

    incoming_email = update_data.get("email")
    if incoming_email is not None:
        normalized_email = incoming_email.strip().lower()
        existing = db.query(User).filter(func.lower(User.email) == normalized_email, User.id != user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email ya registrado")

    for field, value in update_data.items():
        if field in allowed_fields:
            if field == "email" and isinstance(value, str):
                value = value.strip().lower()
            setattr(user, field, value)
            if field in ("first_name", "last_name"):
                fn = user.first_name or ""
                ln = user.last_name or ""
                if fn or ln:
                    user.full_name = f"{fn} {ln}".strip()
    db.commit()
    db.refresh(user)
    return user


# ── Deactivate / delete user ───────────────────────────────────────────────────

def deactivate_user_record(user, db: Session) -> None:
    user.is_active = False
    user.status = UserStatus.inactive
    db.commit()


def delete_user_record(user, db: Session) -> None:
    db.delete(user)
    db.commit()


# ── Preferences ────────────────────────────────────────────────────────────────

def update_preferences_record(user_id: str, payload: dict, db: Session) -> dict:
    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if not pref:
        pref = UserPreference(id=str(uuid.uuid4()), user_id=user_id)
        db.add(pref)

    if "dashboard_widgets" in payload:
        pref.dashboard_widgets = json.dumps(payload["dashboard_widgets"]) if payload["dashboard_widgets"] is not None else None
    if payload.get("accent_color") is not None and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(payload["accent_color"])):
        raise HTTPException(422, "El acento es un color #rrggbb, o vacío para usar el del tema")
    if "accent_color"      in payload: pref.accent_color      = payload["accent_color"] or None
    if payload.get("theme_mode") is not None and payload["theme_mode"] not in TEMAS:
        raise HTTPException(422, f"Tema desconocido: {payload['theme_mode']}")
    if payload.get("ui_density") is not None and payload["ui_density"] not in DENSIDADES:
        raise HTTPException(422, f"Densidad desconocida: {payload['ui_density']}")
    if "theme_mode"        in payload: pref.theme_mode        = payload["theme_mode"]
    if "sidebar_collapsed" in payload: pref.sidebar_collapsed = payload["sidebar_collapsed"]
    if "language"          in payload: pref.language          = payload["language"]
    if "ui_density"        in payload: pref.ui_density        = payload["ui_density"]
    if "extra" in payload:
        # Revisión 2026-11: `extra` se fusiona por claves (una clave a null se
        # borra), para que cada pantalla guarde lo suyo sin pisar lo de otra.
        if payload["extra"] is None:
            pref.extra = None
        else:
            if not isinstance(payload["extra"], dict):
                raise HTTPException(422, "extra es un objeto de claves")
            actual = json.loads(pref.extra) if pref.extra else {}
            for clave, valor in payload["extra"].items():
                if valor is None:
                    actual.pop(clave, None)
                else:
                    actual[clave] = valor
            pref.extra = json.dumps(actual) if actual else None

    db.commit()
    return {"ok": True}
