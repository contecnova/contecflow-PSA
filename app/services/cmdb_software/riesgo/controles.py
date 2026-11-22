"""Controles compensatorios e intentos de explotación (§11.8 del diseño).

**Control compensatorio**: un WAF, IPS, parche virtual, aislamiento, EDR o
segmentación que mitiga un hallazgo **sin cerrarlo**: resta su `reduction` del
riesgo del hallazgo (y de su prioridad, en la reevaluación) mientras está
activo. Caducidad obligatoria (máximo `exception_max_days`); al caducar
(trabajo diario) deja de restar. Alta, revocación y caducidad, auditadas
(`sw_compensating_control`).

**Intentos de explotación**: importados de un SIEM/EDR/IPS (fichero CSV/JSON o
conexión `sw_siem`). Se deduplican por (fuente, id externo), se casan con el
CI por nombre/IP y con el hallazgo vivo del mismo CVE en ese CI, y suben su
riesgo (`exploit_attempts`).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.audit import audit_log
from app.services.cmdb_software.riesgo import ajustes as aj
from app.services.cmdb_software.riesgo import calculo as calc

TIPOS = tuple(aj.REDUCCION_POR_TIPO)
ACCIONES = ("blocked", "detected", "allowed")


def _q(db, modelo, org):
    return calc._q(db, modelo, org)


def control(db, org, id_):
    from app.models.cmdb_riesgo import CompensatingControl
    c = _q(db, CompensatingControl, org).filter(CompensatingControl.id == id_).first() if id_ else None
    if c is None:
        raise error(404, "swr_control_no_encontrado")
    return c


def serializar(db: Session, c) -> dict:
    from app.models.cmdb_software import SoftwareInstance, SoftwareProduct, Vulnerability, VulnerabilityFinding
    from app.models.service_desk.cmdb import ConfigurationItem
    from app.models.user import User
    f = db.get(VulnerabilityFinding, c.finding_id)
    v = db.get(Vulnerability, f.vulnerability_id) if f else None
    p = db.get(SoftwareProduct, f.product_id) if f else None
    i = db.get(SoftwareInstance, f.instance_id) if f and f.instance_id else None
    ci = db.get(ConfigurationItem, i.ci_id) if i and i.ci_id else None
    autor = db.get(User, c.created_by) if c.created_by else None
    return {"id": c.id, "finding_id": c.finding_id, "vuln_id": v.vuln_id if v else None,
            "product_name": p.name if p else None, "ci_name": ci.name if ci else None,
            "control_type": c.control_type, "description": c.description, "evidence": c.evidence,
            "reduction": c.reduction, "expires_at": c.expires_at.isoformat() if c.expires_at else None,
            "status": c.status, "created_by": c.created_by, "created_by_name": autor.full_name if autor else None,
            "created_at": c.created_at.isoformat() if c.created_at else None, "revoked_by": c.revoked_by,
            "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None, "revoke_reason": c.revoke_reason}


def listar(db: Session, org, estado: Optional[str] = None, finding_id: Optional[str] = None) -> list[dict]:
    from app.models.cmdb_riesgo import CompensatingControl
    q = _q(db, CompensatingControl, org)
    if estado:
        q = q.filter(CompensatingControl.status == estado)
    if finding_id:
        q = q.filter(CompensatingControl.finding_id == finding_id)
    return [serializar(db, c) for c in q.order_by(CompensatingControl.created_at.desc()).limit(1000)]


def _fecha(v) -> Optional[date]:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def crear(db: Session, org, datos: dict, usuario) -> list:
    """Uno por hallazgo de `finding_ids`. No confirma; reevalúa para que baje la prioridad."""
    from app.models.cmdb_riesgo import CompensatingControl
    from app.services.cmdb_software import ajustes as base
    from app.services.cmdb_software.correlacion import VIVOS, reevaluar
    from app.services.cmdb_software.gestion import hallazgo
    ids = [x for x in (datos.get("finding_ids") or ([datos["finding_id"]] if datos.get("finding_id") else [])) if x]
    if not ids:
        raise error(422, "swr_control_sin_hallazgos")
    tipo = datos.get("control_type")
    if tipo not in TIPOS:
        raise error(422, "swr_control_tipo", tipo=tipo)
    descripcion = (datos.get("description") or "").strip()
    if len(descripcion) < 5:
        raise error(422, "swr_control_descripcion")
    maximo = int(base.leer(db, org).get("exception_max_days") or 180)
    caduca = _fecha(datos.get("expires_at"))
    hoy = date.today()
    if caduca is None or not hoy < caduca <= hoy + timedelta(days=maximo):
        raise error(422, "swr_control_caducidad", max=maximo)
    reduccion = datos.get("reduction")
    if reduccion in (None, ""):
        reduccion = aj.REDUCCION_POR_TIPO[tipo]
    try:
        reduccion = float(reduccion)
    except (TypeError, ValueError):
        raise error(422, "swr_ajuste_no_valido", campo="reduction")
    if not 0.1 <= reduccion <= 0.9:
        raise error(422, "swr_ajuste_no_valido", campo="reduction")
    creados = []
    for fid in dict.fromkeys(ids):
        f = hallazgo(db, org, fid)
        if f.status not in VIVOS:
            raise error(422, "sw_hallazgo_cerrado")
        c = CompensatingControl(organization_id=org, finding_id=f.id, control_type=tipo, description=descripcion,
                                evidence=(datos.get("evidence") or None), reduction=reduccion, expires_at=caduca,
                                status="active", created_by=getattr(usuario, "id", None))
        db.add(c)
        db.flush()
        audit_log(db, usuario, "CREATE", "sw_compensating_control", c.id, f.finding_key[:80],
                  new_values={"finding_id": f.id, "control_type": tipo, "reduction": reduccion,
                              "expires_at": caduca.isoformat()})
        creados.append(c)
    reevaluar(db, org, usuario)
    return creados


def revocar(db: Session, org, id_: str, motivo: Optional[str], usuario):
    from app.services.cmdb_software.correlacion import reevaluar
    c = control(db, org, id_)
    if c.status != "active":
        raise error(422, "swr_control_no_activo")
    c.status, c.revoked_by, c.revoked_at = "revoked", getattr(usuario, "id", None), datetime.now(timezone.utc)
    c.revoke_reason = (motivo or "").strip() or None
    db.flush()
    audit_log(db, usuario, "UPDATE", "sw_compensating_control", c.id, c.control_type,
              old_values={"status": "active"}, new_values={"status": "revoked", "reason": c.revoke_reason})
    reevaluar(db, org, usuario)
    return c


def caducar(db: Session, org) -> int:
    """Trabajo diario: los controles vencidos dejan de restar. Devuelve cuántos."""
    from app.models.cmdb_riesgo import CompensatingControl
    hoy = date.today()
    n = 0
    for c in _q(db, CompensatingControl, org).filter(CompensatingControl.status == "active",
                                                    CompensatingControl.expires_at < hoy):
        c.status = "expired"
        n += 1
        audit_log(db, None, "UPDATE", "sw_compensating_control", c.id, c.control_type,
                  old_values={"status": "active"}, new_values={"status": "expired"}, metadata={"reason": "expired"})
    db.flush()
    return n


# ── Intentos de explotación ──────────────────────────────────────────────────

def _fecha_hora(v) -> Optional[datetime]:
    if not v:
        return None
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(float(v) / (1000 if v > 1e11 else 1), tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def leer_eventos(contenido: bytes) -> list[dict]:
    """CSV (`cve, host, ip, observed_at, action, count, id`) o JSON (lista u objeto con `events`/`items`)."""
    texto = contenido.decode("utf-8-sig", errors="replace").strip()
    if not texto:
        raise error(422, "sw_fichero_vacio")
    if texto[0] in "[{":
        try:
            datos = json.loads(texto)
        except ValueError as e:
            raise error(422, "sw_fichero_no_valido", detalle=str(e)[:100])
        if isinstance(datos, dict):
            datos = datos.get("events") or datos.get("items") or datos.get("data") or []
        return [d for d in datos if isinstance(d, dict)]
    muestra = texto[:2000]
    lector = csv.DictReader(io.StringIO(texto), delimiter=";" if muestra.count(";") > muestra.count(",") else ",")
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in fila.items()} for fila in lector]


def _normal(d: dict) -> dict:
    def primero(*claves):
        for k in claves:
            if d.get(k) not in (None, ""):
                return d[k]
        return None
    accion = str(primero("action", "outcome", "result") or "detected").lower()
    accion = "blocked" if accion in ("blocked", "block", "deny", "denied", "prevented", "dropped") else \
        "allowed" if accion in ("allowed", "allow", "permitted", "success", "succeeded") else "detected"
    try:
        cuenta = max(1, int(primero("count", "hits", "occurrences") or 1))
    except (TypeError, ValueError):
        cuenta = 1
    return {"cve": (str(primero("cve", "vuln_id", "cve_id", "vulnerability") or "").strip().upper() or None),
            "host": primero("host", "hostname", "device", "dest_host", "destination"),
            "ip": primero("ip", "dest_ip", "destination_ip", "ip_address"),
            "observed_at": _fecha_hora(primero("observed_at", "timestamp", "time", "@timestamp", "date")),
            "action": accion, "count": cuenta, "id": primero("id", "event_id", "uid")}


def aplicar_eventos(db: Session, org, filas: list[dict], fuente: str = "file", usuario=None) -> dict:
    """Guarda (deduplicando), casa con CI y hallazgo y actualiza `exploit_attempts`. No confirma."""
    from app.models.cmdb_riesgo import ExploitEvent
    from app.models.cmdb_software import SoftwareInstance, Vulnerability, VulnerabilityFinding
    from app.services.cmdb_software.correlacion import VIVOS
    from app.services.cmdb_software.importacion import buscar_ci
    resumen = {"rows": 0, "created": 0, "duplicates": 0, "matched": 0, "errors": []}
    tocados: set = set()
    for n, bruto in enumerate(filas[:20000], start=1):
        d = _normal(bruto)
        resumen["rows"] += 1
        if not d["observed_at"] or not (d["host"] or d["ip"]):
            resumen["errors"].append({"row": n, "error": "swr_ajuste_no_valido"})
            continue
        ext = str(d["id"] or hashlib.sha256(json.dumps(
            [d["cve"], d["host"], d["ip"], d["observed_at"].isoformat(), d["action"]]).encode()).hexdigest())[:200]
        if _q(db, ExploitEvent, org).filter(ExploitEvent.source == fuente, ExploitEvent.external_id == ext).first():
            resumen["duplicates"] += 1
            continue
        ci = buscar_ci(db, org, d["host"]) or buscar_ci(db, org, d["ip"])
        if ci is None and d["host"] and "." in str(d["host"]):
            ci = buscar_ci(db, org, str(d["host"]).split(".")[0])
        hallazgo_id = None
        if ci is not None and d["cve"]:
            vids = [v.id for v in _q(db, Vulnerability, org).filter(Vulnerability.vuln_id == d["cve"])]
            if not vids:
                vids = [v.id for v in _q(db, Vulnerability, org).filter(Vulnerability.aliases.like(f'%"{d["cve"]}"%'))]
            insts = [i.id for i in _q(db, SoftwareInstance, org).filter(SoftwareInstance.ci_id == ci.id)]
            versiones = [i.version_id for i in _q(db, SoftwareInstance, org).filter(
                SoftwareInstance.ci_id == ci.id, SoftwareInstance.version_id.isnot(None))]
            if vids:
                from sqlalchemy import or_
                f = (_q(db, VulnerabilityFinding, org)
                     .filter(VulnerabilityFinding.vulnerability_id.in_(vids), VulnerabilityFinding.status.in_(VIVOS),
                             or_(VulnerabilityFinding.instance_id.in_(insts or [""]),
                                 VulnerabilityFinding.parent_version_id.in_(versiones or [""])))
                     .order_by(VulnerabilityFinding.priority_score.desc().nullslast()).first())
                if f is not None:
                    hallazgo_id = f.id
        e = ExploitEvent(organization_id=org, source=fuente[:30], external_id=ext, vuln_id=d["cve"],
                         ci_id=ci.id if ci else None, host=(str(d["host"])[:255] if d["host"] else None),
                         ip=(str(d["ip"])[:45] if d["ip"] else None), observed_at=d["observed_at"],
                         action=d["action"], count=d["count"], finding_id=hallazgo_id,
                         created_by=getattr(usuario, "id", None))
        db.add(e)
        resumen["created"] += 1
        if hallazgo_id:
            resumen["matched"] += 1
            tocados.add(hallazgo_id)
    db.flush()
    from sqlalchemy import func
    for fid in tocados:
        f = db.get(VulnerabilityFinding, fid)
        total, ultima = (_q(db, ExploitEvent, org).with_entities(func.coalesce(func.sum(ExploitEvent.count), 0),
                                                                 func.max(ExploitEvent.observed_at))
                         .filter(ExploitEvent.finding_id == fid).one())
        f.exploit_attempts, f.last_exploit_at = int(total or 0), ultima
    db.flush()
    audit_log(db, usuario, "IMPORT", "sw_exploit_events", fuente, fuente,
              metadata={k: v for k, v in resumen.items() if k != "errors"} | {"errors": len(resumen["errors"])})
    resumen["errors"] = resumen["errors"][:100]
    return resumen


def importar_eventos(db: Session, org, contenido: bytes, usuario=None, fuente: str = "file") -> dict:
    from app.services.cmdb_software.importacion import comprobar_fichero
    comprobar_fichero(contenido)
    return aplicar_eventos(db, org, leer_eventos(contenido), fuente, usuario)


def listar_eventos(db: Session, org, dias: int = 30, pagina: int = 1, por_pagina: int = 50) -> dict:
    from app.models.cmdb_riesgo import ExploitEvent
    from app.models.service_desk.cmdb import ConfigurationItem
    desde = datetime.now(timezone.utc) - timedelta(days=max(1, min(int(dias or 30), 3650)))
    q = _q(db, ExploitEvent, org).filter(ExploitEvent.observed_at >= desde)
    total = q.count()
    filas = q.order_by(ExploitEvent.observed_at.desc()).offset((max(1, pagina) - 1) * por_pagina).limit(por_pagina).all()
    cis = {c.id: c.name for c in db.query(ConfigurationItem).filter(
        ConfigurationItem.id.in_({e.ci_id for e in filas if e.ci_id} or {""}))}
    return {"items": [{"id": e.id, "source": e.source, "vuln_id": e.vuln_id, "ci_id": e.ci_id,
                       "ci_name": cis.get(e.ci_id), "host": e.host, "ip": e.ip,
                       "observed_at": e.observed_at.isoformat() if e.observed_at else None, "action": e.action,
                       "count": e.count, "finding_id": e.finding_id} for e in filas], "total": total}
