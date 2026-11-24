"""Certificaciones: utilidades comunes (empresa, JSON, fechas, SoD, auditoría y avisos)."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.codigos_de_error import error
from app.models.certificaciones import CertConfiguracion

logger = logging.getLogger("contecflow.certificaciones")

#: Recurso de `audit_log` de todo el módulo (el detalle va en `resource_name`/valores).
RECURSO = "certificaciones"


def org_de(usuario) -> str:
    org = getattr(usuario, "organization_id", None)
    if not org:
        raise error(403, "cert_sin_empresa")
    return org


def json_de(raw, defecto=None) -> Any:
    try:
        v = json.loads(raw) if raw else defecto
    except (TypeError, ValueError):
        return defecto
    return v if v is not None else defecto


def dump(v) -> Optional[str]:
    return json.dumps(v, ensure_ascii=False, default=str) if v is not None else None


def hoy() -> date:
    return timeutil.today()


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def aware(v: Optional[datetime]) -> Optional[datetime]:
    """SQLite devuelve fechas sin zona: se leen como UTC."""
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def fecha(v, campo: str = "fecha") -> Optional[date]:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError as exc:
        raise error(422, "cert_campo_no_valido", campo=campo) from exc


def fecha_hora(v, campo: str = "fecha") -> Optional[datetime]:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return aware(v)
    try:
        return aware(datetime.fromisoformat(str(v).replace("Z", "+00:00")))
    except ValueError as exc:
        raise error(422, "cert_campo_no_valido", campo=campo) from exc


def iso(v) -> Optional[str]:
    return v.isoformat() if v is not None else None


def elegir(valor, opciones: tuple, campo: str):
    if valor not in opciones:
        raise error(422, "cert_campo_no_valido", campo=campo)
    return valor


def propio(db: Session, modelo, id_: str, usuario, que: str):
    """La fila `id_` de `modelo` si es de la empresa del usuario; 404 si no (no se distingue «ajena»)."""
    fila = db.get(modelo, id_) if id_ else None
    if fila is None or fila.organization_id != org_de(usuario):
        raise error(404, "no_encontrado", que=f"cert_{que}")
    return fila


def usuario_de_la_empresa(db: Session, org: str, user_id: Optional[str], campo: str) -> Optional[str]:
    if not user_id:
        return None
    from app.models.user import User
    u = db.get(User, user_id)
    if u is None or u.organization_id != org:
        raise error(422, "cert_campo_no_valido", campo=campo)
    return u.id


def nombre_de(db: Session, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    from app.models.user import User
    u = db.get(User, user_id)
    return (u.full_name or u.username) if u else None


# ── Configuración ────────────────────────────────────────────────────────────

CAMPOS_DE_CONFIG = (
    "aviso_certificado_dias", "aviso_auditoria_dias", "caducidad_evidencia_dias", "aviso_evidencia_dias",
    "exigir_evidencia_aprobada", "acceso_auditor_max_dias", "autoridad_nis2", "nis2_alerta_horas",
    "nis2_notificacion_horas", "nis2_informe_final_dias", "proyecto_capa_id",
)
_DEFECTOS = {"aviso_certificado_dias": 90, "aviso_auditoria_dias": 30, "caducidad_evidencia_dias": 365,
             "aviso_evidencia_dias": 30, "exigir_evidencia_aprobada": True, "acceso_auditor_max_dias": 30,
             "autoridad_nis2": None, "nis2_alerta_horas": 24, "nis2_notificacion_horas": 72,
             "nis2_informe_final_dias": 30, "proyecto_capa_id": None}


def config(db: Session, org: str) -> CertConfiguracion:
    """La configuración de la empresa; sin fila, una en memoria con los valores por defecto (no se guarda)."""
    c = db.query(CertConfiguracion).filter(CertConfiguracion.organization_id == org).first()
    if c is None:
        c = CertConfiguracion(organization_id=org, **_DEFECTOS)
    return c


def config_dict(c: CertConfiguracion) -> dict:
    return {k: getattr(c, k) if getattr(c, k) is not None else _DEFECTOS[k] for k in CAMPOS_DE_CONFIG} | {
        "autoridad_nis2": c.autoridad_nis2, "proyecto_capa_id": c.proyecto_capa_id}


def guardar_config(db: Session, usuario, datos: dict) -> dict:
    org = org_de(usuario)
    c = db.query(CertConfiguracion).filter(CertConfiguracion.organization_id == org).first()
    if c is None:
        c = CertConfiguracion(organization_id=org, **_DEFECTOS)
        db.add(c)
    antes = config_dict(c)
    for k, v in datos.items():
        if k not in CAMPOS_DE_CONFIG:
            continue
        if k == "proyecto_capa_id" and v:
            from app.models.project import Project
            p = db.get(Project, v)
            if p is None or p.organization_id != org:
                raise error(422, "cert_config_no_valida", campo=k)
        if k.endswith(("_dias", "_horas")) and (v is None or int(v) < 1 or int(v) > 3650):
            raise error(422, "cert_config_no_valida", campo=k)
        setattr(c, k, v)
    c.updated_por = usuario.id
    c.updated_at = ahora()
    auditar(db, usuario, "UPDATE", "config", c.id, antes=antes, despues=config_dict(c))
    db.commit()
    return config_dict(c)


# ── Auditoría, SoD y avisos ──────────────────────────────────────────────────

def auditar(db: Session, usuario, accion: str, que: str, id_: Optional[str], nombre: Optional[str] = None,
            antes: Optional[dict] = None, despues: Optional[dict] = None, meta: Optional[dict] = None) -> None:
    """Cada cambio del módulo queda en el registro de auditoría encadenado (recurso `certificaciones`)."""
    from app.services.audit import audit_log
    audit_log(db, usuario, accion, RECURSO, id_, f"{que}:{nombre or id_ or ''}"[:255],
              old_values=antes, new_values=despues, metadata={"entidad": que, **(meta or {})})


def exigir_segregacion(db: Session, usuario, otro_id: Optional[str], codigo: str, entidad: str, entidad_id: str) -> None:
    """SoD del módulo: `usuario` no puede ser `otro_id`. 403 con código y la infracción queda registrada."""
    if not otro_id or otro_id != usuario.id:
        return
    try:
        from app.services.grc_sod import record_self_approval_violation_for_request
        rol = getattr(getattr(usuario, "role", None), "value", getattr(usuario, "role", None))
        record_self_approval_violation_for_request(db, "certificaciones", str(entidad_id), otro_id, usuario.id, rol,
                                                   organization_id=usuario.organization_id,
                                                   context_type=f"certificaciones.{entidad}")
        auditar(db, usuario, "SOD_BLOCKED", entidad, entidad_id, meta={"regla": codigo})
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Certificaciones: no se pudo registrar la infracción SoD %s", codigo, exc_info=True)
    raise error(403, codigo)


def avisar(db: Session, user_id: Optional[str], clave: str, ref: str, id_: str, url: str, **params) -> None:
    """Aviso en la aplicación en el idioma de quien lo recibe (no rompe el flujo si falla)."""
    if not user_id:
        return
    try:
        from app.services.notifications import notify_user
        notify_user(db, user_id, "system", ref, None, RECURSO, id_, url,
                    aviso={"titulo": f"cert.aviso.{clave}", "cuerpo": f"cert.aviso.{clave}_cuerpo",
                           "params": {"ref": ref, **params}})
    except Exception:
        logger.warning("Certificaciones: no se pudo avisar a %s (%s)", user_id, clave, exc_info=True)


def siguiente_codigo(db: Session, modelo, org: str, prefijo: str) -> str:
    """PREFIJO-0001 por empresa (cuenta las filas; el único por empresa evita choques)."""
    from sqlalchemy import func
    n = db.query(func.count(modelo.id)).filter(modelo.organization_id == org).scalar() or 0
    while True:
        n += 1
        codigo = f"{prefijo}-{n:04d}"
        if db.query(modelo.id).filter(modelo.organization_id == org, modelo.codigo == codigo).first() is None:
            return codigo
