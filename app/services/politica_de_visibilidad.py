"""Quién ve a quién, y qué ajustes ve cada uno (segunda auditoría 2026-11).

Una sola regla para todos los endpoints de personas y de ajustes. Antes cada
endpoint decidía por su cuenta y el subcontratado (`UserRole.subcontractor`)
se colaba: `GET /users/{id}` solo frenaba al empleado, y el organigrama y la
productividad ajena solo pedían sesión.

**Personas.**

- Los roles de gestión (admin, pm, team_lead, hr) siguen viendo lo que veían:
  su empresa (`scope_users_query`) y, en cada endpoint, lo que su rol permita.
- El empleado ve a la gente de su empresa para asignar o mencionar, pero no su
  contacto: en `GET /users`, la ficha interna (mínima + departamento y si está
  activa); en el equipo de un proyecto, solo de los proyectos que ve y sin
  correo; ni organigrama ni ficha ajena (`ve_contacto_ajeno`).
- El subcontratado es **externo**. Ve su propia ficha completa y, de las
  personas de los proyectos que ve (`scope_projects_query`, la misma regla que
  decide sus proyectos), solo la **ficha mínima**: lo que la interfaz necesita
  para asignar o mencionar (id, nombre, avatar, rol y puesto). Ni correo, ni
  teléfono, ni tarifa, ni manager, ni departamento, ni organigrama, ni la
  productividad de otros. A quien no ve, ni lo encuentra: 404, no 403, para no
  confirmar que existe.

  «Personas de un proyecto» = su PM, sus miembros activos (`project_members`) y
  quienes tienen tareas asignadas en él.

**Ajustes.** Cada ajuste declara su `Audiencia` en el catálogo
(`settings_service.generales`); `audiencia_de` dice hasta dónde llega quien
pregunta. El externo solo recibe los de audiencia `SESION` (marca, idioma,
moneda, zona, jornada y el cierre por inactividad, que la interfaz tiene que
conocer para aplicarlo).
"""
from __future__ import annotations

from enum import IntEnum
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.user import User, UserRole

#: Lo único que un externo ve de otra persona. Basta para pintar un selector de
#: responsable o una mención: quién es, su cara y qué hace.
#: `external_company` (migracion 178): «Externo · proveedor» en los selectores;
#: None para internos.
CAMPOS_DE_FICHA_MINIMA = ("id", "full_name", "first_name", "last_name", "avatar_url", "role", "job_title",
                          "external_company")

#: Roles que ven la ficha completa de otra persona de su empresa (la tarifa la
#: sigue filtrando `ve_tarifas`).
_ROLES_CON_FICHA_AJENA = frozenset(r.value for r in (UserRole.admin, UserRole.pm, UserRole.team_lead, UserRole.hr))

#: Roles que solo ven sus propias estadísticas de productividad.
_ROLES_SIN_ESTADISTICAS_AJENAS = frozenset(r.value for r in (UserRole.employee, UserRole.subcontractor))

#: Roles que ven la tarifa horaria de otra persona.
_ROLES_QUE_VEN_TARIFAS = frozenset(r.value for r in (UserRole.admin, UserRole.hr))


class Audiencia(IntEnum):
    """Quién puede leer un ajuste. Cada nivel incluye a los anteriores."""

    SESION = 0   #: cualquiera con sesión, el subcontratado incluido
    INTERNA = 1  #: la plantilla interna
    ADMIN = 2    #: el administrador de la empresa


def _rol(usuario) -> Optional[str]:
    rol = getattr(usuario, "role", None)
    return getattr(rol, "value", rol)


def _es_superadmin(usuario) -> bool:
    return bool(getattr(usuario, "is_superadmin", False))


def es_externo(viewer) -> bool:
    """El subcontratado: ve lo suyo y lo de sus proyectos, no la empresa."""
    return not _es_superadmin(viewer) and _rol(viewer) == UserRole.subcontractor.value


# ── Personas ──────────────────────────────────────────────────────────────────

def ids_de_personas_visibles(db: Session, viewer) -> Optional[set[str]]:
    """Ids de las personas que `viewer` puede ver; `None` = toda su empresa."""
    if not es_externo(viewer):
        return None
    from app.models.project import Project, ProjectMember
    from app.models.task import Task
    from app.services.project_service import scope_projects_query

    proyectos = scope_projects_query(db.query(Project.id), db, viewer).subquery()
    visibles = {viewer.id}
    for columna, filtro in (
        (Project.pm_id, Project.id.in_(db.query(proyectos.c.id))),
        (ProjectMember.user_id, ProjectMember.project_id.in_(db.query(proyectos.c.id))
         & ProjectMember.is_active.is_(True)),
        (Task.assignee_id, Task.project_id.in_(db.query(proyectos.c.id))),
    ):
        visibles |= {fila[0] for fila in db.query(columna).filter(filtro, columna.isnot(None)).distinct()}
    return visibles


