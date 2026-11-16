"""Estado de uso derivado de las evidencias: por asignación y por licencia.

Estados (umbrales por empresa, grupo de ajustes `licencias_uso`):

- `en_uso`: último uso hace menos de `ALM_USAGE_UNDERUSED_DAYS` días (y, si la
  fuente da frecuencia, al menos `ALM_USAGE_MIN_ACTIVE_DAYS` días con uso en su
  periodo).
- `infrautilizada`: último uso entre `ALM_USAGE_UNDERUSED_DAYS` y
  `ALM_USAGE_IDLE_DAYS`, o frecuencia por debajo del mínimo.
- `sin_uso`: más de `ALM_USAGE_IDLE_DAYS` días sin uso, nunca usada desde que se
  asignó (pasado ese plazo), o la cuenta está desactivada en la fuente.
- `sin_datos`: ninguna fuente dice nada de ese titular con esa licencia (o
  la asignación es tan reciente que aún no se puede decir).

Los días sin uso se cuentan también descontando las AUSENCIAS APROBADAS de la
persona (vacaciones, bajas) dentro del intervalo (`dias_sin_uso_efectivos`):
el estado se calcula con los efectivos, para no marcar como «sin uso» a quien
estaba de baja. Si la lectura más reciente tiene más de
`ALM_USAGE_STALE_DATA_DAYS` días, `datos_desactualizados` = sí (se enseña, y
la recuperación no actúa sobre ella).

Con varias fuentes para el mismo titular manda el uso más reciente; la
fiabilidad que se informa es la de esa fuente.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.models.alm import ALMLicense
from app.models.alm import ALMLicenseAssignment as Asignacion
from app.models.alm_uso import ALMUsoEvidencia
from app.services.alm_uso._comun import (
    con_nombres, nombres_de_usuarios, RANGO_DE_FIABILIDAD, TITULAR_DISPOSITIVO, TITULAR_PERSONA, Umbrales, ahora, aware, cargar_json, exigir_org,
    umbrales,
)

_TITULAR_DE_ASIGNACION = {"user": TITULAR_PERSONA, "asset": TITULAR_DISPOSITIVO}


def _iso(v):
    return v.isoformat() if isinstance(v, (date, datetime)) else v


def ausencias_aprobadas(db: Session, org: str, user_ids: Iterable[str], desde: date) -> dict:
    """{user_id: [(inicio, fin)]} de ausencias aprobadas que terminan desde `desde`."""
    from app.models.resources import Absence, AbsenceStatus
    ids = [u for u in set(user_ids) if u]
    if not ids:
        return {}
    salida: dict = {}
    for uid, ini, fin in db.query(Absence.user_id, Absence.start_date, Absence.end_date).filter(
            Absence.organization_id == org, Absence.user_id.in_(ids), Absence.status == AbsenceStatus.approved,
            or_(Absence.is_active.is_(True), Absence.is_active.is_(None)), Absence.end_date >= desde).all():
        salida.setdefault(uid, []).append((ini, fin))
    return salida


def _dias_de_ausencia(periodos: list, desde: date, hasta: date) -> int:
    dias: set = set()
    for ini, fin in periodos or []:
        a, b = max(ini, desde), min(fin, hasta)
        while a <= b:
            dias.add(a)
            a += timedelta(days=1)
    return len(dias)


def evaluar(evidencias: list[ALMUsoEvidencia], u: Umbrales, hoy: date, *, referencia: Optional[date] = None,
            ausencias: Optional[list] = None) -> dict:
    """El estado de uso de UN titular con UNA licencia a partir de sus evidencias."""
    ausencias = ausencias or []
    en_ausencia = any(ini <= hoy <= fin for ini, fin in ausencias)
    if not evidencias:
        return {"estado": "sin_datos", "motivo": "sin_evidencias", "ultimo_uso": None, "dias_sin_uso": None,
                "dias_sin_uso_efectivos": None, "dias_ausencia": 0, "en_ausencia": en_ausencia, "frecuencia": None,
                "periodo_dias": None, "fuente": None, "fiabilidad": None, "leido_at": None,
                "datos_desactualizados": False, "cuenta_desactivada": False, "fuentes": [], "servicios": {}}
    ordenadas = sorted(evidencias, key=lambda e: (aware(e.ultimo_uso_at) or datetime.min.replace(
        tzinfo=ahora().tzinfo), -RANGO_DE_FIABILIDAD.get(e.fiabilidad, 9)), reverse=True)
    mejor = ordenadas[0]
    ultimo = aware(mejor.ultimo_uso_at)
    leido = max(aware(e.leido_at) for e in evidencias if e.leido_at)
    desactualizados = leido < ahora() - timedelta(days=u.dias_datos_antiguos)
    cuenta_desactivada = any((cargar_json(e.detalle, {}) or {}).get("cuenta_activa") is False
                             and e.vista_en_ultima_lectura for e in evidencias)
    servicios: dict = {}
    for e in evidencias:
        for k, v in (cargar_json(e.servicios, {}) or {}).items():
            if v and (k not in servicios or v > servicios[k]):
                servicios[k] = v
    fuentes = [{"fuente": e.fuente, "ultimo_uso": _iso(aware(e.ultimo_uso_at)), "fiabilidad": e.fiabilidad,
                "leido_at": _iso(aware(e.leido_at)), "frecuencia": e.frecuencia, "periodo_dias": e.periodo_dias,
                "asignada_en_fuente": e.asignada_en_fuente, "vista": e.vista_en_ultima_lectura,
                "producto": e.nombre_producto or e.producto} for e in ordenadas]

    desde = ultimo.date() if ultimo else (referencia or min(aware(e.created_at or e.leido_at).date()
                                                            for e in evidencias))
    dias = max(0, (hoy - desde).days)
    dias_aus = _dias_de_ausencia(ausencias, desde + timedelta(days=1), hoy)
    efectivos = max(0, dias - dias_aus)

    frecuencia = mejor.frecuencia
    solo_presencia = ultimo is None and all((cargar_json(e.detalle, {}) or {}).get("solo_presencia") for e in evidencias)
    if solo_presencia and not cuenta_desactivada:
        estado, motivo = "sin_datos", "instalada_sin_medida_de_uso"
    elif cuenta_desactivada:
        estado, motivo = "sin_uso", "cuenta_desactivada"
    elif ultimo is None and efectivos < u.dias_infrautilizada:
        estado, motivo = "sin_datos", "asignacion_reciente_sin_uso"
    elif efectivos >= u.dias_sin_uso:
        estado, motivo = "sin_uso", ("nunca_usada" if ultimo is None else "sin_uso_en_plazo")
    elif ultimo is None or efectivos >= u.dias_infrautilizada:
        estado, motivo = "infrautilizada", ("nunca_usada" if ultimo is None else "uso_antiguo")
    elif (frecuencia is not None and u.dias_activos_minimos and frecuencia < u.dias_activos_minimos):
        estado, motivo = "infrautilizada", "frecuencia_baja"
    else:
        estado, motivo = "en_uso", "uso_reciente"
    return {"estado": estado, "motivo": motivo, "ultimo_uso": _iso(ultimo), "dias_sin_uso": dias,
            "dias_sin_uso_efectivos": efectivos, "dias_ausencia": dias_aus, "en_ausencia": en_ausencia,
            "frecuencia": frecuencia, "periodo_dias": mejor.periodo_dias, "fuente": mejor.fuente,
            "fiabilidad": mejor.fiabilidad, "leido_at": _iso(leido), "datos_desactualizados": desactualizados,
            "cuenta_desactivada": cuenta_desactivada, "fuentes": fuentes, "servicios": servicios}


class Lector:
    """Carga de una vez las evidencias y ausencias de una empresa para muchas asignaciones."""

    def __init__(self, db: Session, org: str, license_ids: Optional[list] = None):
        self.db, self.org = db, exigir_org(org)
        self.u = umbrales(db, org)
        self.hoy = timeutil.today()
        q = db.query(ALMUsoEvidencia).filter(ALMUsoEvidencia.organization_id == org,
                                             ALMUsoEvidencia.license_id.isnot(None))
        if license_ids is not None:
            q = q.filter(ALMUsoEvidencia.license_id.in_(license_ids or [""]))
        self.por_titular: dict = {}
        self.por_licencia: dict = {}
        usuarios = set()
        primera = self.hoy
        for e in q.all():
            clave = e.user_id if e.titular_tipo == TITULAR_PERSONA else e.asset_id
            if clave:
                self.por_titular.setdefault((e.license_id, e.titular_tipo, clave), []).append(e)
            self.por_licencia.setdefault(e.license_id, []).append(e)
            if e.user_id:
                usuarios.add(e.user_id)
            if e.ultimo_uso_at:
                primera = min(primera, aware(e.ultimo_uso_at).date())
        self._usuarios = usuarios
        self._desde = max(primera, self.hoy - timedelta(days=730))
        self._ausencias: Optional[dict] = None

    def ausencias(self, user_id: Optional[str]) -> list:
        if not user_id:
            return []
        if self._ausencias is None:
            self._ausencias = ausencias_aprobadas(self.db, self.org, self._usuarios, self._desde)
        if user_id not in self._ausencias and user_id not in self._usuarios:
            self._ausencias.update(ausencias_aprobadas(self.db, self.org, [user_id], self._desde))
        return self._ausencias.get(user_id, [])

    def de_asignacion(self, a: Asignacion) -> dict:
        tipo = _TITULAR_DE_ASIGNACION.get(a.holder_type)
        titular = a.holder_user_id if tipo == TITULAR_PERSONA else (a.holder_asset_id if tipo else None)
        base = {"assignment_id": a.id, "license_id": a.license_id, "holder_type": a.holder_type,
                "user_id": a.holder_user_id, "asset_id": a.holder_asset_id, "mode": a.mode,
                "valid_from": _iso(a.valid_from)}
        if tipo is None:
            # Bolsa de un proyecto, departamento o cliente: su uso es el de sus hijas.
            return {**base, **evaluar([], self.u, self.hoy), "motivo": "titular_colectivo"}
        evs = self.por_titular.get((a.license_id, tipo, titular), [])
        return {**base, **evaluar(evs, self.u, self.hoy, referencia=a.valid_from,
                                  ausencias=self.ausencias(a.holder_user_id))}


def _asignaciones(db: Session, org: str, license_ids: Optional[list] = None) -> list[Asignacion]:
    q = db.query(Asignacion).filter(Asignacion.organization_id == org, Asignacion.resource_type == "license",
                                    Asignacion.status == "active", Asignacion.license_id.isnot(None))
    if license_ids is not None:
        q = q.filter(Asignacion.license_id.in_(license_ids or [""]))
    return q.all()


def uso_de_asignacion(db: Session, assignment_id: str, organization_id: Optional[str] = None) -> dict:
    org = exigir_org(organization_id or (db.info or {}).get("organization_id"))
    a = db.query(Asignacion).filter(Asignacion.id == assignment_id, Asignacion.organization_id == org).first()
    if a is None or not a.license_id:
        raise ErrorDeDominio(404, {"code": "ALM_USAGE_ASSIGNMENT_NOT_FOUND", "message": "Asignación no encontrada"})
    return con_nombres(db, org, [Lector(db, org, [a.license_id]).de_asignacion(a)])[0]


def _resumen(lic: ALMLicense, filas: list[dict], sin_asignacion: int, evidencias: list) -> dict:
    cuenta = {k: sum(1 for f in filas if f["estado"] == k) for k in ("en_uso", "infrautilizada", "sin_uso", "sin_datos")}
    lecturas = [aware(e.leido_at) for e in evidencias if e.leido_at]
    medido = max(lecturas) if lecturas else None
    fuentes = sorted({e.fuente for e in evidencias})
    if not filas:
        global_ = "sin_datos"
    elif cuenta["sin_datos"] == len(filas):
        global_ = "sin_datos"
    elif cuenta["sin_uso"] + cuenta["infrautilizada"] == 0:
        global_ = "en_uso"
    elif cuenta["sin_uso"] >= max(1, len(filas) - cuenta["sin_datos"]):
        global_ = "sin_uso"
    else:
        global_ = "infrautilizada"
    ultimos = [f["ultimo_uso"] for f in filas if f.get("ultimo_uso")]
    return {"license_id": lic.id, "nombre": lic.name, "metric": lic.metric, "estado": global_,
            "asignados": len(filas), "total": lic.total_seats, "en_uso": cuenta["en_uso"],
            "infrautilizadas": cuenta["infrautilizada"], "sin_uso": cuenta["sin_uso"], "sin_datos": cuenta["sin_datos"],
            "uso_sin_asignacion": sin_asignacion, "pico_concurrente": lic.concurrent_peak,
            "pico_medido_en": _iso(aware(lic.concurrent_peak_at)),
            "ultimo_uso": max(ultimos) if ultimos else None,
            "fuente": ", ".join(fuentes) or None, "fuentes": fuentes, "medido_en": _iso(medido)}


def uso_de_licencias(db: Session, organization_id: str, license_ids: Optional[list] = None,
                     con_asignaciones: bool = False) -> list[dict]:
    """El resumen de uso de varias licencias (todas las activas de la empresa si no se dicen)."""
    org = exigir_org(organization_id)
    q = db.query(ALMLicense).filter(ALMLicense.organization_id == org, ALMLicense.is_active.is_(True))
    if license_ids is not None:
        q = q.filter(ALMLicense.id.in_(license_ids or [""]))
    licencias = q.order_by(ALMLicense.name).all()
    ids = [l.id for l in licencias]
    lector = Lector(db, org, ids)
    por_lic: dict = {}
    for a in _asignaciones(db, org, ids):
        por_lic.setdefault(a.license_id, []).append(lector.de_asignacion(a))
    salida = []
    for lic in licencias:
        filas = por_lic.get(lic.id, [])
        con = {(f["user_id"] if f["holder_type"] == "user" else f["asset_id"]) for f in filas}
        evs = lector.por_licencia.get(lic.id, [])
        sin = {(e.user_id or e.asset_id or e.titular_externo) for e in evs
               if e.vista_en_ultima_lectura and (e.user_id or e.asset_id) not in con
               and (e.ultimo_uso_at is not None or e.asignada_en_fuente)}
        r = _resumen(lic, filas, len(sin), evs)
        if con_asignaciones:
            r["asignaciones"] = con_nombres(db, org, filas)
        salida.append(r)
    return salida


def uso_de_licencia(db: Session, license_id: str, organization_id: Optional[str] = None) -> dict:
    org = organization_id or (db.info or {}).get("organization_id")
    if not org:
        lic = db.query(ALMLicense).filter(ALMLicense.id == license_id).first()
        org = lic.organization_id if lic else None
    r = uso_de_licencias(db, exigir_org(org), [license_id], con_asignaciones=True)
    if not r:
        raise ErrorDeDominio(404, {"code": "ALM_USAGE_LICENSE_NOT_FOUND", "message": "Licencia no encontrada"})
    return r[0]


def uso_de_equipos(db: Session, organization_id: str) -> list[dict]:
    """Último contacto de cada activo según el inventario: quién usa (o dejó de usar) cada equipo."""
    from app.models.alm import ALMAsset
    from app.services.alm_uso.conciliacion import PRODUCTO_EQUIPO
    org = exigir_org(organization_id)
    u = umbrales(db, org)
    hoy = timeutil.today()
    evs: dict = {}
    for e in db.query(ALMUsoEvidencia).filter(ALMUsoEvidencia.organization_id == org,
                                              ALMUsoEvidencia.producto == PRODUCTO_EQUIPO,
                                              ALMUsoEvidencia.asset_id.isnot(None)).all():
        evs.setdefault(e.asset_id, []).append(e)
    salida = []
    activos = db.query(ALMAsset).filter(ALMAsset.organization_id == org, ALMAsset.is_active.is_(True)).all()
    nombres = nombres_de_usuarios(db, org, [a.assigned_to_id for a in activos]
                                  + [e.user_id for lista in evs.values() for e in lista])
    for a in activos:
        lista = evs.get(a.id, [])
        r = evaluar(lista, u, hoy)
        principal = next((e.user_id for e in sorted(lista, key=lambda e: aware(e.ultimo_uso_at) or aware(e.leido_at),
                                                    reverse=True) if e.user_id), None)
        salida.append({"asset_id": a.id, "nombre": a.name, "serie": a.serial_number, "tipo": getattr(a.type, "value", a.type),
                       "estado_activo": getattr(a.status, "value", a.status), "asignado_a": a.assigned_to_id,
                       "asignado_a_nombre": nombres.get(a.assigned_to_id), "usuario_en_fuente": principal,
                       "usuario_en_fuente_nombre": nombres.get(principal),
                       "discrepancia_de_usuario": bool(principal and a.assigned_to_id and principal != a.assigned_to_id),
                       **{k: r[k] for k in ("estado", "motivo", "ultimo_uso", "dias_sin_uso", "fuente", "fiabilidad",
                                            "leido_at", "datos_desactualizados", "fuentes")}})
    return salida
