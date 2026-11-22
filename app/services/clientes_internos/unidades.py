"""Unidades internas: validación, miembros deducidos de RR. HH., papeles y alcance."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.clientes_internos import (COST_METHODS, FINANCE_MODES, INTERNAL_TYPES, KINDS, ROLES,
                                          InternalClientRole)
from app.models.clients import Client

#: Campos que solo tienen sentido en un cliente interno.
CAMPOS_INTERNOS = ("internal_type", "department_id", "area_id", "cost_center_id", "group_organization_id",
                   "business_owner_id", "finance_mode", "cost_method", "internal_rate_table_id",
                   "transfer_markup_pct", "erp_account")

#: Campos cuya modificación se audita aparte (finanzas y responsabilidad).
CAMPOS_AUDITADOS = ("kind",) + CAMPOS_INTERNOS

#: Papeles con acceso a costes y con firma.
VEN_COSTES = ("responsable", "finanzas", "direccion")
FIRMAN = ("responsable",)
FIRMAN_UAT = ("responsable", "usuario_clave")


def _v(x):
    return getattr(x, "value", x)


def es_interno(cliente) -> bool:
    return (getattr(cliente, "kind", None) or "externo") == "interno"


# ── Validación de la ficha ───────────────────────────────────────────────────

def validar(data: dict, actual: Optional[Client] = None, org_id: Optional[str] = None) -> dict:
    """Normaliza y valida los campos internos de `data` (alta o edición).

    Devuelve `data` modificado: un externo no lleva campos internos (se limpian).
    """
    kind = data.get("kind", getattr(actual, "kind", None) or "externo") or "externo"
    if kind not in KINDS:
        raise error(422, "interno_tipo_no_valido", valor=kind)
    if "kind" in data:
        data["kind"] = kind
    if kind == "externo":
        if actual is not None and es_interno(actual) or "kind" in data:
            for campo in CAMPOS_INTERNOS:
                if campo in data or (actual is not None and getattr(actual, campo, None) is not None):
                    data[campo] = None
        else:
            for campo in CAMPOS_INTERNOS:
                data.pop(campo, None)
        return data

    def valor(campo):
        return data[campo] if campo in data else getattr(actual, campo, None)

    for campo, lista, codigo in (("internal_type", INTERNAL_TYPES, "interno_subtipo_no_valido"),
                                 ("finance_mode", FINANCE_MODES, "interno_modo_no_valido"),
                                 ("cost_method", COST_METHODS, "interno_metodo_no_valido")):
        v = valor(campo)
        if v not in (None, "") and v not in lista:
            raise error(422, codigo, valor=v)
    if valor("finance_mode") == "intercompania":
        grupo = valor("group_organization_id")
        if not grupo or (org_id and grupo == org_id):
            raise error(422, "interno_intercompania_sin_empresa")
    if valor("cost_method") == "tarifa_interna" and not valor("internal_rate_table_id"):
        raise error(422, "interno_tarifa_obligatoria")
    cuenta = data.get("erp_account")
    if cuenta not in (None, ""):
        from app.services.settings_service.valores_de_negocio import CUENTA_ERP
        cuenta = str(cuenta).strip()
        if not CUENTA_ERP.match(cuenta):
            raise error(422, "interno_cuenta_erp_no_valida")
        data["erp_account"] = cuenta
    margen = valor("transfer_markup_pct")
    if margen not in (None, ""):
        try:
            margen = float(margen)
        except (TypeError, ValueError):
            raise error(422, "interno_margen_fuera_de_rango")
        if not -100 <= margen <= 1000:
            raise error(422, "interno_margen_fuera_de_rango")
        if "transfer_markup_pct" in data:
            data["transfer_markup_pct"] = margen
    if valor("finance_mode") in (None, "") and actual is None:
        data["finance_mode"] = "showback"
    if valor("cost_method") in (None, "") and actual is None:
        data["cost_method"] = "horas_coste"
    return data


def foto(cliente) -> dict:
    return {c: _v(getattr(cliente, c, None)) for c in CAMPOS_AUDITADOS}


def auditar_cambio(db: Session, usuario, cliente, antes: dict) -> None:
    """`audit_log` si cambió algún campo interno (finanzas, responsable, estructura)."""
    despues = foto(cliente)
    cambios = {k: despues[k] for k in CAMPOS_AUDITADOS if antes.get(k) != despues.get(k)}
    if not cambios:
        return
    from app.services.audit import audit_log
    audit_log(db, usuario, "UPDATE", "internal_client", cliente.id, cliente.name,
              old_values={k: antes.get(k) for k in cambios}, new_values=cambios)


def resumen(db: Session, cliente) -> dict:
    """Campos internos para la ficha del cliente (`client_service.get_client_summary`)."""
    if not es_interno(cliente):
        return {"kind": "externo"}
    owner = getattr(cliente, "business_owner", None)
    return {
        "kind": "interno",
        **{c: _v(getattr(cliente, c, None)) for c in CAMPOS_INTERNOS},
        "business_owner_name": owner.full_name if owner else None,
        "members_count": len(miembros_ids(db, cliente)),
    }


def avisos(db: Session, cliente, presupuesto: Optional[dict] = None) -> list[str]:
    """Configuración que falta en la unidad (avisos contextuales del frontend)."""
    salida = []
    if not cliente.business_owner_id:
        salida.append("interno_sin_responsable")
    if not (cliente.department_id or cliente.area_id or cliente.cost_center_id):
        salida.append("interno_sin_estructura")
    if cliente.cost_method == "tarifa_interna" and not cliente.internal_rate_table_id:
        salida.append("interno_sin_tarifa")
    if cliente.finance_mode in ("chargeback", "intercompania") and not (cliente.erp_account or "").strip():
        salida.append("interno_sin_cuenta_erp")
    if presupuesto is not None and not presupuesto.get("budget"):
        salida.append("interno_sin_presupuesto")
    return salida


# ── Miembros (deducidos, sin altas) ──────────────────────────────────────────

def departamentos_de(db: Session, cliente) -> list:
    """Departamentos (filas) que forman la unidad: el suyo, el de su centro y los de su área."""
    from app.models.alm import ALMCostCenter
    from app.models.settings import Department
    ids = set()
    if cliente.department_id:
        ids.add(cliente.department_id)
    if cliente.cost_center_id:
        cc = db.get(ALMCostCenter, cliente.cost_center_id)
        if cc is not None and cc.department_id:
            ids.add(cc.department_id)
    q = db.query(Department)
    filas = q.filter(Department.id.in_(ids)).all() if ids else []
    if cliente.area_id:
        filas += [d for d in q.filter(Department.area_id == cliente.area_id).all() if d.id not in ids]
    return filas


def jefes_de(db: Session, cliente) -> set:
    """Jefes de la estructura de la unidad (departamentos, área, centro de coste)."""
    from app.models.alm import ALMCostCenter
    from app.models.settings import Area
    jefes = {d.manager_id for d in departamentos_de(db, cliente) if d.manager_id}
    if cliente.area_id:
        a = db.get(Area, cliente.area_id)
        if a is not None and a.manager_id:
            jefes.add(a.manager_id)
    if cliente.cost_center_id:
        cc = db.get(ALMCostCenter, cliente.cost_center_id)
        if cc is not None and cc.manager_id:
            jefes.add(cc.manager_id)
    return jefes


def designaciones(db: Session, cliente_id: str) -> list:
    return db.query(InternalClientRole).filter(InternalClientRole.client_id == cliente_id).all()


def miembros(db: Session, cliente) -> list:
    """Usuarios activos de la unidad: los de sus departamentos, el responsable y los designados."""
    from app.models.user import User
    nombres = [d.name for d in departamentos_de(db, cliente) if d.name]
    extra = {cliente.business_owner_id} | {r.user_id for r in designaciones(db, cliente.id)} | jefes_de(db, cliente)
    extra.discard(None)
    # La empresa la acota el filtro de tenant de la sesión (ficha y pertenencias).
    q = db.query(User).filter(User.is_active.is_(True))
    por_dep = q.filter(User.department.in_(nombres)).all() if nombres else []
    vistos = {u.id for u in por_dep}
    otros = db.query(User).filter(User.id.in_(extra - vistos), User.is_active.is_(True)).all() if extra - vistos else []
    return sorted(por_dep + otros, key=lambda u: (u.full_name or "").lower())


def miembros_ids(db: Session, cliente) -> set:
    return {u.id for u in miembros(db, cliente)}


def es_direccion(db: Session, usuario) -> bool:
    if getattr(usuario, "is_superadmin", False):
        return True
    from app.core import capacidades
    return capacidades.tiene(db, usuario, "interno.gestionar")


def papel(db: Session, usuario, cliente) -> Optional[str]:
    """Papel de `usuario` en la unidad, o None si no es de ella."""
    if usuario is None or not es_interno(cliente):
        return None
    if cliente.business_owner_id == usuario.id or usuario.id in jefes_de(db, cliente):
        return "responsable"
    propios = {r.role for r in designaciones(db, cliente.id) if r.user_id == usuario.id}
    if "delegado" in propios:
        return "responsable"
    if "finanzas" in propios:
        return "finanzas"
    if "usuario_clave" in propios:
        return "usuario_clave"
    if usuario.id in miembros_ids(db, cliente):
        return "miembro"
    if es_direccion(db, usuario):
        return "direccion"
    return None


def unidades(db: Session, usuario=None, solo_activas: bool = True) -> list:
    q = db.query(Client).filter(Client.kind == "interno")
    if solo_activas:
        q = q.filter(Client.is_active.is_(True))
    org = getattr(usuario, "organization_id", None)
    if org and not getattr(usuario, "is_superadmin", False):
        q = q.filter((Client.organization_id == org) | Client.organization_id.is_(None))
    return q.order_by(Client.name).all()


def unidades_de(db: Session, usuario) -> list[tuple]:
    """[(unidad, papel)] de las unidades que puede ver `usuario` en el portal."""
    direccion = es_direccion(db, usuario)
    salida = []
    for u in unidades(db, usuario):
        p = papel(db, usuario, u)
        if p is None and direccion:
            p = "direccion"
        if p is not None:
            salida.append((u, p))
    return salida


def unidad_o_404(db: Session, cliente_id: str, usuario=None):
    c = db.query(Client).filter(Client.id == cliente_id, Client.is_active.is_(True)).first()
    org = getattr(usuario, "organization_id", None)
    if c is None or (org and not getattr(usuario, "is_superadmin", False) and c.organization_id not in (None, org)):
        raise error(404, "no_encontrado", detail="Unidad interna no encontrada", que="unidad_interna")
    if not es_interno(c):
        raise error(422, "interno_no_es_interno")
    return c


def exigir_papel(db: Session, usuario, cliente_id: str, papeles: Optional[tuple] = None):
    """(unidad, papel) si `usuario` es de la unidad (y con uno de `papeles`); si no, 403."""
    c = unidad_o_404(db, cliente_id, usuario)
    p = papel(db, usuario, c)
    if p is None:
        raise error(403, "interno_sin_acceso")
    if papeles is not None and p not in papeles and p != "direccion":
        raise error(403, "interno_sin_permiso_costes" if set(papeles) == set(VEN_COSTES) else "interno_solo_responsable")
    return c, p


# ── Designaciones ────────────────────────────────────────────────────────────

def lista_de_miembros(db: Session, cliente) -> list[dict]:
    desig = designaciones(db, cliente.id)
    salida = []
    for u in miembros(db, cliente):
        salida.append({
            "user_id": u.id, "full_name": u.full_name, "email": u.email, "department": u.department,
            "job_title": u.job_title, "role": papel(db, u, cliente),
            "designations": [{"id": r.id, "role": r.role} for r in desig if r.user_id == u.id],
        })
    return salida


def designar(db: Session, actor, cliente_id: str, user_id: str, role: str) -> dict:
    from app.models.user import User
    from app.services.audit import audit_log
    c = unidad_o_404(db, cliente_id, actor)
    if role not in ROLES:
        raise error(422, "interno_papel_no_valido", valor=role)
    u = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if u is None:
        raise error(404, "no_encontrado", detail="Usuario no encontrado", que="usuario")
    r = db.query(InternalClientRole).filter_by(client_id=c.id, user_id=u.id, role=role).first()
    if r is None:
        r = InternalClientRole(organization_id=c.organization_id, client_id=c.id, user_id=u.id, role=role,
                               created_by=actor.id)
        db.add(r)
        db.flush()
        audit_log(db, actor, "CREATE", "internal_client_role", r.id, f"{c.name}: {role}",
                  new_values={"client_id": c.id, "user_id": u.id, "role": role})
        db.commit()
    return {"id": r.id, "client_id": c.id, "user_id": u.id, "role": r.role}


def quitar_designacion(db: Session, actor, cliente_id: str, rol_id: str) -> None:
    from app.services.audit import audit_log
    c = unidad_o_404(db, cliente_id, actor)
    r = db.query(InternalClientRole).filter_by(id=rol_id, client_id=c.id).first()
    if r is None:
        raise error(404, "no_encontrado", detail="Designación no encontrada", que="designacion")
    audit_log(db, actor, "DELETE", "internal_client_role", r.id, f"{c.name}: {r.role}",
              old_values={"client_id": c.id, "user_id": r.user_id, "role": r.role})
    db.delete(r)
    db.commit()


# ── Opciones de los selectores de la ficha ───────────────────────────────────

def opciones(db: Session, usuario) -> dict:
    from app.models.advanced_config import RateTable
    from app.models.alm import ALMCostCenter
    from app.models.mfa import Organization
    from app.models.settings import Area, Department
    from app.models.user import User
    org = getattr(usuario, "organization_id", None)
    empresas = []
    try:
        from app.models.user import UserOrganizationMembership
        ids = {org} | {m.organization_id for m in db.query(UserOrganizationMembership)
                       .filter(UserOrganizationMembership.user_id == usuario.id)}
        from app.db.session import sin_filtro_de_tenant
        with sin_filtro_de_tenant(db):
            empresas = [{"id": o.id, "name": o.name} for o in db.query(Organization).filter(Organization.id.in_(ids))
                        .order_by(Organization.name)]
    except Exception:
        empresas = []
    return {
        "departments": [{"id": d.id, "name": d.name} for d in db.query(Department)
                        .filter(Department.is_active.isnot(False)).order_by(Department.name)],
        "areas": [{"id": a.id, "name": a.name} for a in db.query(Area).filter(Area.is_active.isnot(False))
                  .order_by(Area.name)],
        "cost_centers": [{"id": c.id, "code": c.code, "name": c.name} for c in db.query(ALMCostCenter)
                         .filter(ALMCostCenter.is_active.isnot(False)).order_by(ALMCostCenter.code)],
        "organizations": empresas,
        "rate_tables": [{"id": t.id, "name": t.name} for t in db.query(RateTable)
                        .filter(RateTable.is_active.isnot(False)).order_by(RateTable.name)],
        "users": [{"id": u.id, "full_name": u.full_name} for u in db.query(User)
                  .filter(User.is_active.is_(True)).order_by(User.full_name)],
    }


# ── Filtro externos/internos en cartera y paneles ────────────────────────────

TIPOS_DE_CLIENTE = ("externo", "interno")


def ids_de_clientes_internos(db: Session) -> set:
    return {i for (i,) in db.query(Client.id).filter(Client.kind == "interno")}


def del_tipo(client_id: Optional[str], kind: Optional[str], internos: set) -> bool:
    """¿El cliente (o su ausencia) es del tipo pedido? Sin cliente cuenta como externo
    (proyectos con cliente de texto libre de antes de la rev. 193)."""
    if kind not in TIPOS_DE_CLIENTE:
        return True
    return (client_id in internos) if kind == "interno" else (client_id not in internos)


def filtrar_proyectos(db: Session, proyectos: list, kind: Optional[str]) -> list:
    """Proyectos (filas con `client_id`) cuyo cliente es del tipo pedido; sin tipo, todos."""
    if kind not in TIPOS_DE_CLIENTE:
        return proyectos
    internos = ids_de_clientes_internos(db)
    return [p for p in proyectos if del_tipo(getattr(p, "client_id", None), kind, internos)]


def filtrar_por_proyecto(db: Session, items: list, kind: Optional[str], clave: str = "project_id") -> list:
    """Filas (dicts) con `clave` = id de proyecto cuyo cliente es del tipo pedido."""
    if kind not in TIPOS_DE_CLIENTE or not items:
        return items
    from app.models.project import Project
    ids = [i.get(clave) for i in items]
    cliente = dict(db.query(Project.id, Project.client_id).filter(Project.id.in_(ids)))
    internos = ids_de_clientes_internos(db)
    return [i for i in items if del_tipo(cliente.get(i.get(clave)), kind, internos)]


def tipo_de_cliente(db: Session, client_id: Optional[str]) -> Optional[str]:
    if not client_id:
        return None
    fila = db.query(Client.kind).filter(Client.id == client_id).first()
    return (fila[0] or "externo") if fila else None
