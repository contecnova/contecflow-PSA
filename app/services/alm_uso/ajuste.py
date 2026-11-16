"""Ajuste de nivel (right-sizing): quien no usa lo que paga de más, a la licencia inferior.

Una regla (`ALMUsoNivel`) dice: licencia superior → inferior, y los SERVICIOS
que justifican la superior (claves de servicio de las evidencias: `exchange`,
`onedrive`, `sharepoint`, `teams`, `apps_escritorio`, `gmail`, `drive`, `sso`…).
Para cada asignación vigente de la superior con evidencias de la fuente, si en
los últimos `ALM_RIGHTSIZING_WINDOW_DAYS` días no usó NINGUNO de esos
servicios, se propone bajarla, con el ahorro estimado (coste unitario anual de
la superior − el de la inferior).

Ejemplo con Microsoft 365: E3 → E1 si no usa `apps_escritorio` (E1 no incluye
las aplicaciones de escritorio y el informe `getM365AppUserDetail` lo mide).
E5 → E3 depende de servicios (telefonía, Power BI, seguridad avanzada) que los
informes de uso no miden: la regla solo puede apoyarse en lo que la fuente da.

Sugerencias de reglas: los pares del mismo producto con `tier_rank` (fase 1)
distinto; la persona elige los servicios.

Sin evidencias no hay propuesta (nunca se baja a ciegas); una asignación sin
uso no se propone aquí: es de Recuperación.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.alm import ALMLicense
from app.models.alm import ALMLicenseAssignment as Asignacion
from app.models.alm_uso import ALMUsoAjusteDecision, ALMUsoNivel
from app.services.alm_uso._comun import (
    ahora, ajuste_int, cargar_json, coste_unitario_anual, exigir_org, moneda_de_licencia, volcar_json,
)


def _lic(db: Session, org: str, lid: str) -> ALMLicense:
    lic = db.query(ALMLicense).filter(ALMLicense.id == lid, ALMLicense.organization_id == org,
                                      ALMLicense.is_active.is_(True)).first()
    if lic is None:
        raise ErrorDeDominio(404, {"code": "ALM_USAGE_LICENSE_NOT_FOUND", "message": "Licencia no encontrada"})
    return lic


def regla_dict(db: Session, n: ALMUsoNivel) -> dict:
    sup = db.query(ALMLicense).filter(ALMLicense.id == n.license_superior_id).first()
    inf = db.query(ALMLicense).filter(ALMLicense.id == n.license_inferior_id).first()
    return {"id": n.id, "license_superior_id": n.license_superior_id, "superior": sup.name if sup else None,
            "license_inferior_id": n.license_inferior_id, "inferior": inf.name if inf else None,
            "servicios": cargar_json(n.servicios, []), "activa": n.activa, "notas": n.notas}


def reglas(db: Session, org: str) -> list[dict]:
    exigir_org(org)
    return [regla_dict(db, n) for n in db.query(ALMUsoNivel).filter(ALMUsoNivel.organization_id == org).all()]


def guardar_regla(db: Session, usuario, datos: dict, regla_id: Optional[str] = None) -> dict:
    from app.services.audit import audit_log
    org = exigir_org(getattr(usuario, "organization_id", None))
    servicios = [str(s).strip() for s in (datos.get("servicios") or []) if str(s).strip()]
    if not servicios:
        raise ErrorDeDominio(422, {"code": "ALM_USAGE_SERVICES_REQUIRED",
                                   "message": "Indica qué servicios justifican la licencia superior"})
    sup, inf = datos.get("license_superior_id"), datos.get("license_inferior_id")
    if not sup or not inf or sup == inf:
        raise ErrorDeDominio(422, {"code": "ALM_USAGE_TIERS_REQUIRED", "message": "Elige dos licencias distintas"})
    _lic(db, org, sup)
    _lic(db, org, inf)
    if regla_id:
        n = db.query(ALMUsoNivel).filter(ALMUsoNivel.id == regla_id, ALMUsoNivel.organization_id == org).first()
        if n is None:
            raise ErrorDeDominio(404, {"code": "ALM_USAGE_RULE_NOT_FOUND", "message": "Regla no encontrada"})
    else:
        if db.query(ALMUsoNivel.id).filter(ALMUsoNivel.organization_id == org, ALMUsoNivel.license_superior_id == sup,
                                           ALMUsoNivel.license_inferior_id == inf).first():
            raise ErrorDeDominio(409, {"code": "ALM_USAGE_RULE_EXISTS", "message": "Esa regla ya existe"})
        n = ALMUsoNivel(organization_id=org, created_by=usuario.id)
        db.add(n)
    n.license_superior_id, n.license_inferior_id = sup, inf
    n.servicios = volcar_json(servicios)
    n.activa = bool(datos.get("activa", True))
    n.notas = (datos.get("notas") or None) and str(datos["notas"])[:500]
    db.flush()
    audit_log(db, usuario, "UPDATE" if regla_id else "CREATE", "alm_uso_nivel", n.id, None,
              new_values={"superior": sup, "inferior": inf, "servicios": servicios, "activa": n.activa})
    db.commit()
    return regla_dict(db, n)


def borrar_regla(db: Session, usuario, regla_id: str) -> None:
    from app.services.audit import audit_log
    org = exigir_org(getattr(usuario, "organization_id", None))
    n = db.query(ALMUsoNivel).filter(ALMUsoNivel.id == regla_id, ALMUsoNivel.organization_id == org).first()
    if n is None:
        raise ErrorDeDominio(404, {"code": "ALM_USAGE_RULE_NOT_FOUND", "message": "Regla no encontrada"})
    audit_log(db, usuario, "DELETE", "alm_uso_nivel", n.id, None, old_values=regla_dict(db, n))
    db.delete(n)
    db.commit()


def sugerencias(db: Session, org: str) -> list[dict]:
    """Pares (superior, inferior) del mismo producto por `tier_rank` que aún no tienen regla."""
    exigir_org(org)
    existentes = {(n.license_superior_id, n.license_inferior_id)
                  for n in db.query(ALMUsoNivel).filter(ALMUsoNivel.organization_id == org)}
    por_producto: dict = {}
    for lic in db.query(ALMLicense).filter(ALMLicense.organization_id == org, ALMLicense.is_active.is_(True),
                                           ALMLicense.tier_rank.isnot(None), ALMLicense.product_name.isnot(None)):
        por_producto.setdefault(lic.product_name.strip().lower(), []).append(lic)
    salida = []
    for lics in por_producto.values():
        lics.sort(key=lambda l: l.tier_rank, reverse=True)
        for i, sup in enumerate(lics):
            for inf in lics[i + 1:]:
                if inf.tier_rank < sup.tier_rank and (sup.id, inf.id) not in existentes:
                    salida.append({"license_superior_id": sup.id, "superior": sup.name, "tier_superior": sup.tier,
                                   "license_inferior_id": inf.id, "inferior": inf.name, "tier_inferior": inf.tier})
    return salida


def _servicios_usados(fila: dict, desde: datetime) -> set:
    salida = set()
    for k, v in (fila.get("servicios") or {}).items():
        try:
            if v and datetime.fromisoformat(str(v).replace("Z", "+00:00")) >= desde:
                salida.add(k)
        except ValueError:
            continue
    return salida


def propuestas(db: Session, org: str) -> dict:
    from app.services.alm_uso.estado import Lector
    exigir_org(org)
    ventana = ajuste_int(db, "ALM_RIGHTSIZING_WINDOW_DAYS", org, minimo=1)
    desde = ahora() - timedelta(days=ventana)
    decididas = {(d.nivel_id, d.assignment_id) for d in db.query(ALMUsoAjusteDecision).filter(
        ALMUsoAjusteDecision.organization_id == org)}
    salida, ahorro = [], 0.0
    for n in db.query(ALMUsoNivel).filter(ALMUsoNivel.organization_id == org, ALMUsoNivel.activa.is_(True)).all():
        sup = db.query(ALMLicense).filter(ALMLicense.id == n.license_superior_id, ALMLicense.organization_id == org).first()
        inf = db.query(ALMLicense).filter(ALMLicense.id == n.license_inferior_id, ALMLicense.organization_id == org).first()
        if sup is None or inf is None:
            continue
        justifican = set(cargar_json(n.servicios, []))
        lector = Lector(db, org, [sup.id])
        cu_sup, cu_inf = coste_unitario_anual(sup), coste_unitario_anual(inf)
        unitario = round(cu_sup - cu_inf, 2) if (cu_sup is not None and cu_inf is not None) else None
        for a in db.query(Asignacion).filter(Asignacion.organization_id == org, Asignacion.license_id == sup.id,
                                             Asignacion.status == "active",
                                             Asignacion.holder_type.in_(("user", "asset"))).all():
            if (n.id, a.id) in decididas:
                continue
            fila = lector.de_asignacion(a)
            if fila["estado"] in ("sin_datos", "sin_uso") or fila["datos_desactualizados"]:
                continue
            usados = _servicios_usados(fila, desde)
            if usados & justifican:
                continue
            ahorro += unitario or 0
            salida.append({"nivel_id": n.id, "assignment_id": a.id, "user_id": a.holder_user_id,
                           "asset_id": a.holder_asset_id, "license_superior_id": sup.id, "superior": sup.name,
                           "license_inferior_id": inf.id, "inferior": inf.name,
                           "servicios_que_justifican": sorted(justifican), "servicios_usados": sorted(usados),
                           "ultimo_uso": fila["ultimo_uso"], "fuente": fila["fuente"], "fiabilidad": fila["fiabilidad"],
                           "ahorro_anual": unitario, "moneda": moneda_de_licencia(db, sup, org)})
    from app.services.alm_uso._comun import con_nombres
    return {"items": con_nombres(db, org, salida, license_key="license_superior_id"),
            "ahorro_anual_total": round(ahorro, 2), "ventana_dias": ventana}


def decidir(db: Session, usuario, nivel_id: str, assignment_id: str, aceptar: bool,
            motivo: Optional[str] = None) -> dict:
    """Aceptar: cierra la asignación superior y asigna la inferior al mismo titular. Descartar: no vuelve a proponerse."""
    from app.services import alm_asignaciones
    from app.services.audit import audit_log
    org = exigir_org(getattr(usuario, "organization_id", None))
    actual = {(p["nivel_id"], p["assignment_id"]): p for p in propuestas(db, org)["items"]}
    p = actual.get((nivel_id, assignment_id))
    if p is None:
        raise ErrorDeDominio(409, {"code": "ALM_USAGE_PROPOSAL_GONE",
                                   "message": "La propuesta ya no es válida (cambió el uso o ya se decidió)"})
    a = db.query(Asignacion).filter(Asignacion.id == assignment_id, Asignacion.organization_id == org).one()
    nueva_id = None
    if aceptar:
        titular = a.holder_user_id if a.holder_type == "user" else a.holder_asset_id
        nueva = alm_asignaciones.asignar(
            db, actor=usuario, holder_type=a.holder_type, holder_id=titular, license_id=p["license_inferior_id"],
            reason=f"Ajuste de nivel desde {p['superior']}", source="usage", require_approval=False, commit=False)
        alm_asignaciones.liberar(db, a.id, actor=usuario, motivo=f"Ajuste de nivel a {p['inferior']}",
                                 tipo="transferred", origen="usage", commit=False)
        nueva_id = nueva.id
    d = ALMUsoAjusteDecision(organization_id=org, nivel_id=nivel_id, assignment_id=assignment_id,
                             decision="aceptada" if aceptar else "descartada", nueva_asignacion_id=nueva_id,
                             ahorro_estimado=p["ahorro_anual"] if aceptar else None,
                             motivo=(motivo or None) and motivo[:500], decidido_por=usuario.id)
    db.add(d)
    audit_log(db, usuario, "UPDATE", "alm_uso_ajuste", assignment_id, p["superior"],
              new_values={"decision": d.decision, "inferior": p["inferior"], "nueva_asignacion": nueva_id,
                          "ahorro_anual": d.ahorro_estimado})
    db.commit()
    return {"decision": d.decision, "nueva_asignacion_id": nueva_id, "ahorro_anual": d.ahorro_estimado}


def ahorro_logrado(db: Session, org: str) -> float:
    return round(sum(d.ahorro_estimado or 0 for d in db.query(ALMUsoAjusteDecision).filter(
        ALMUsoAjusteDecision.organization_id == org, ALMUsoAjusteDecision.decision == "aceptada")), 2)
