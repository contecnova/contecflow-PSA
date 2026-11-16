"""Concilia lo que lee una fuente con ALM y lo guarda.

- Titular persona → `User` de la empresa por correo (ficha o pertenencia). Si
  no es de la empresa, la evidencia se guarda igual (cuenta para cumplimiento:
  alguien consume un puesto) pero sin persona (`sin_titular`).
- Titular dispositivo → `ALMAsset` de la empresa por nº de serie y, si no, por
  nombre de equipo. Si no existe y `ALM_USAGE_CREATE_ASSETS`, se crea.
- Producto/SKU → licencia de ALM: el mapeo explícito de la empresa
  (`ALMUsoMapeo`) y, si no hay, la licencia cuyo `sku` coincide o, si solo hay
  una, la cuyo nombre o producto normalizado coincide. Si hay varias candidatas
  no se adivina: queda sin licencia y la pantalla propone el mapeo.
- Asignación: la asignación vigente de esa licencia a esa persona
  (`holder_user_id`) o a ese equipo (`holder_asset_id`).
- Software de un equipo con licencia → `ALMSoftwareInstall` (se crea si no
  existe). Si la fuente dio la lista COMPLETA del equipo y una app ya no está,
  su evidencia deja de estar «vista» y la instalación que creó esta
  conciliación se desactiva.

Todo se escribe con `organization_id` de la conexión, y toda búsqueda se acota
explícitamente a esa empresa.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.alm import ALMAsset, ALMAssetHistory, ALMLicense, ALMSoftwareInstall, AssetType, ALMAssetStatus
from app.models.alm import ALMLicenseAssignment as Asignacion
from app.models.alm_uso import ALMUsoDerecho, ALMUsoEvidencia, ALMUsoMapeo
from app.services.alm_uso._comun import (
    TITULAR_DISPOSITIVO, TITULAR_PERSONA, aware, cargar_json, normalizar, volcar_json,
)
from app.services.alm_uso.proveedores.base import Dispositivo, Evidencia, ResultadoDeLectura

#: Producto de la evidencia que dice que el equipo da señales (último contacto).
PRODUCTO_EQUIPO = "__equipo__"
_REBAJA = {"alta": "media", "media": "baja", "baja": "baja"}


class Indices:
    """Lo que la conciliación consulta una vez por lectura (todo de UNA empresa)."""

    def __init__(self, db: Session, org: str, fuente: str):
        from app.db.session import _miembros_de
        from app.models.user import User
        self.db, self.org, self.fuente = db, org, fuente
        self.usuarios = {e.lower(): uid for uid, e in db.query(User.id, User.email)
                         .filter(_miembros_de(User, org), User.email.isnot(None)).all() if e}
        self.licencias = db.query(ALMLicense).filter(ALMLicense.organization_id == org,
                                                     ALMLicense.is_active.is_(True)).all()
        self.por_sku: dict = {}
        self.por_nombre: dict = {}
        for lic in self.licencias:
            if lic.sku:
                self.por_sku.setdefault(lic.sku.strip().lower(), []).append(lic.id)
            for n in {normalizar(lic.product_name), normalizar(lic.name),
                      normalizar(f"{lic.product_name or ''} {lic.edition or ''}")}:
                if n:
                    self.por_nombre.setdefault(n, set()).add(lic.id)
        self.mapeos = {m.producto: m for m in db.query(ALMUsoMapeo).filter(
            ALMUsoMapeo.organization_id == org, ALMUsoMapeo.fuente == fuente).all()}
        self.asignaciones: dict = {}
        for a in db.query(Asignacion).filter(Asignacion.organization_id == org,
                                             Asignacion.resource_type == "license",
                                             Asignacion.status == "active").all():
            if a.holder_user_id:
                self.asignaciones.setdefault((a.license_id, TITULAR_PERSONA, a.holder_user_id), a.id)
            if a.holder_asset_id:
                self.asignaciones.setdefault((a.license_id, TITULAR_DISPOSITIVO, a.holder_asset_id), a.id)

    def licencia(self, producto: str, nombre: Optional[str], sku: Optional[str]) -> tuple[Optional[str], bool]:
        """(license_id, ignorado). Mapeo explícito → SKU → nombre único."""
        m = self.mapeos.get(producto)
        if m is not None:
            return (None, True) if m.ignorar else (m.license_id, False)
        for clave in (producto, sku):
            ids = self.por_sku.get((clave or "").strip().lower()) or []
            if len(ids) == 1:
                return ids[0], False
        for n in (normalizar(nombre), normalizar(producto)):
            ids = self.por_nombre.get(n) or set()
            if len(ids) == 1:
                return next(iter(ids)), False
        return None, False


def _servicios_json(servicios: dict) -> Optional[str]:
    return volcar_json({k: (aware(v).isoformat() if isinstance(v, datetime) else v)
                        for k, v in (servicios or {}).items() if v is not None}) if servicios else None


def guardar_evidencias(db: Session, idx: Indices, conexion, fiabilidad: str, evidencias: list[Evidencia],
                       leido_at: datetime, contador: dict, completa: bool = True) -> None:
    """Upsert de las evidencias de personas de una lectura.

    Si la lectura fue completa, las que la fuente ya no da dejan de estar vistas
    (p. ej. le quitaron la licencia en Microsoft 365). Una lectura cortada no
    retira nada.
    """
    existentes = {(e.titular_tipo, e.titular_externo, e.producto): e for e in db.query(ALMUsoEvidencia).filter(
        ALMUsoEvidencia.organization_id == idx.org, ALMUsoEvidencia.fuente == idx.fuente,
        ALMUsoEvidencia.titular_tipo == TITULAR_PERSONA)}
    vistos = set()
    for ev in evidencias:
        titular = (ev.titular or "").strip().lower()[:320]
        producto = (ev.producto or "").strip()[:255]
        if not titular or not producto:
            continue
        clave = (TITULAR_PERSONA, titular, producto)
        if clave in vistos:
            continue
        vistos.add(clave)
        user_id = idx.usuarios.get(titular)
        if user_id is None:
            contador["sin_titular"] += 1
        license_id, ignorado = idx.licencia(producto, ev.nombre_producto, ev.sku)
        if license_id is None and not ignorado:
            contador["sin_licencia"] += 1
        fila = existentes.get(clave)
        if fila is None:
            fila = ALMUsoEvidencia(organization_id=idx.org, fuente=idx.fuente, titular_tipo=TITULAR_PERSONA,
                                   titular_externo=titular, producto=producto)
            db.add(fila)
            contador["nuevas"] += 1
        else:
            contador["actualizadas"] += 1
        _rellenar(fila, ev, conexion, fiabilidad, leido_at, license_id)
        fila.user_id = user_id
        fila.assignment_id = idx.asignaciones.get((license_id, TITULAR_PERSONA, user_id)) if license_id and user_id else None
    for clave, fila in existentes.items():
        if completa and clave not in vistos:
            fila.vista_en_ultima_lectura = False
            fila.leido_at = leido_at


def _rellenar(fila: ALMUsoEvidencia, ev: Evidencia, conexion, fiabilidad: str, leido_at: datetime,
              license_id: Optional[str]) -> None:
    fila.conexion_id = conexion.id if conexion is not None else None
    fila.nombre_producto = (ev.nombre_producto or None) and str(ev.nombre_producto)[:255]
    fila.sku = (ev.sku or None) and str(ev.sku)[:120]
    fila.license_id = license_id
    fila.asignada_en_fuente = ev.asignada
    fila.ultimo_uso_at = aware(ev.ultimo_uso)
    fila.frecuencia = ev.frecuencia
    fila.periodo_dias = ev.periodo_dias
    fila.servicios = _servicios_json(ev.servicios)
    fila.fiabilidad = _REBAJA[fiabilidad] if (ev.detalle or {}).get("fiabilidad_reducida") else fiabilidad
    fila.leido_at = leido_at
    fila.vista_en_ultima_lectura = True
    fila.detalle = volcar_json(ev.detalle or None)


# ── Dispositivos ──────────────────────────────────────────────────────────────

def tipo_de_activo(d: Dispositivo) -> AssetType:
    """Tipo de activo deducido del sistema y del modelo. Sin pista clara: «otro» (no se inventa)."""
    so = (d.sistema or "").lower()
    modelo = (d.modelo or "").lower()
    if "ipad" in so or "ipad" in modelo:
        return AssetType.tablet
    if any(x in so for x in ("ios", "android")):
        return AssetType.mobile
    if "server" in so:
        return AssetType.server
    if "virtual" in modelo or "vmware" in modelo:
        return AssetType.vm
    if re.search(r"book|laptop|notebook|thinkpad|latitude|surface|elitebook|probook|zenbook|xps", modelo):
        return AssetType.laptop
    if re.search(r"imac|mac mini|mac pro|mac studio|optiplex|desktop|tower|prodesk|thinkcentre", modelo):
        return AssetType.desktop
    return AssetType.other


def _activo(db: Session, idx: Indices, d: Dispositivo, crear: bool, contador: dict) -> Optional[ALMAsset]:
    a = None
    serie = (d.serie or "").strip()
    if serie:
        a = db.query(ALMAsset).filter(ALMAsset.organization_id == idx.org, ALMAsset.is_active.is_(True),
                                      func.lower(ALMAsset.serial_number) == serie.lower()).first()
    nombre = (d.nombre or "").strip()
    if a is None and nombre:
        a = db.query(ALMAsset).filter(ALMAsset.organization_id == idx.org, ALMAsset.is_active.is_(True),
                                      func.lower(ALMAsset.hostname) == nombre.lower()).first()
    if a is None and crear and (serie or nombre):
        a = ALMAsset(organization_id=idx.org, name=(nombre or serie)[:200], type=tipo_de_activo(d),
                     serial_number=serie or None, hostname=nombre or None, brand=d.fabricante, model=d.modelo,
                     os=" ".join(x for x in (d.sistema, d.version_sistema) if x)[:100] or None,
                     ip_address=d.ip, status=ALMAssetStatus.in_use if d.usuario else ALMAssetStatus.available,
                     notes=f"Creado por el inventario ({idx.fuente})")
        db.add(a)
        db.flush()
        db.add(ALMAssetHistory(organization_id=idx.org, asset_id=a.id, field_name="created", new_value=idx.fuente,
                               note=f"inventario:{idx.fuente}"))
        contador["activos_creados"] += 1
        return a
    if a is not None:
        cambios = {"serial_number": serie or None, "hostname": nombre or None, "brand": d.fabricante,
                   "model": d.modelo, "ip_address": d.ip,
                   "os": " ".join(x for x in (d.sistema, d.version_sistema) if x)[:100] or None}
        for campo, valor in cambios.items():
            actual = getattr(a, campo)
            # Solo rellena lo vacío (y la IP / el sistema, que cambian): no pisa lo que escribió una persona.
            if valor and (not actual or (campo in ("ip_address", "os") and actual != valor)):
                db.add(ALMAssetHistory(organization_id=idx.org, asset_id=a.id, field_name=campo,
                                       old_value=(str(actual)[:500] if actual else None), new_value=str(valor)[:500],
                                       note=f"inventario:{idx.fuente}"))
                setattr(a, campo, valor)
    return a


def _titular_de_equipo(d: Dispositivo) -> str:
    return ((d.serie or "").strip() or (d.nombre or "").strip() or f"id:{d.externo_id}").lower()[:320]


def guardar_dispositivos(db: Session, idx: Indices, conexion, fiabilidad: str, dispositivos: list[Dispositivo],
                         leido_at: datetime, crear_activos: bool, contador: dict) -> list[tuple]:
    """Evidencias de equipo y de su software; activos e instalaciones. Devuelve las apps sin licencia vistas."""
    sin_licencia: list = []
    for d in dispositivos:
        titular = _titular_de_equipo(d)
        activo = _activo(db, idx, d, crear_activos, contador)
        usuario = idx.usuarios.get((d.usuario or "").lower()) if d.usuario else None
        contador["dispositivos"] += 1
        previas = {e.producto: e for e in db.query(ALMUsoEvidencia).filter(
            ALMUsoEvidencia.organization_id == idx.org, ALMUsoEvidencia.fuente == idx.fuente,
            ALMUsoEvidencia.titular_tipo == TITULAR_DISPOSITIVO, ALMUsoEvidencia.titular_externo == titular)}
        equipo = previas.get(PRODUCTO_EQUIPO)
        if equipo is None:
            equipo = ALMUsoEvidencia(organization_id=idx.org, fuente=idx.fuente, titular_tipo=TITULAR_DISPOSITIVO,
                                     titular_externo=titular, producto=PRODUCTO_EQUIPO)
            db.add(equipo)
            contador["nuevas"] += 1
        else:
            contador["actualizadas"] += 1
        _rellenar(equipo, Evidencia(titular_tipo=TITULAR_DISPOSITIVO, titular=titular, producto=PRODUCTO_EQUIPO,
                                    nombre_producto=d.nombre, ultimo_uso=d.ultimo_contacto,
                                    detalle={**(d.detalle or {}), "usuario": d.usuario, "serie": d.serie,
                                             "sistema": d.sistema, "modelo": d.modelo, "id_externo": d.externo_id}),
                  conexion, fiabilidad, leido_at, None)
        equipo.asset_id = activo.id if activo else None
        equipo.user_id = usuario

        vistas = {PRODUCTO_EQUIPO}
        for app in d.apps:
            producto = normalizar(app.nombre)[:255]
            if not producto or producto in vistas:
                continue
            vistas.add(producto)
            license_id, ignorado = idx.licencia(producto, app.nombre, None)
            if license_id is None and not ignorado:
                contador["sin_licencia"] += 1
                sin_licencia.append((app.nombre, titular, usuario))
            fila = previas.get(producto)
            if fila is None:
                fila = ALMUsoEvidencia(organization_id=idx.org, fuente=idx.fuente, titular_tipo=TITULAR_DISPOSITIVO,
                                       titular_externo=titular, producto=producto)
                db.add(fila)
                contador["nuevas"] += 1
            else:
                contador["actualizadas"] += 1
            previo = cargar_json(fila.detalle, {}) or {}
            _rellenar(fila, Evidencia(titular_tipo=TITULAR_DISPOSITIVO, titular=titular, producto=producto,
                                      nombre_producto=app.nombre, ultimo_uso=app.ultimo_uso, asignada=True,
                                      detalle={"version": app.version, "editor": app.editor,
                                               "install_creada": previo.get("install_creada"),
                                               # Instalada no es usada: sin dato de uso, no dice «sin uso».
                                               "solo_presencia": app.ultimo_uso is None}),
                      conexion, fiabilidad, leido_at, license_id)
            fila.asset_id = activo.id if activo else None
            fila.user_id = usuario
            fila.assignment_id = (idx.asignaciones.get((license_id, TITULAR_DISPOSITIVO, activo.id))
                                  if license_id and activo else None)
            if license_id and activo:
                _instalacion(db, idx, fila, license_id, activo.id, app.version)
        if d.apps_leidas:
            for producto, fila in previas.items():
                if producto in vistas:
                    continue
                fila.vista_en_ultima_lectura = False
                fila.leido_at = leido_at
                if fila.install_id and (cargar_json(fila.detalle, {}) or {}).get("install_creada"):
                    inst = db.query(ALMSoftwareInstall).filter(ALMSoftwareInstall.id == fila.install_id,
                                                               ALMSoftwareInstall.organization_id == idx.org).first()
                    if inst is not None and inst.is_active:
                        inst.is_active = False
                        contador["instalaciones_retiradas"] += 1
    return sin_licencia


def _instalacion(db: Session, idx: Indices, fila: ALMUsoEvidencia, license_id: str, asset_id: str,
                 version: Optional[str]) -> None:
    inst = db.query(ALMSoftwareInstall).filter(ALMSoftwareInstall.organization_id == idx.org,
                                               ALMSoftwareInstall.license_id == license_id,
                                               ALMSoftwareInstall.asset_id == asset_id,
                                               ALMSoftwareInstall.is_active.is_(True)).first()
    detalle = cargar_json(fila.detalle, {}) or {}
    if inst is None:
        inst = ALMSoftwareInstall(organization_id=idx.org, license_id=license_id, asset_id=asset_id,
                                  version=(version or None) and str(version)[:50],
                                  notes=f"Detectado por el inventario ({idx.fuente})")
        db.add(inst)
        db.flush()
        detalle["install_creada"] = True
        fila.detalle = volcar_json(detalle)
    elif version and inst.version != str(version)[:50]:
        inst.version = str(version)[:50]
    fila.install_id = inst.id


# ── Derechos ──────────────────────────────────────────────────────────────────

def guardar_derechos(db: Session, idx: Indices, conexion, derechos: list, leido_at: datetime) -> None:
    previos = {d.sku: d for d in db.query(ALMUsoDerecho).filter(ALMUsoDerecho.organization_id == idx.org,
                                                                ALMUsoDerecho.fuente == idx.fuente)}
    for d in derechos:
        sku = (d.sku or "")[:255]
        if not sku:
            continue
        fila = previos.get(sku)
        if fila is None:
            fila = ALMUsoDerecho(organization_id=idx.org, fuente=idx.fuente, sku=sku)
            db.add(fila)
        fila.conexion_id = conexion.id if conexion is not None else None
        fila.nombre = d.nombre
        fila.comprados, fila.consumidos, fila.suspendidos = d.comprados, d.consumidos, d.suspendidos
        fila.license_id, _ = idx.licencia(sku, d.nombre, (d.detalle or {}).get("sku_id"))
        fila.detalle = volcar_json(d.detalle or None)
        fila.leido_at = leido_at


def conciliar(db: Session, org: str, fuente: str, conexion, fiabilidad: str, r: ResultadoDeLectura,
              leido_at: datetime, crear_activos: bool) -> dict:
    """Guarda una lectura completa. Devuelve los contadores para el registro de la sincronización."""
    contador = {"leidos": len(r.evidencias) + len(r.dispositivos), "nuevas": 0, "actualizadas": 0,
                "sin_titular": 0, "sin_licencia": 0, "dispositivos": 0, "activos_creados": 0,
                "instalaciones_retiradas": 0}
    idx = Indices(db, org, fuente)
    if r.evidencias or fuente not in ("intune", "jamf", "agente_cmdb"):
        completa = not any(a.get("codigo") == "TRUNCATED" for a in r.avisos)
        guardar_evidencias(db, idx, conexion, fiabilidad, r.evidencias, leido_at, contador, completa)
    apps_sin_licencia = guardar_dispositivos(db, idx, conexion, fiabilidad, r.dispositivos, leido_at,
                                             crear_activos, contador) if r.dispositivos else []
    if r.derechos:
        guardar_derechos(db, idx, conexion, r.derechos, leido_at)
    db.flush()
    from app.services.alm_uso import no_controlado
    no_controlado.registrar_de_lectura(db, org, fuente, idx, r, apps_sin_licencia)
    return contador
