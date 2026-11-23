"""Fuentes de medicion de dispositivos y usuarios de un servicio gestionado (migracion 191).

Un servicio cobrado por dispositivo o usuario al mes (`device_month`,
`user_month`) necesita saber cuantos hay. Antes: el ultimo recuento registrado a
mano o importado o, sin el, las unidades contratadas. Ahora el servicio declara
su **fuente de medicion** (`supplier_services.metering_source`):

- `manual`: como antes (consumo registrado a mano o importado).
- `cmdb`: se cuenta en la CMDB (`sd_configuration_items`) con los filtros del
  servicio (`metering_config`): tipos y clases de elemento, entorno, fabricante,
  ubicacion, proyecto, visto en los ultimos N dias y, si se indica, solo los
  elementos con un producto de software instalado (`sw_instances` de la CMDB de
  software: p. ej. el agente EDR del SOC). Cuenta elementos (dispositivos) o
  propietarios distintos (usuarios). Se mide sola cada dia (trabajo
  `externos-caducidad`) y con el boton «Medir ahora». Solo LEE la CMDB.
- `external`: el recuento llega de otro sistema (SIEM, consola del proveedor,
  MDM…) por API (`POST /suppliers/services/{sid}/metering/ingest`, con un token
  de API de un gestor) o por importacion (`POST /suppliers/metering/import`).

Cada fuente cumple la interfaz `FuenteDeMedicion` (`validar`, `contar`) y se
registra en `FUENTES`; una fuente nueva (MDM, consola cloud) es una clase mas.

Cada muestra se acumula en UN consumo por servicio, mes y origen
(`supplier_usage_records`, `source` = `cmdb` | `api` | `import`) con su
detalle (`detail`: muestras, maximo, minimo, media, ultimo) y la cantidad del mes
segun la agregacion del servicio (`last`, `max`, `average`). La prevision lo usa
como cualquier recuento registrado (`consumo.medir`). Un mes ya cerrado en un
estado de cuenta no se toca.

RGPD: solo se guarda el numero. Si el sistema externo manda identificadores
(`items`: equipos, usuarios), se cuentan sin duplicados y se descartan; nunca se
guardan. Auditoria: cada muestra deja `audit_log` (`supplier_usage_records`) y
cada cambio de fuente, el de `supplier_services`.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import NamedTuple, Optional, Protocol

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.codigos_de_error import error
from app.services.audit import audit_log
from app.services.proveedores import serializar as ser
from app.services.proveedores.tipos import (
    METERING_AGGREGATIONS, METERING_COUNTS, METERING_SOURCES, UNIDADES_RECUENTO,
)

logger = logging.getLogger(__name__)

#: Muestras que se guardan en el detalle del consumo del mes (una al dia basta).
MAX_MUESTRAS = 62
#: Elementos de ejemplo que devuelve la vista previa (codigos de la CMDB, no datos personales).
MAX_EJEMPLOS = 10


class Recuento(NamedTuple):
    quantity: float
    detail: dict


class FuenteDeMedicion(Protocol):
    """Interfaz de una fuente de medicion."""

    clave: str
    #: Se mide sola (trabajo diario y «Medir ahora»). Las externas llegan por API o importacion.
    automatica: bool

    def validar(self, db: Session, config: dict) -> dict:
        """Normaliza la configuracion del servicio (422 si no vale)."""

    def contar(self, db: Session, servicio, config: dict, fecha: date) -> Recuento:
        """Cuantos dispositivos o usuarios hay hoy (solo las automaticas)."""


def _agregacion(config: dict) -> str:
    a = (config or {}).get("aggregation") or "last"
    if a not in METERING_AGGREGATIONS:
        raise error(422, "proveedor_medicion_agregacion_no_valida", agregacion=a)
    return a


def _lista(v) -> list[str]:
    if v is None or v == "":
        return []
    if isinstance(v, str):
        v = [x.strip() for x in v.split(",")]
    return [str(x).strip() for x in v if str(x).strip()]


class FuenteCMDB:
    """Recuento en la CMDB (`sd_configuration_items`), opcionalmente con software instalado."""

    clave = "cmdb"
    automatica = True

    def validar(self, db: Session, config: dict) -> dict:
        from app.models.service_desk._enums import CIType
        c = dict(config or {})
        tipos = _lista(c.get("ci_types"))
        validos = {t.value for t in CIType}
        malos = [t for t in tipos if t not in validos]
        if malos:
            raise error(422, "proveedor_medicion_filtro_no_valido", filtro="ci_types", valor=", ".join(malos))
        cuenta = c.get("count") or ("owners" if c.get("unit") == "user_month" else "devices")
        if cuenta not in METERING_COUNTS:
            raise error(422, "proveedor_medicion_filtro_no_valido", filtro="count", valor=cuenta)
        dias = c.get("seen_within_days")
        if dias not in (None, ""):
            try:
                dias = int(dias)
            except (TypeError, ValueError):
                raise error(422, "proveedor_medicion_filtro_no_valido", filtro="seen_within_days", valor=str(dias))
            if dias < 1 or dias > 3650:
                raise error(422, "proveedor_medicion_filtro_no_valido", filtro="seen_within_days", valor=str(dias))
        else:
            dias = None
        producto = (c.get("software_product_id") or "").strip() or None
        if producto:
            from app.models.cmdb_software import SoftwareProduct
            if not db.query(SoftwareProduct.id).filter(SoftwareProduct.id == producto).first():
                raise error(404, "no_encontrado", detail="Producto de software no encontrado", que="producto_de_software")
        proyecto = (c.get("project_id") or "").strip() or None
        if proyecto:
            from app.models.project import Project
            if not db.query(Project.id).filter(Project.id == proyecto).first():
                raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
        return {
            "ci_types": tipos, "ci_classes": _lista(c.get("ci_classes")),
            "environment": (c.get("environment") or "").strip() or None,
            "vendor": (c.get("vendor") or "").strip() or None,
            "location": (c.get("location") or "").strip() or None,
            "project_id": proyecto, "software_product_id": producto, "seen_within_days": dias,
            "count": cuenta, "aggregation": _agregacion(c),
        }

    def _consulta(self, db: Session, config: dict, fecha: date):
        from sqlalchemy import or_

        from app.models.service_desk._enums import CIStatus, CIType
        from app.models.service_desk.cmdb import ConfigurationItem as CI
        q = db.query(CI).filter(CI.is_active.isnot(False), or_(CI.status.is_(None), CI.status != CIStatus.retired))
        if config.get("ci_types"):
            q = q.filter(CI.ci_type.in_([CIType(t) for t in config["ci_types"]]))
        if config.get("ci_classes"):
            q = q.filter(CI.ci_class.in_(config["ci_classes"]))
        for campo in ("environment", "vendor", "location"):
            if config.get(campo):
                q = q.filter(getattr(CI, campo).ilike(config[campo]))
        if config.get("project_id"):
            q = q.filter(CI.project_id == config["project_id"])
        limite = None
        if config.get("seen_within_days"):
            limite = datetime.combine(fecha, datetime.min.time(), tzinfo=timezone.utc) - timedelta(
                days=int(config["seen_within_days"]))
        if config.get("software_product_id"):
            from app.models.cmdb_software import SoftwareInstance as SI
            sub = db.query(SI.ci_id).filter(SI.product_id == config["software_product_id"], SI.ci_id.isnot(None),
                                            SI.is_active.isnot(False), SI.status != "retired")
            if limite is not None:
                sub = sub.filter(or_(SI.last_seen_at.is_(None), SI.last_seen_at >= limite))
            q = q.filter(CI.id.in_(sub))
        elif limite is not None:
            q = q.filter(or_(CI.last_discovered_at.is_(None), CI.last_discovered_at >= limite))
        return q

    def contar(self, db: Session, servicio, config: dict, fecha: date) -> Recuento:
        from sqlalchemy import func

        from app.models.service_desk.cmdb import ConfigurationItem as CI
        q = self._consulta(db, config, fecha)
        if config.get("count") == "owners":
            n = q.filter(CI.owner_user_id.isnot(None)).with_entities(func.count(func.distinct(CI.owner_user_id))).scalar()
        else:
            n = q.with_entities(func.count(func.distinct(CI.id))).scalar()
        ejemplos = [c for (c,) in q.with_entities(CI.code).order_by(CI.code).limit(MAX_EJEMPLOS).all()]
        return Recuento(float(n or 0), {"source": "cmdb", "count": config.get("count"), "examples": ejemplos,
                                        "filters": {k: v for k, v in config.items() if v not in (None, [], "")}})


class FuenteExterna:
    """Recuento que manda otro sistema (SIEM, consola del proveedor, MDM) por API o importacion."""

    clave = "external"
    automatica = False

    def validar(self, db: Session, config: dict) -> dict:
        c = dict(config or {})
        sistema = (c.get("system") or "").strip()
        if not sistema:
            raise error(422, "campo_obligatorio", campo="metering_config.system")
        return {"system": sistema[:100], "aggregation": _agregacion(c)}

    def contar(self, db: Session, servicio, config: dict, fecha: date) -> Recuento:
        raise error(409, "proveedor_medicion_sin_fuente")


class FuenteManual:
    """Sin medicion automatica: consumo registrado a mano o importado (como antes)."""

    clave = "manual"
    automatica = False

    def validar(self, db: Session, config: dict) -> dict:
        return {}

    def contar(self, db: Session, servicio, config: dict, fecha: date) -> Recuento:
        raise error(409, "proveedor_medicion_sin_fuente")


FUENTES: dict[str, FuenteDeMedicion] = {"manual": FuenteManual(), "cmdb": FuenteCMDB(), "external": FuenteExterna()}
assert set(FUENTES) == set(METERING_SOURCES)


def fuente(clave: Optional[str]) -> FuenteDeMedicion:
    f = FUENTES.get(clave or "manual")
    if f is None:
        raise error(422, "proveedor_medicion_no_valida", fuente=clave)
    return f


def validar_servicio(db: Session, s) -> None:
    """Normaliza `metering_source` / `metering_config` del servicio (lo llama `servicios._validar`)."""
    clave = s.metering_source or "manual"
    f = fuente(clave)
    if clave != "manual" and s.unit not in UNIDADES_RECUENTO:
        raise error(422, "proveedor_medicion_sin_unidad")
    s.metering_source = clave
    s.metering_config = f.validar(db, {**(s.metering_config or {}), "unit": s.unit}) or None


# ── Registro de muestras ─────────────────────────────────────────────────────

def _linea_del_servicio(db: Session, s) -> Optional[str]:
    from app.models.proveedores import SupplierPricingLine
    if not s.contract_id:
        return None
    lineas = db.query(SupplierPricingLine.id).filter(SupplierPricingLine.contract_id == s.contract_id,
                                                     SupplierPricingLine.service_id == s.id,
                                                     SupplierPricingLine.unit == s.unit,
                                                     SupplierPricingLine.is_active.isnot(False)).all()
    return lineas[0][0] if len(lineas) == 1 else None


def _resumir(muestras: list, agregacion: str) -> tuple[float, dict]:
    valores = [float(m["quantity"]) for m in muestras]
    det = {"samples": muestras[-MAX_MUESTRAS:], "max": max(valores), "min": min(valores),
           "average": round(sum(valores) / len(valores), 4), "last": valores[-1],
           "last_date": muestras[-1]["date"], "aggregation": agregacion, "n_samples": len(valores)}
    cantidad = {"last": det["last"], "max": det["max"], "average": det["average"]}[agregacion]
    return round(cantidad, 4), det


def anotar(db: Session, s, cantidad: float, fecha: date, origen: str, sistema: Optional[str], actor,
           extra: Optional[dict] = None, commit: bool = True):
    """Suma una muestra al consumo del mes del servicio (uno por servicio, mes y origen).

    Devuelve el `SupplierUsageRecord`, o None si el mes ya esta cerrado en un estado de cuenta.
    """
    from app.models.proveedores import SupplierUsageRecord as U
    if s.unit not in UNIDADES_RECUENTO:
        raise error(422, "proveedor_medicion_sin_unidad")
    if cantidad is None or float(cantidad) < 0:
        raise error(422, "proveedor_medicion_cantidad_no_valida")
    mes = fecha.replace(day=1)
    registros = db.query(U).filter(U.service_id == s.id, U.unit == s.unit, U.source == origen,
                                   U.period_start == mes).order_by(U.created_at.desc()).all()
    if any(r.statement_id for r in registros):
        return None
    r = registros[0] if registros else None
    agregacion = _agregacion(s.metering_config or {})
    muestra = {"date": str(fecha), "quantity": float(cantidad)}
    previas = [m for m in ((r.detail or {}).get("samples") or []) if m.get("date") != str(fecha)] if r else []
    muestras = sorted(previas + [muestra], key=lambda m: m["date"])
    total, det = _resumir(muestras, agregacion)
    det.update({"system": sistema, **(extra or {})})
    nuevo = r is None
    if nuevo:
        r = U(subcontractor_id=s.subcontractor_id, contract_id=s.contract_id, service_id=s.id,
              pricing_line_id=_linea_del_servicio(db, s), period_start=mes, period_end=fecha, unit=s.unit,
              quantity=total, source=origen, source_system=(sistema or None) and sistema[:100],
              description=f"{s.name} · {origen}"[:500], created_by=getattr(actor, "id", None))
        db.add(r)
    else:
        r.period_end = max(r.period_end, fecha)
        r.quantity = total
        r.source_system = (sistema or r.source_system or None) and (sistema or r.source_system)[:100]
    r.detail = det
    s.metering_last_at = datetime.now(timezone.utc)
    s.metering_last_quantity = float(cantidad)
    s.metering_last_error = None
    db.flush()
    audit_log(db, actor, "CREATE" if nuevo else "UPDATE", "supplier_usage_records", r.id, s.name,
              new_values={"source": origen, "system": sistema, "date": str(fecha), "sample": float(cantidad),
                          "month_quantity": total, "aggregation": agregacion})
    if commit:
        db.commit()
        db.refresh(r)
    return r


# ── Medir (fuentes automaticas) ──────────────────────────────────────────────

def vista_previa(db: Session, clave: str, config: dict, unidad: Optional[str] = None) -> dict:
    """Cuantos contaria la fuente con esta configuracion hoy (sin guardar nada)."""
    f = fuente(clave)
    if not f.automatica:
        raise error(409, "proveedor_medicion_sin_fuente")
    cfg = f.validar(db, {**(config or {}), "unit": unidad})
    r = f.contar(db, None, cfg, timeutil.today())
    return {"quantity": r.quantity, "detail": r.detail}


def medir_servicio(db: Session, s, actor=None, fecha: Optional[date] = None) -> dict:
    """«Medir ahora»: cuenta con la fuente del servicio y anota la muestra del dia."""
    f = fuente(s.metering_source)
    if not f.automatica:
        raise error(409, "proveedor_medicion_sin_fuente")
    fecha = fecha or timeutil.today()
    try:
        r = f.contar(db, s, s.metering_config or {}, fecha)
    except Exception as exc:  # la CMDB fallo: queda anotado en el servicio
        db.rollback()
        s.metering_last_error = str(getattr(exc, "detail", exc))[:255]
        s.metering_last_at = datetime.now(timezone.utc)
        db.commit()
        raise
    u = anotar(db, s, r.quantity, fecha, f.clave if f.clave != "external" else "api", f.clave, actor,
               extra={"examples": r.detail.get("examples"), "count": r.detail.get("count")})
    if u is None:
        raise error(409, "proveedor_consumo_en_estado_de_cuenta")
    return {"service": ser.servicio(s), "usage": ser.consumo(u), "detail": r.detail}


def medir_todo(db: Session, org_id: Optional[str] = None, hoy: Optional[date] = None) -> dict:
    """Trabajo diario: cada servicio activo con fuente automatica anota su muestra del dia."""
    from app.models.proveedores import SupplierService
    hoy = hoy or timeutil.today()
    automaticas = [k for k, f in FUENTES.items() if f.automatica]
    q = db.query(SupplierService).filter(SupplierService.metering_source.in_(automaticas),
                                         SupplierService.status == "active")
    if org_id:
        q = q.filter(SupplierService.organization_id == org_id)
    medidos = fallos = 0
    for s in q.all():
        if s.end_date and s.end_date < hoy:
            continue
        try:
            f = fuente(s.metering_source)
            r = f.contar(db, s, s.metering_config or {}, hoy)
            anotar(db, s, r.quantity, hoy, f.clave, f.clave, None,
                   extra={"examples": r.detail.get("examples"), "count": r.detail.get("count")})
            medidos += 1
        except Exception as exc:  # un servicio roto no para a los demas
            db.rollback()
            fallos += 1
            logger.warning("medicion del servicio %s: %s", s.id, exc)
            try:
                s.metering_last_error = str(getattr(exc, "detail", exc))[:255]
                s.metering_last_at = datetime.now(timezone.utc)
                db.commit()
            except Exception:
                logger.warning("medir_todo: excepcion ignorada", exc_info=True)
                db.rollback()
    return {"supplier_metering_measured": medidos, "supplier_metering_failed": fallos}


# ── Recuentos externos: API e importacion ────────────────────────────────────

def _cantidad_de(datos: dict) -> float:
    items = datos.get("items")
    if items:
        # Se cuentan sin duplicados y se descartan: no se guarda ningun identificador.
        return float(len({str(x).strip().lower() for x in items if str(x).strip()}))
    if datos.get("quantity") is None:
        raise error(422, "campo_obligatorio", campo="quantity")
    return float(datos["quantity"])


def ingerir(db: Session, s, datos: dict, actor, origen: str = "api") -> dict:
    """Un recuento de un sistema externo para un servicio con fuente `external`."""
    if (s.metering_source or "manual") != "external":
        raise error(409, "proveedor_medicion_fuente_distinta", fuente=s.metering_source or "manual")
    fecha = datos.get("as_of") or timeutil.today()
    if isinstance(fecha, str):
        fecha = date.fromisoformat(fecha[:10])
    if fecha > timeutil.today():
        raise error(422, "proveedor_medicion_fecha_futura")
    sistema = (datos.get("system") or (s.metering_config or {}).get("system") or "").strip() or None
    u = anotar(db, s, _cantidad_de(datos), fecha, origen, sistema, actor,
               extra={"items_counted": bool(datos.get("items"))})
    if u is None:
        raise error(409, "proveedor_consumo_en_estado_de_cuenta")
    return ser.consumo(u)


def importar(db: Session, filas: list[dict], actor, sub_id: Optional[str] = None) -> dict:
    """Importacion de recuentos (CSV/JSON de un SIEM u otro sistema): fila a fila, sin parar."""
    from app.models.proveedores import SupplierService
    resultado = []
    ok = 0
    for i, fila in enumerate(filas):
        try:
            q = db.query(SupplierService).filter(SupplierService.id == fila.get("service_id"))
            if sub_id:
                q = q.filter(SupplierService.subcontractor_id == sub_id)
            s = q.first()
            if s is None:
                raise error(404, "no_encontrado", detail="Servicio no encontrado", que="servicio")
            u = ingerir(db, s, fila, actor, origen="import")
            resultado.append({"row": i + 1, "ok": True, "usage_id": u["id"], "quantity": u["quantity"]})
            ok += 1
        except Exception as exc:
            logger.warning("importar: excepcion ignorada", exc_info=True)
            db.rollback()
            resultado.append({"row": i + 1, "ok": False, "code": getattr(exc, "code", None),
                              "error": str(getattr(exc, "detail", exc))[:255]})
    return {"imported": ok, "failed": len(filas) - ok, "rows": resultado}