def acotar_personas(q, db: Session, viewer):
    """Filtra una consulta sobre `User` a las personas que `viewer` ve."""
    ids = ids_de_personas_visibles(db, viewer)
    return q if ids is None else q.filter(User.id.in_(ids))


def ficha_minima(usuario) -> dict:
    datos = {campo: getattr(usuario, campo, None) for campo in CAMPOS_DE_FICHA_MINIMA}
    datos["role"] = _rol(usuario)
    return datos


def ve_ficha_completa_de(db: Session, viewer, objetivo) -> bool:
    """¿Ficha completa (True) o mínima (False)? Lanza si no puede ver a nadie.

    - la propia, o un rol de gestión (admin, pm, team_lead, hr): completa;
    - el externo, de alguien de sus proyectos: mínima; de otro: 404;
    - el empleado, de otra persona: 403 (como antes de esta política).
    """
    if viewer.id == objetivo.id or _es_superadmin(viewer) or _rol(viewer) in _ROLES_CON_FICHA_AJENA:
        return True
    if es_externo(viewer):
        if objetivo.id in ids_de_personas_visibles(db, viewer):
            return False
        raise ErrorDeDominio(status_code=404, detail="Usuario no encontrado")
    raise ErrorDeDominio(status_code=403, detail="Acceso denegado")


def ve_tarifas(viewer) -> bool:
    return _es_superadmin(viewer) or _rol(viewer) in _ROLES_QUE_VEN_TARIFAS


def ve_contacto_ajeno(viewer) -> bool:
    """Correo y teléfono de otras personas: solo los roles con ficha ajena.

    Segunda auditoría 2026-11 (empleado): el empleado recibía 403 en
    `GET /users/{otro}` pero el correo y el teléfono de toda la empresa en
    `GET /users`, en el equipo de cualquier proyecto y en el organigrama. Ahora
    una sola regla: quien no ve la ficha ajena tampoco ve su contacto.
    """
    return _es_superadmin(viewer) or _rol(viewer) in _ROLES_CON_FICHA_AJENA


def exigir_organigrama(viewer) -> None:
    """El organigrama retrata la empresa entera, con correos y jerarquía: solo
    para quien ve la ficha ajena (la pantalla `/org-chart` ya excluía al
    empleado y al externo; la API no)."""
    if not ve_contacto_ajeno(viewer):
        raise ErrorDeDominio(status_code=403, detail="El organigrama no está disponible para tu rol")


#: Lo que ve un empleado de otra persona en un listado (`GET /users`): la ficha
#: mínima más lo que sus selectores filtran (departamento y si está activa).
CAMPOS_DE_FICHA_INTERNA = CAMPOS_DE_FICHA_MINIMA + ("department", "is_active")


def ficha_de_listado(viewer, usuario):
    """Una fila de `GET /users`: completa (la propia o un rol con ficha ajena)
    o la ficha interna (empleado), sin correo, teléfono, manager ni accesos."""
    if usuario.id == viewer.id or ve_contacto_ajeno(viewer):
        return usuario
    datos = {campo: getattr(usuario, campo, None) for campo in CAMPOS_DE_FICHA_INTERNA}
    datos["role"] = _rol(usuario)
    return datos


# ── Proyectos ─────────────────────────────────────────────────────────────────

#: Roles cuyo alcance de proyectos es «los suyos» (`scope_projects_query`).
_ROLES_CON_PROYECTOS_PROPIOS = frozenset(r.value for r in (UserRole.employee, UserRole.subcontractor))


def solo_proyectos_propios(viewer) -> bool:
    return not _es_superadmin(viewer) and _rol(viewer) in _ROLES_CON_PROYECTOS_PROPIOS


def acotar_a_proyectos_visibles(q, columna, db: Session, viewer):
    """Filas ligadas a un proyecto (`columna`): para quien solo ve sus proyectos,
    las de esos proyectos (`scope_projects_query`); las sin proyecto, no. Quien
    ve toda la empresa no cambia (el aislamiento por empresa ya lo pone
    `TenantSession`)."""
    if not solo_proyectos_propios(viewer):
        return q
    from app.models.project import Project
    from app.services.project_service import scope_projects_query
    visibles = scope_projects_query(db.query(Project.id), db, viewer).subquery()
    return q.filter(columna.in_(db.query(visibles.c.id)))


# ── Finanzas ──────────────────────────────────────────────────────────────────

