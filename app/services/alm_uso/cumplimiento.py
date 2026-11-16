"""Cumplimiento real: posición efectiva de licencias por producto (derechos frente a consumo).

Derechos: los puestos de la licencia en ALM (`total_seats`) y, si una fuente
los da (p. ej. `subscribedSkus` de Microsoft 365), lo comprado según el
fabricante, para ver discrepancias.

Consumo, según la métrica de la licencia (`ALMLicense.metric`, fase 1):

- `named_user`: lo mayor entre los asientos asignados en ALM
  (`alm_asignaciones.asientos_usados`) y las personas distintas a las que la
  fuente da el producto o que lo usan (vistas en la última lectura): una
  persona que lo usa sin asignación en ALM también consume.
- `device` y `volume`: equipos distintos con el software (instalaciones activas
  de ALM más evidencias de inventario vistas).
- `concurrent`: el pico medido en su ventana (`concurrent_peak`).
- `site`: sin límite de puestos; solo se informa.

Posición = derechos − consumo. `deficit` (< 0): riesgo en una auditoría del
fabricante; `excedente` (> 0): puestos pagados sin usar (coste ocioso =
excedente × coste unitario); `conforme` (= 0); `sin_limite` (sitio, o sin
puestos declarados). Además: licencia caducada que se sigue usando, y
discrepancia entre los puestos de ALM y lo comprado según la fuente.

`exportar` da la misma tabla en CSV o XLSX para el auditor.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.models.alm import ALMLicense, ALMSoftwareInstall
from app.models.alm_uso import ALMUsoDerecho, ALMUsoEvidencia
from app.services.alm_uso._comun import (
    TITULAR_DISPOSITIVO, TITULAR_PERSONA, coste_unitario_anual, exigir_org, moneda_de_licencia,
)
from app.services.alm_uso.conciliacion import PRODUCTO_EQUIPO


def _consumo(db: Session, org: str, lic: ALMLicense, evs: list) -> dict:
    from app.services.alm_asignaciones import asientos_usados
    asignados = asientos_usados(db, lic)
    personas = {e.user_id or e.titular_externo for e in evs if e.titular_tipo == TITULAR_PERSONA
                and e.vista_en_ultima_lectura and (e.asignada_en_fuente or e.ultimo_uso_at is not None)}
    equipos = {e.asset_id or e.titular_externo for e in evs if e.titular_tipo == TITULAR_DISPOSITIVO
               and e.producto != PRODUCTO_EQUIPO and e.vista_en_ultima_lectura}
    equipos |= {a for (a,) in db.query(ALMSoftwareInstall.asset_id).filter(
        ALMSoftwareInstall.organization_id == org, ALMSoftwareInstall.license_id == lic.id,
        ALMSoftwareInstall.is_active.is_(True))}
    m = lic.metric or "named_user"
    if m in ("device", "volume"):
        consumo, base = len(equipos), "equipos"
    elif m == "concurrent":
        consumo, base = int(lic.concurrent_peak or 0), "pico"
    elif m == "site":
        consumo, base = max(asignados, len(personas)), "informativo"
    else:
        consumo, base = max(asignados, len(personas)), ("fuente" if len(personas) > asignados else "asignaciones")
    return {"consumo": consumo, "base_del_consumo": base, "asignados": asignados, "personas_en_fuente": len(personas),
            "equipos": len(equipos), "pico": lic.concurrent_peak}


def posicion(db: Session, organization_id: str) -> dict:
    org = exigir_org(organization_id)
    hoy = timeutil.today()
    licencias = db.query(ALMLicense).filter(ALMLicense.organization_id == org, ALMLicense.is_active.is_(True)) \
        .order_by(ALMLicense.product_name, ALMLicense.name).all()
    evs: dict = {}
    for e in db.query(ALMUsoEvidencia).filter(ALMUsoEvidencia.organization_id == org,
                                              ALMUsoEvidencia.license_id.isnot(None)):
        evs.setdefault(e.license_id, []).append(e)
    derechos: dict = {}
    for d in db.query(ALMUsoDerecho).filter(ALMUsoDerecho.organization_id == org, ALMUsoDerecho.license_id.isnot(None)):
        derechos.setdefault(d.license_id, []).append(d)
    filas = []
    for lic in licencias:
        c = _consumo(db, org, lic, evs.get(lic.id, []))
        ds = derechos.get(lic.id, [])
        comprados_fuente = sum(d.comprados or 0 for d in ds) if ds else None
        m = lic.metric or "named_user"
        limite = None if m == "site" else lic.total_seats
        if limite is None:
            estado, pos = "sin_limite", None
        else:
            pos = int(limite) - c["consumo"]
            estado = "deficit" if pos < 0 else ("excedente" if pos > 0 else "conforme")
        unit = coste_unitario_anual(lic)
        incidencias = []
        if lic.expiry_date and lic.expiry_date < hoy and c["consumo"] > 0:
            incidencias.append("caducada_en_uso")
        if comprados_fuente is not None and limite is not None and comprados_fuente != limite:
            incidencias.append("discrepancia_con_fuente")
        if m == "concurrent" and lic.concurrent_peak is None:
            incidencias.append("sin_pico_medido")
        filas.append({
            "license_id": lic.id, "nombre": lic.name, "producto": lic.product_name, "edicion": lic.edition,
            "sku": lic.sku, "metrica": m, "tipo": getattr(lic.type, "value", lic.type),
            "derechos": limite, "comprados_segun_fuente": comprados_fuente,
            "fuentes": sorted({d.fuente for d in ds} | {e.fuente for e in evs.get(lic.id, [])}),
            **c, "posicion": pos, "estado": estado,
            "coste_unitario_anual": unit, "moneda": moneda_de_licencia(db, lic, org),
            "exposicion": round(-pos * unit, 2) if (pos is not None and pos < 0 and unit) else None,
            "coste_ocioso": round(pos * unit, 2) if (pos is not None and pos > 0 and unit) else None,
            "caduca": lic.expiry_date.isoformat() if lic.expiry_date else None,
            "requiere_cumplimiento": bool(lic.is_compliance_req), "incidencias": incidencias})
    return {
        "items": filas,
        "kpis": {"licencias": len(filas), "deficit": sum(1 for f in filas if f["estado"] == "deficit"),
                 "excedente": sum(1 for f in filas if f["estado"] == "excedente"),
                 "conforme": sum(1 for f in filas if f["estado"] == "conforme"),
                 "con_incidencias": sum(1 for f in filas if f["incidencias"]),
                 "exposicion": round(sum(f["exposicion"] or 0 for f in filas), 2),
                 "coste_ocioso": round(sum(f["coste_ocioso"] or 0 for f in filas), 2)},
    }


CABECERA = ("Licencia", "Producto", "Edición", "SKU", "Métrica", "Derechos (ALM)", "Comprados según fuente",
            "Consumo", "Base del consumo", "Asignados", "Personas en fuente", "Equipos", "Pico", "Posición", "Estado",
            "Coste unitario anual", "Moneda", "Exposición", "Coste ocioso", "Caduca", "Fuentes", "Incidencias")


def exportar(db: Session, organization_id: str, formato: str = "csv", producto: Optional[str] = None):
    """La posición para la auditoría del fabricante (`producto`: filtra por nombre de producto o proveedor)."""
    from app.services.exportador_tabular import respuesta_tabular
    filas = posicion(db, organization_id)["items"]
    if producto:
        p = producto.strip().lower()
        filas = [f for f in filas if p in (f["producto"] or "").lower() or p in (f["nombre"] or "").lower()]
    return respuesta_tabular(formato, nombre=f"posicion_de_licencias_{timeutil.today().isoformat()}", cabecera=CABECERA,
                             filas=[(f["nombre"], f["producto"], f["edicion"], f["sku"], f["metrica"], f["derechos"],
                                     f["comprados_segun_fuente"], f["consumo"], f["base_del_consumo"], f["asignados"],
                                     f["personas_en_fuente"], f["equipos"], f["pico"], f["posicion"], f["estado"],
                                     f["coste_unitario_anual"], f["moneda"], f["exposicion"], f["coste_ocioso"],
                                     f["caduca"], ", ".join(f["fuentes"]), ", ".join(f["incidencias"]))
                                    for f in filas])
