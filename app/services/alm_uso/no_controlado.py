"""Software no controlado: lo que se usa, se paga o está instalado y no está en ALM.

Orígenes:
- `gasto`: gastos de la categoría `software` de los últimos
  `ALM_UNMANAGED_LOOKBACK_DAYS` días (no rechazados) cuya descripción no nombra
  ninguna licencia ni proveedor de ALM. Se agrupan por la descripción sin las
  palabras de trámite (licencia, suscripción, anual…), importe en la moneda de
  la empresa al tipo de cambio de la fecha de cada gasto.
- Cada fuente de uso: productos/SKU con titulares sin licencia de ALM (M365,
  Google, Okta…), aplicaciones vistas por SSO o autorizadas con la cuenta
  (Okta, Google, proveedor de identidad de contecflow) y software de los equipos
  (Intune, Jamf, agente) que no corresponde a ninguna licencia.

Un candidato con al menos `ALM_UNMANAGED_MIN_OCCURRENCES` apariciones (gastos,
personas o equipos) se propone. «Dar de alta» crea la licencia con la
propuesta (nombre, métrica, puestos, coste anual) y deja mapeados sus productos
de origen; «Descartar» los marca como ignorados para que no vuelvan.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.models.alm_uso import ALMSoftwareNoControlado, ALMUsoEvidencia, ALMUsoMapeo
from app.services.alm_uso._comun import (
    ajuste_int, cargar_json, exigir_org, moneda_de_empresa, normalizar, volcar_json,
)

#: Palabras de trámite que se quitan de la descripción de un gasto para quedarse
#: con el nombre del producto. Vocabulario (es/en), no un umbral.
PALABRAS_DE_TRAMITE = frozenset("""
licencia licencias suscripcion suscripciones renovacion renovaciones cuota cuotas pago pagos factura plan planes
anual anuales mensual mensuales trimestral ano mes meses usuario usuarios puesto puestos de del la el para por con
y en a software app aplicacion herramienta servicio servicios
license licenses licence subscription subscriptions renewal fee payment invoice annual monthly yearly year month
user users seat seats for the of and to tool service pro plus
enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre
january february march april may june july august september october november december
""".split())
_MAX_REFERENCIAS = 20


def clave_de_gasto(descripcion: str) -> str:
    palabras = [p for p in normalizar(descripcion).split() if p not in PALABRAS_DE_TRAMITE and not p.isdigit()]
    return " ".join(palabras[:4])


def _nombres_de_alm(db: Session, org: str) -> list[str]:
    from app.models.alm import ALMLicense, ALMVendor
    nombres = set()
    for n, p in db.query(ALMLicense.name, ALMLicense.product_name).filter(ALMLicense.organization_id == org,
                                                                          ALMLicense.is_active.is_(True)):
        nombres |= {normalizar(n), normalizar(p)}
    for (v,) in db.query(ALMVendor.name).filter(ALMVendor.organization_id == org, ALMVendor.is_active.is_(True)):
        nombres.add(normalizar(v))
    return [n for n in nombres if len(n) >= 3]


def _ignorados(db: Session, org: str) -> set:
    return {(m.fuente, m.producto) for m in db.query(ALMUsoMapeo).filter(ALMUsoMapeo.organization_id == org,
                                                                        ALMUsoMapeo.ignorar.is_(True))}


def _candidato(db: Session, org: str, clave: str, nombre: str) -> ALMSoftwareNoControlado:
    c = db.query(ALMSoftwareNoControlado).filter(ALMSoftwareNoControlado.organization_id == org,
                                                 ALMSoftwareNoControlado.clave == clave).first()
    if c is None:
        c = ALMSoftwareNoControlado(organization_id=org, clave=clave, nombre=nombre[:255], estado="nuevo",
                                    usuarios=0, dispositivos=0)
        db.add(c)
    return c


def _anotar(c: ALMSoftwareNoControlado, origen: str, *, usuarios: int = 0, dispositivos: int = 0,
            apariciones: int = 0, productos: Optional[list] = None, ejemplos: Optional[list] = None) -> None:
    """Cada lectura es una foto completa del origen: se sustituye lo de ese origen."""
    hoy = timeutil.today()
    origenes = cargar_json(c.origenes, {}) or {}
    origenes[origen] = {"usuarios": usuarios, "dispositivos": dispositivos, "apariciones": apariciones}
    c.origenes = volcar_json(origenes)
    c.usuarios = max(int(o.get("usuarios") or 0) for o in origenes.values())
    c.dispositivos = max(int(o.get("dispositivos") or 0) for o in origenes.values())
    refs = cargar_json(c.referencias, {}) or {}
    if productos:
        previos = [p for p in refs.get("productos") or [] if p.get("fuente") != origen]
        refs["productos"] = previos + productos[:_MAX_REFERENCIAS]
    if ejemplos:
        refs.setdefault("ejemplos", {})[origen] = ejemplos[:_MAX_REFERENCIAS]
    c.referencias = volcar_json(refs)
    c.primera_vez = c.primera_vez or hoy
    c.ultima_vez = hoy


def registrar_de_lectura(db: Session, org: str, fuente: str, idx, r, apps_sin_licencia: list) -> int:
    """Candidatos de una lectura de una fuente de uso (productos, aplicaciones y software sin licencia)."""
    if fuente == "contecflow":
        return 0   # la propia plataforma no es software «no controlado»
    ignorados = _ignorados(db, org)
    grupos: dict = {}

    def sumar(nombre, producto, usuario=None, equipo=None):
        clave = normalizar(nombre)
        # Ya está en ALM con ese nombre (aunque el mapeo sea ambiguo): no es «no controlado».
        if not clave or (fuente, producto) in ignorados or clave in idx.por_nombre:
            return
        g = grupos.setdefault(clave, {"nombre": nombre, "usuarios": set(), "equipos": set(), "productos": set()})
        if usuario:
            g["usuarios"].add(usuario)
        if equipo:
            g["equipos"].add(equipo)
        g["productos"].add(producto)

    for ev in r.evidencias:
        lic, ignorado = idx.licencia(ev.producto, ev.nombre_producto, ev.sku)
        if lic is None and not ignorado and (ev.asignada or ev.ultimo_uso):
            sumar(ev.nombre_producto or ev.producto, ev.producto, usuario=ev.titular)
    for a in r.aplicaciones:
        lic, ignorado = idx.licencia(a.nombre, a.nombre, None)
        if lic is None and not ignorado and normalizar(a.nombre) not in idx.por_nombre:
            g = grupos.setdefault(normalizar(a.nombre), {"nombre": a.nombre, "usuarios": set(), "equipos": set(),
                                                         "productos": set()})
            g["productos"].add(a.nombre)
            g["n_usuarios"] = max(g.get("n_usuarios", 0), a.usuarios)
    for nombre, equipo, usuario in apps_sin_licencia:
        sumar(nombre, normalizar(nombre)[:255], usuario=None, equipo=equipo)

    if not grupos:
        return 0
    from app.models.alm_uso import ALMSoftwareNoControlado as M
    existentes = {c.clave: c for c in db.query(M).filter(M.organization_id == org, M.clave.in_(list(grupos)))}
    for clave, g in grupos.items():
        c = existentes.get(clave) or _candidato(db, org, clave[:255], g["nombre"])
        if c.estado == "dado_de_alta":
            continue
        _anotar(c, fuente, usuarios=max(len(g["usuarios"]), g.get("n_usuarios", 0)), dispositivos=len(g["equipos"]),
                apariciones=max(len(g["usuarios"]), len(g["equipos"]), g.get("n_usuarios", 0)),
                productos=[{"fuente": fuente, "producto": p} for p in sorted(g["productos"])],
                ejemplos=sorted(g["equipos"])[:_MAX_REFERENCIAS] or sorted(g["usuarios"])[:_MAX_REFERENCIAS])
    return len(grupos)


def detectar_gastos(db: Session, org: str) -> int:
    """Candidatos de los gastos de software. Devuelve cuántos candidatos tocó."""
    from app.models.expenses import Expense, ExpenseCategory, ExpenseStatus
    from app.services.profitability_service import get_fx_rate
    exigir_org(org)
    dias = ajuste_int(db, "ALM_UNMANAGED_LOOKBACK_DAYS", org, minimo=1)
    desde = timeutil.today() - timedelta(days=dias)
    moneda = moneda_de_empresa(db, org)
    alm = _nombres_de_alm(db, org)
    ignorados = {p for f, p in _ignorados(db, org) if f == "gasto"}
    grupos: dict = {}
    cache: dict = {}
    for g in db.query(Expense).filter(Expense.organization_id == org, Expense.category == ExpenseCategory.software.value,
                                      Expense.expense_date >= desde, Expense.status != ExpenseStatus.rejected,
                                      Expense.is_active.is_(True)).all():
        texto = normalizar(g.description)
        if any(n in texto for n in alm):
            continue
        clave = clave_de_gasto(g.description)
        if not clave or clave in ignorados:
            continue
        de = (g.currency or moneda).upper()
        importe = float(g.amount or 0) * (get_fx_rate(db, de, moneda, g.expense_date, _cache=cache) if de != moneda else 1)
        d = grupos.setdefault(clave, {"nombre": g.description.strip()[:255], "n": 0, "importe": 0.0, "usuarios": set(),
                                      "ids": [], "primera": g.expense_date, "ultima": g.expense_date})
        d["n"] += 1
        d["importe"] += importe
        d["usuarios"].add(g.user_id)
        d["ids"].append(g.id)
        d["primera"] = min(d["primera"], g.expense_date)
        d["ultima"] = max(d["ultima"], g.expense_date)
    for clave, d in grupos.items():
        c = _candidato(db, org, clave[:255], d["nombre"])
        if c.estado == "dado_de_alta":
            continue
        _anotar(c, "gasto", usuarios=len(d["usuarios"]), apariciones=d["n"],
                productos=[{"fuente": "gasto", "producto": clave}], ejemplos=d["ids"])
        c.importe = round(d["importe"], 2)
        c.moneda = moneda
        c.primera_vez = min(c.primera_vez or d["primera"], d["primera"])
    return len(grupos)


def _apariciones(c: ALMSoftwareNoControlado) -> int:
    return max([int(o.get("apariciones") or 0) for o in (cargar_json(c.origenes, {}) or {}).values()] + [0])


def propuesta(c: ALMSoftwareNoControlado) -> dict:
    """Lo que se propone dar de alta (la pantalla lo deja editar antes de crear la licencia)."""
    metrica = "device" if c.dispositivos > c.usuarios else "named_user"
    return {"name": c.nombre, "product_name": c.nombre, "metric": metrica,
            "type": "subscription" if c.importe else "named",
            "total_seats": max(c.usuarios, c.dispositivos) or None,
            "annual_cost": c.importe, "notes": f"Alta desde software no controlado ({', '.join(sorted((cargar_json(c.origenes, {}) or {}).keys()))})"}


def candidato_dict(c: ALMSoftwareNoControlado) -> dict:
    return {"id": c.id, "nombre": c.nombre, "clave": c.clave, "origenes": cargar_json(c.origenes, {}),
            "usuarios": c.usuarios, "dispositivos": c.dispositivos, "apariciones": _apariciones(c),
            "importe": c.importe, "moneda": c.moneda,
            "primera_vez": c.primera_vez.isoformat() if c.primera_vez else None,
            "ultima_vez": c.ultima_vez.isoformat() if c.ultima_vez else None,
            "estado": c.estado, "license_id": c.license_id, "referencias": cargar_json(c.referencias, {}),
            "propuesta": propuesta(c)}


def listar(db: Session, org: str, estado: Optional[str] = "nuevo") -> dict:
    exigir_org(org)
    minimo = ajuste_int(db, "ALM_UNMANAGED_MIN_OCCURRENCES", org, minimo=1)
    q = db.query(ALMSoftwareNoControlado).filter(ALMSoftwareNoControlado.organization_id == org)
    if estado:
        q = q.filter(ALMSoftwareNoControlado.estado == estado)
    filas = [c for c in q.all() if estado != "nuevo" or _apariciones(c) >= minimo]
    filas.sort(key=lambda c: (-(c.importe or 0), -max(c.usuarios, c.dispositivos), c.nombre))
    return {"minimo": minimo, "items": [candidato_dict(c) for c in filas],
            "importe_total": round(sum(c.importe or 0 for c in filas), 2), "moneda": moneda_de_empresa(db, org)}


def _candidato_o_404(db: Session, org: str, cid: str) -> ALMSoftwareNoControlado:
    c = db.query(ALMSoftwareNoControlado).filter(ALMSoftwareNoControlado.id == cid,
                                                 ALMSoftwareNoControlado.organization_id == org).first()
    if c is None:
        raise ErrorDeDominio(404, {"code": "ALM_USAGE_CANDIDATE_NOT_FOUND", "message": "Candidato no encontrado"})
    return c


def _mapear_origenes(db: Session, org: str, c: ALMSoftwareNoControlado, usuario, *, license_id=None,
                     ignorar=False) -> None:
    for p in (cargar_json(c.referencias, {}) or {}).get("productos") or []:
        m = db.query(ALMUsoMapeo).filter(ALMUsoMapeo.organization_id == org, ALMUsoMapeo.fuente == p["fuente"],
                                         ALMUsoMapeo.producto == p["producto"]).first()
        if m is None:
            m = ALMUsoMapeo(organization_id=org, fuente=p["fuente"], producto=p["producto"][:255],
                            created_by=usuario.id)
            db.add(m)
        m.license_id, m.ignorar = license_id, ignorar


def dar_de_alta(db: Session, usuario, cid: str, datos: dict) -> dict:
    """Crea la licencia (con la propuesta, corregida por la persona) y mapea sus productos de origen."""
    from app.models.alm import ALMLicense
    from app.services.audit import audit_log
    org = exigir_org(getattr(usuario, "organization_id", None))
    c = _candidato_o_404(db, org, cid)
    if c.estado == "dado_de_alta":
        raise ErrorDeDominio(409, {"code": "ALM_USAGE_CANDIDATE_DONE", "message": "Ya se dio de alta"})
    p = {**propuesta(c), **{k: v for k, v in (datos or {}).items() if v not in (None, "")}}
    if not (p.get("name") or "").strip():
        raise ErrorDeDominio(422, {"code": "ALM_USAGE_NAME_REQUIRED", "message": "La licencia necesita nombre"})
    permitidos = {"name", "product_name", "metric", "type", "total_seats", "annual_cost", "notes", "vendor_id",
                  "edition", "sku", "cost_center_id", "expiry_date"}
    from app.services.alm_service import create_license_record
    creada = create_license_record({k: v for k, v in p.items() if k in permitidos}, db)
    lic = db.query(ALMLicense).filter(ALMLicense.id == creada["id"], ALMLicense.organization_id == org).one()
    c.estado, c.license_id, c.revisado_por, c.revisado_at = "dado_de_alta", lic.id, usuario.id, timeutil.utcnow()
    _mapear_origenes(db, org, c, usuario, license_id=lic.id)
    # Las evidencias ya guardadas de esos productos pasan a la licencia nueva.
    for prod in (cargar_json(c.referencias, {}) or {}).get("productos") or []:
        db.query(ALMUsoEvidencia).filter(ALMUsoEvidencia.organization_id == org,
                                         ALMUsoEvidencia.fuente == prod["fuente"],
                                         ALMUsoEvidencia.producto == prod["producto"]).update(
            {"license_id": lic.id}, synchronize_session=False)
    audit_log(db, usuario, "CREATE", "alm_software_no_controlado", c.id, c.nombre,
              new_values={"license_id": lic.id, "estado": c.estado})
    db.commit()
    return candidato_dict(c)


def descartar(db: Session, usuario, cid: str, motivo: Optional[str] = None) -> dict:
    from app.services.audit import audit_log
    org = exigir_org(getattr(usuario, "organization_id", None))
    c = _candidato_o_404(db, org, cid)
    c.estado, c.revisado_por, c.revisado_at = "descartado", usuario.id, timeutil.utcnow()
    _mapear_origenes(db, org, c, usuario, ignorar=True)
    audit_log(db, usuario, "UPDATE", "alm_software_no_controlado", c.id, c.nombre,
              new_values={"estado": "descartado", "motivo": motivo})
    db.commit()
    return candidato_dict(c)


def reabrir(db: Session, usuario, cid: str) -> dict:
    from app.services.audit import audit_log
    org = exigir_org(getattr(usuario, "organization_id", None))
    c = _candidato_o_404(db, org, cid)
    if c.estado != "descartado":
        raise ErrorDeDominio(409, {"code": "ALM_USAGE_CANDIDATE_NOT_DISCARDED", "message": "Solo se reabre un descartado"})
    c.estado = "nuevo"
    for p in (cargar_json(c.referencias, {}) or {}).get("productos") or []:
        db.query(ALMUsoMapeo).filter(ALMUsoMapeo.organization_id == org, ALMUsoMapeo.fuente == p["fuente"],
                                     ALMUsoMapeo.producto == p["producto"], ALMUsoMapeo.ignorar.is_(True)).delete(
            synchronize_session=False)
    audit_log(db, usuario, "UPDATE", "alm_software_no_controlado", c.id, c.nombre, new_values={"estado": "nuevo"})
    db.commit()
    return candidato_dict(c)


__all__ = ["registrar_de_lectura", "detectar_gastos", "listar", "dar_de_alta", "descartar", "reabrir"]


def detectar_ahora(db: Session, org: str) -> int:
    """«Volver a analizar» desde la pantalla: detecta y confirma."""
    n = detectar_gastos(db, org)
    db.commit()
    return n