def ve_modulo_financiero(db: Session, viewer, modulo: str) -> bool:
    """¿Puede `viewer` leer el módulo financiero `modulo` (invoices, pipeline,
    budgets, contracts)? Las mismas dos guardas que sus rutas propias: el rol
    (`require_any_manager`) y la matriz GRC (`ver` no denegado)."""
    if _es_superadmin(viewer):
        return True
    from app.core.deps import require_any_manager
    if getattr(viewer, "role", None) not in require_any_manager.roles:
        return False
    from app.core.grc_enforce import decidir
    return not decidir(db, viewer, modulo, "ver", getattr(viewer, "organization_id", None))["denied"]


def exigir_estadisticas_de(viewer, user_id: str) -> None:
    """Productividad: la propia siempre; la ajena, solo roles de gestión."""
    if viewer.id != user_id and not _es_superadmin(viewer) and _rol(viewer) in _ROLES_SIN_ESTADISTICAS_AJENAS:
        raise ErrorDeDominio(status_code=403, detail="Acceso denegado")


def exigir_proyecto_visible(db: Session, viewer, project_id: str) -> None:
    """Para quien solo ve sus proyectos (empleado, externo), uno que no ve no
    existe (404). Segunda auditoría 2026-11: antes solo frenaba al externo."""
    if not solo_proyectos_propios(viewer):
        return
    from app.models.project import Project
    from app.services.project_service import scope_projects_query
    if not scope_projects_query(db.query(Project.id), db, viewer).filter(Project.id == project_id).first():
        raise ErrorDeDominio(status_code=404, detail="Proyecto no encontrado")


#: De un miembro de proyecto (`list_members_payload`), lo que ve el externo:
#: sin correo, dedicación, fechas ni notas.
CAMPOS_DE_MIEMBRO_PARA_EXTERNOS = ("id", "user_id", "full_name", "avatar_initials", "role", "external_company")


#: Contacto de un miembro: lo que pierde quien no ve el contacto ajeno.
_CAMPOS_DE_CONTACTO_DE_MIEMBRO = ("email", "phone")


def recortar_miembros(viewer, filas: list[dict]) -> list[dict]:
    if es_externo(viewer):
        return [{campo: fila.get(campo) for campo in CAMPOS_DE_MIEMBRO_PARA_EXTERNOS} for fila in filas]
    if ve_contacto_ajeno(viewer):
        return filas

    def _sin_contacto(fila: dict) -> dict:
        if fila.get("user_id") == viewer.id:
            return fila
        return {**fila, **{c: None for c in _CAMPOS_DE_CONTACTO_DE_MIEMBRO if c in fila}}
    return [_sin_contacto(fila) for fila in filas]


def fichas_para(viewer, usuarios) -> list:
    """Fichas de personas que ya se sabe que `viewer` puede ver (p. ej. las de un
    proyecto suyo): públicas para quien ve el contacto ajeno, mínimas para el
    resto (empleado y externo)."""
    if not ve_contacto_ajeno(viewer):
        return [ficha_minima(u) for u in usuarios]
    from app.schemas import UserPublic
    return [UserPublic.model_validate(u) for u in usuarios]


# ── Ajustes ───────────────────────────────────────────────────────────────────

def audiencia_de(viewer) -> Audiencia:
    if _es_superadmin(viewer) or _rol(viewer) == UserRole.admin.value:
        return Audiencia.ADMIN
    if es_externo(viewer):
        return Audiencia.SESION
    return Audiencia.INTERNA


# ── Contactos de clientes (18-11-2026) ────────────────────────────────────────
# Las personas de un cliente (contactos y su reflejo `contact_*` en la ficha)
# son datos personales. Los internos con acceso al cliente
# (`client_service.scoped_client_query`) los ven; el externo (subcontratado)
# solo ve quién es (nombre, cargo, rol), sin email, teléfono ni notas.

#: Lo que se quita de un contacto de cliente a quien no ve datos de contacto.
CAMPOS_DE_CONTACTO_DE_CLIENTE = ("email", "phone", "notes")


def ve_datos_de_contacto_de_clientes(viewer) -> bool:
    """Email, teléfono y notas de las personas de un cliente: la plantilla interna."""
    return viewer is None or not es_externo(viewer)


def recortar_contacto_de_cliente(viewer, fila: dict) -> dict:
    if ve_datos_de_contacto_de_clientes(viewer):
        return fila
    return {k: (None if k in CAMPOS_DE_CONTACTO_DE_CLIENTE else v) for k, v in fila.items()}


def recortar_ficha_de_cliente(viewer, ficha: dict) -> dict:
    """La ficha del cliente: el reflejo del contacto principal y sus contactos."""
    if ve_datos_de_contacto_de_clientes(viewer):
        return ficha
    out = {**ficha, "contact_email": None, "contact_phone": None}
    if isinstance(out.get("contacts"), list):
        out["contacts"] = [recortar_contacto_de_cliente(viewer, c) for c in out["contacts"]]
    return out
