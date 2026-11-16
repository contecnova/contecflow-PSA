"""Kit de alta: qué licencias y qué tipo de equipo corresponden a una persona
según su rol, puesto, departamento o equipo (configurable por empresa).

Al dar de alta a alguien (manual o SCIM, si `ALM_KIT_ON_HIRE`) se crea una
propuesta con la unión de los kits que le aplican; su responsable (su manager
o, si no tiene, los roles de `ALM_KIT_FALLBACK_ROLES`) la confirma con un clic
y se reservan asientos y equipos del almacén, o se piden por compra.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.models.alm import ALMLicense, AssetType
from app.models.alm_integracion import (
    CRITERIOS_DE_KIT, TIPOS_DE_ELEMENTO, ALMKit, ALMKitElemento, ALMPropuestaDeKit,
)
from app.models.user import User
from app.services.alm_integracion import _comun as c
from app.services.alm_integracion import _suministro as s

#: Atributo de la persona que mira cada criterio.
ATRIBUTO_DE_CRITERIO = {"rol": "role", "puesto": "job_title", "departamento": "department", "equipo": "team"}

TIPOS_DE_EQUIPO = tuple(t.value for t in AssetType)


# ── Configuración de kits ─────────────────────────────────────────────────────

def _limpiar_elementos(db: Session, elementos: list) -> list[dict]:
    limpios = []
    for e in elementos or []:
        tipo = (e or {}).get("tipo")
        c.exigir(tipo in TIPOS_DE_ELEMENTO, "almint_tipo_invalido")
        try:
            cantidad = int(e.get("cantidad") or 1)
        except (TypeError, ValueError):
            cantidad = 0
        c.exigir(cantidad >= 1, "almint_cantidad_invalida")
        if tipo == "licencia":
            lic = db.query(ALMLicense).filter(ALMLicense.id == e.get("license_id"),
                                              ALMLicense.is_active.is_(True)).first()
            c.exigir(lic is not None, "almint_licencia_no_encontrada", 404)
            limpios.append({"tipo": tipo, "license_id": lic.id, "asset_type": None, "cantidad": 1,
                            "notas": (e.get("notas") or None)})
        else:
            c.exigir(e.get("asset_type") in TIPOS_DE_EQUIPO, "almint_tipo_de_equipo_invalido")
            limpios.append({"tipo": tipo, "license_id": None, "asset_type": e["asset_type"],
                            "cantidad": cantidad, "notas": (e.get("notas") or None)})
    c.exigir(bool(limpios), "almint_kit_vacio")
    return limpios


def guardar_kit(db: Session, datos: dict, actor, kit_id: Optional[str] = None) -> dict:
    nombre = (datos.get("nombre") or "").strip()
    c.exigir(bool(nombre), "almint_nombre_obligatorio")
    criterio = datos.get("criterio") or "todos"
    c.exigir(criterio in CRITERIOS_DE_KIT, "almint_criterio_invalido")
    valor = (datos.get("valor") or "").strip() or None
    c.exigir(criterio == "todos" or bool(valor), "almint_valor_obligatorio")
    elementos = _limpiar_elementos(db, datos.get("elementos") or [])
    if kit_id:
        kit = db.get(ALMKit, kit_id)
        c.exigir(kit is not None, "almint_kit_no_encontrado", 404)
        db.query(ALMKitElemento).filter(ALMKitElemento.kit_id == kit.id).delete(synchronize_session=False)
    else:
        kit = ALMKit(organization_id=getattr(actor, "organization_id", None), created_by=getattr(actor, "id", None))
        db.add(kit)
    kit.nombre, kit.descripcion = nombre[:200], (datos.get("descripcion") or None)
    kit.criterio, kit.valor = criterio, (None if criterio == "todos" else valor[:200])
    kit.is_active = bool(datos.get("is_active", True))
    db.flush()
    for e in elementos:
        db.add(ALMKitElemento(organization_id=kit.organization_id, kit_id=kit.id, **e))
    from app.services.audit import audit_log
    audit_log(db, actor, "UPDATE" if kit_id else "CREATE", "alm_kit", kit.id, kit.nombre,
              new_values={"criterio": criterio, "valor": kit.valor, "elementos": elementos})
    db.commit()
    return serializar_kit(db, kit)


def borrar_kit(db: Session, kit_id: str, actor) -> dict:
    """Se desactiva (las propuestas ya hechas lo siguen nombrando)."""
    kit = db.get(ALMKit, kit_id)
    c.exigir(kit is not None, "almint_kit_no_encontrado", 404)
    kit.is_active = False
    from app.services.audit import audit_log
    audit_log(db, actor, "DELETE", "alm_kit", kit.id, kit.nombre)
    db.commit()
    return {"ok": True}


def listar_kits(db: Session) -> list[dict]:
    return [serializar_kit(db, k) for k in db.query(ALMKit).filter(ALMKit.is_active.is_(True))
            .order_by(ALMKit.nombre).all()]


def serializar_kit(db: Session, kit: ALMKit) -> dict:
    elementos = db.query(ALMKitElemento).filter(ALMKitElemento.kit_id == kit.id).all()
    return {
        "id": kit.id, "nombre": kit.nombre, "descripcion": kit.descripcion, "criterio": kit.criterio,
        "valor": kit.valor, "is_active": kit.is_active,
        "elementos": [_elemento(db, e.tipo, e.license_id, e.asset_type, e.cantidad, e.notas) for e in elementos],
    }


def _elemento(db: Session, tipo, license_id, asset_type, cantidad, notas=None) -> dict:
    lic = db.get(ALMLicense, license_id) if license_id else None
    return {"clave": f"lic:{license_id}" if tipo == "licencia" else f"eq:{asset_type}", "tipo": tipo,
            "license_id": license_id, "license_name": lic.name if lic else None,
            "asset_type": asset_type, "cantidad": cantidad, "notas": notas}


# ── A quién aplica ────────────────────────────────────────────────────────────

def _aplica(kit: ALMKit, user: User) -> bool:
    if kit.criterio == "todos":
        return True
    atributo = ATRIBUTO_DE_CRITERIO.get(kit.criterio)
    valor = getattr(user, atributo, None) if atributo else None
    valor = getattr(valor, "value", valor)
    return bool(valor) and str(valor).strip().lower() == (kit.valor or "").strip().lower()


def kits_para(db: Session, user: User) -> list[ALMKit]:
    return [k for k in db.query(ALMKit).filter(ALMKit.is_active.is_(True)).all() if _aplica(k, user)]


def elementos_para(db: Session, kits: list[ALMKit]) -> list[dict]:
    """La unión de los kits: una licencia una vez; de cada tipo de equipo, la mayor cantidad."""
    union: dict[str, dict] = {}
    for kit in kits:
        for e in db.query(ALMKitElemento).filter(ALMKitElemento.kit_id == kit.id).all():
            el = _elemento(db, e.tipo, e.license_id, e.asset_type, e.cantidad)
            previo = union.get(el["clave"])
            if previo is None or el["cantidad"] > previo["cantidad"]:
                union[el["clave"]] = el
    return list(union.values())


# ── Propuestas ────────────────────────────────────────────────────────────────

def responsable_de(db: Session, user: User) -> Optional[str]:
    """Quien confirma: el manager de la persona (si está activo)."""
    if user.manager_id:
        jefe = db.get(User, user.manager_id)
        if jefe is not None and jefe.is_active:
            return jefe.id
    return None


def proponer(db: Session, user: User, actor=None, *, forzar: bool = False) -> Optional[ALMPropuestaDeKit]:
    """Crea la propuesta de kit de la persona si le aplica alguno. No confirma.

    Sin ``forzar`` respeta `ALM_KIT_ON_HIRE` y no repite si ya hay una pendiente.
    """
    org = user.organization_id
    with c.en_organizacion(db, org):
        if not forzar and not c.ajuste_bool(db, "ALM_KIT_ON_HIRE", org):
            return None
        pendiente = db.query(ALMPropuestaDeKit).filter(ALMPropuestaDeKit.user_id == user.id,
                                                       ALMPropuestaDeKit.estado == "pendiente").first()
        if pendiente is not None:
            return pendiente
        kits = kits_para(db, user)
        elementos = elementos_para(db, kits)
        if not elementos:
            return None
        p = ALMPropuestaDeKit(organization_id=org, user_id=user.id, responsable_id=responsable_de(db, user),
                              kits=json.dumps([k.id for k in kits]), elementos=json.dumps(elementos))
        db.add(p)
        db.flush()
        _avisar(db, p, user)
    return p


def _avisar(db: Session, p: ALMPropuestaDeKit, user: User) -> None:
    from app.services.notifications import notify_role, notify_user
    titulo = f"Kit de alta para {user.full_name}"
    cuerpo = "Revisa y confirma con un clic las licencias y el equipo que le corresponden."
    url = f"/alm/altas-y-bajas?tab=kits_propuestos&propuesta={p.id}"
    if p.responsable_id:
        notify_user(db, p.responsable_id, "alm_onboarding", titulo, cuerpo, "alm_kit_propuesta", p.id, url)
        return
    for rol in c.roles_de_respaldo(db, p.organization_id):
        notify_role(db, rol, "alm_onboarding", titulo, cuerpo, "alm_kit_propuesta", p.id, url,
                    organization_id=p.organization_id)


def puede_decidir(db: Session, p: ALMPropuestaDeKit, actor) -> bool:
    if getattr(actor, "is_superadmin", False):
        return True
    rol = getattr(getattr(actor, "role", None), "value", getattr(actor, "role", None))
    return actor.id == p.responsable_id or rol == "admin" or rol in c.roles_de_respaldo(db, p.organization_id)


def _propuesta(db: Session, propuesta_id: str) -> ALMPropuestaDeKit:
    p = db.get(ALMPropuestaDeKit, propuesta_id)
    c.exigir(p is not None, "almint_propuesta_no_encontrada", 404)
    return p


def confirmar(db: Session, propuesta_id: str, actor, claves: Optional[list[str]] = None) -> dict:
    """El clic del responsable: reserva lo disponible y pide compra de lo que falte.

    ``claves``: los elementos que se confirman (por defecto, todos).
    """
    p = _propuesta(db, propuesta_id)
    c.exigir(p.estado == "pendiente", "almint_propuesta_ya_decidida", 409)
    c.exigir(puede_decidir(db, p, actor), "almint_sin_permiso", 403)
    user = db.get(User, p.user_id)
    c.exigir(user is not None and user.is_active, "almint_persona_inactiva", 409)
    elegidos = set(claves) if claves else None
    resultado = []
    for el in c.json_o(p.elementos, []):
        if elegidos is not None and el["clave"] not in elegidos:
            resultado.append({**el, "resultado": "omitido"})
            continue
        if el["tipo"] == "licencia":
            r = s.dar_licencia(db, actor=actor, user_id=user.id, license_id=el["license_id"],
                               org_id=p.organization_id, source="onboarding", reason="Kit de alta")
            resultado.append({**el, **r})
        else:
            for _ in range(int(el.get("cantidad") or 1)):
                r = s.dar_equipo(db, actor=actor, user_id=user.id, asset_type=el["asset_type"],
                                 org_id=p.organization_id, source="onboarding", reason="Kit de alta")
                resultado.append({**el, **r})
    p.estado = "confirmada"
    p.resultado = json.dumps(resultado, default=str)
    p.decidida_por = actor.id
    p.decidida_en = timeutil.utcnow()
    from app.services.audit import audit_log
    audit_log(db, actor, "APPROVE", "alm_kit_propuesta", p.id, user.full_name, new_values={"resultado": resultado})
    db.commit()
    return serializar_propuesta(db, p)


def descartar(db: Session, propuesta_id: str, actor, motivo: Optional[str] = None) -> dict:
    p = _propuesta(db, propuesta_id)
    c.exigir(p.estado == "pendiente", "almint_propuesta_ya_decidida", 409)
    c.exigir(puede_decidir(db, p, actor), "almint_sin_permiso", 403)
    p.estado = "descartada"
    p.resultado = json.dumps({"motivo": motivo}) if motivo else None
    p.decidida_por = actor.id
    p.decidida_en = timeutil.utcnow()
    from app.services.audit import audit_log
    audit_log(db, actor, "REJECT", "alm_kit_propuesta", p.id, new_values={"motivo": motivo})
    db.commit()
    return serializar_propuesta(db, p)


def proponer_confirmado(db: Session, user_id: str, actor) -> Optional[dict]:
    """Acción manual «proponer kit» (p. ej. tras cambiar de puesto)."""
    user = db.query(User).filter(User.id == user_id).first()
    c.exigir(user is not None, "almint_persona_no_encontrada", 404)
    p = proponer(db, user, actor, forzar=True)
    db.commit()
    return serializar_propuesta(db, p) if p else None


def listar_propuestas(db: Session, actor, estado: Optional[str] = None) -> list[dict]:
    q = db.query(ALMPropuestaDeKit)
    if estado:
        q = q.filter(ALMPropuestaDeKit.estado == estado)
    filas = q.order_by(ALMPropuestaDeKit.created_at.desc()).all()
    return [serializar_propuesta(db, p, actor) for p in filas]


def serializar_propuesta(db: Session, p: ALMPropuestaDeKit, actor=None) -> dict:
    user = db.get(User, p.user_id)
    responsable = db.get(User, p.responsable_id) if p.responsable_id else None
    elementos = c.json_o(p.elementos, [])
    if p.estado == "pendiente":
        elementos = [{**e, **s.disponibilidad(db, license_id=e.get("license_id"), asset_type=e.get("asset_type"))}
                     for e in elementos]
    kits = [db.get(ALMKit, k) for k in c.json_o(p.kits, [])]
    return {
        "id": p.id, "user_id": p.user_id, "user_name": user.full_name if user else None,
        "user_job_title": user.job_title if user else None, "user_department": user.department if user else None,
        "responsable_id": p.responsable_id, "responsable_name": responsable.full_name if responsable else None,
        "estado": p.estado, "kits": [{"id": k.id, "nombre": k.nombre} for k in kits if k is not None],
        "elementos": elementos, "resultado": c.json_o(p.resultado, None),
        "puedo_decidir": puede_decidir(db, p, actor) if actor is not None else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "decidida_en": p.decidida_en.isoformat() if p.decidida_en else None,
    }
