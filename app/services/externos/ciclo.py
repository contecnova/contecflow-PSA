"""Ciclo de vida del externo: alta, acceso, caducidad y baja.

- **Alta** (`crear_usuario`): toda persona externa tiene su `User` (rol
  `subcontractor`): es lo que la hace asignable, planificable y con coste. Con
  acceso, con contrasena temporal; sin acceso, sin credenciales (no entra, no
  puede pedir cambio de contrasena) y sus horas las registra el PM o se
  importan (parte manual). Despues, `alm_personas.al_crear` (kit de alta) y, si
  la empresa tiene publicado el proceso BPM `subcontractor_onboarding`, se
  arranca.
- **Acceso** (`acceso_vigente`): solo entra un externo activo, con acceso y
  sin pasar `access_until`. Lo comprueban el login, el cambio de contrasena y
  cada peticion (`deps.get_current_user`).
- **Caducidad** (`caducar_accesos`, diario): avisa al externo y a su
  responsable interno `EXTERNOS_AVISO_CADUCIDAD_DIAS` antes; el dia siguiente
  al fin quita el acceso y revoca sus sesiones. Tambien cierra las
  asignaciones vencidas (deja de ser miembro).
- **Baja** (`dar_de_baja`): termina sus asignaciones, abre la baja de ALM
  (`alm_personas.al_desactivar`: licencias y devolucion de equipos), desactiva
  el usuario y revoca sus sesiones.
"""
from __future__ import annotations

import logging
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)


def es_rol_externo(user) -> bool:
    from app.models.user import UserRole
    rol = getattr(user, "role", None)
    return getattr(rol, "value", rol) == UserRole.subcontractor.value


def trabajador_de_usuario(db: Session, user_id: str):
    from app.models.enterprise import SubcontractorWorker
    return db.query(SubcontractorWorker).filter(SubcontractorWorker.user_id == user_id).first()


def acceso_vigente(db: Session, user, hoy: Optional[date] = None) -> bool:
    """Un usuario externo solo entra con ficha activa, acceso y sin caducar.

    Un usuario de rol externo sin ficha de proveedor (creado a mano, de antes)
    conserva el acceso: lo gobierna su `is_active`, como siempre.
    """
    if not es_rol_externo(user):
        return True
    w = trabajador_de_usuario(db, user.id)
    if w is None:
        return True
    hoy = hoy or timeutil.today()
    return bool(w.is_active is not False and w.has_access
                and (w.access_until is None or w.access_until >= hoy))


def exigir_responsable(db: Session, owner_id: Optional[str]):
    """El responsable interno: obligatorio, de la empresa e interno."""
    from app.models.user import User
    if not owner_id:
        raise ErrorDeDominio(400, "El externo necesita un responsable interno.", code="externo_sin_responsable")
    owner = db.query(User).filter(User.id == owner_id, User.is_active == True).first()  # noqa: E712
    if owner is None or es_rol_externo(owner):
        raise ErrorDeDominio(400, "El responsable interno tiene que ser una persona interna activa.",
                             code="externo_responsable_no_valido")
    return owner


def _usuario_unico(db: Session, nombre: str, codigo: str) -> str:
    from app.models.user import User
    base = re.sub(r"[^a-z0-9]", ".", nombre.lower().strip())
    base = re.sub(r"\.{2,}", ".", base).strip(".") or "externo"
    base = f"{base}.{codigo.lower()}"
    username, n = base, 0
    while db.query(User).filter(User.username == username).first():
        n += 1
        username = f"{base}{n}"
    return username


def crear_usuario(db: Session, sub, datos: dict, actor, con_acceso: bool):
    """Crea el `User` del externo. Devuelve (user, contrasena temporal o None)."""
    from app.core.security import get_password_hash
    from app.services.settings_service import por_empresa as _pe
    from app.models.user import User, UserRole, UserStatus
    username = _usuario_unico(db, datos["name"], sub.code)
    email = datos.get("email")
    # M102 (auditoría 22-11-2026): un correo que ya usa otra persona es un error
    # (antes se sustituía en silencio por uno inventado y quedaban dos fichas de
    # la misma persona, una sin poder recibir avisos). Sin correo, el técnico.
    if email and db.query(User).filter(User.email == email).first():
        from app.core.codigos_de_error import error
        raise error(409, "email_ya_registrado")
    if not email:
        email = f"{username}@subcontractor.internal"
    partes = datos["name"].strip().split(" ", 1)
    temporal = secrets.token_urlsafe(12) if con_acceso else None
    user = User(
        username=username, email=email, full_name=datos["name"], first_name=partes[0],
        last_name=partes[1] if len(partes) > 1 else None, job_title=datos.get("role"),
        department=sub.name, role=UserRole.subcontractor, status=UserStatus.active,
        # 18-11-2026: sin horas, la capacidad semanal de la empresa del externo.
        weekly_capacity_hours=datos.get("weekly_capacity_hours") or _pe.capacidad_semanal_de_empresa(db, registro=sub),
        hourly_rate=datos.get("cost_rate"), currency=datos.get("currency") or sub.currency,
        phone=datos.get("phone"), is_active=True, organization_id=actor.organization_id,
        manager_id=datos.get("internal_owner_id"),
        hashed_password=get_password_hash(temporal) if temporal else None,
        # M102: la contraseña temporal se cambia al primer acceso (estándar de
        # alta de cuentas: la que viaja en la respuesta no sirve más que una vez).
        password_must_change=bool(temporal),
    )
    db.add(user)
    db.flush()
    return user, temporal


def dar_acceso(db: Session, worker) -> Optional[str]:
    """Activa el acceso de un externo que no lo tenia: contrasena temporal nueva."""
    from app.core.security import get_password_hash
    from app.models.user import User
    user = db.get(User, worker.user_id) if worker.user_id else None
    if user is None:
        return None
    temporal = secrets.token_urlsafe(12)
    user.hashed_password = get_password_hash(temporal)
    user.password_must_change = True   # M102
    return temporal


def revocar_sesiones(db: Session, user_id: str) -> int:
    """M102 (auditoría 22-11-2026): la revocación común
    (`auth_service.revocar_sesiones_del_usuario`, con motivo), no una copia."""
    from app.services.auth_service.tokens_y_cookies import revocar_sesiones_del_usuario
    return revocar_sesiones_del_usuario(db, user_id, "external_access_revoked")


def al_dar_de_alta(db: Session, user, actor) -> None:
    from app.services.alm_integracion import personas as alm_personas
    alm_personas.al_crear(db, user, actor)


def arrancar_proceso(db: Session, clave: str, actor, variables: dict) -> Optional[str]:
    """Arranca el proceso BPM `clave` si la empresa lo tiene publicado. Nunca
    corta la operacion que lo dispara. Devuelve el id de la instancia."""
    from app.models.bpmn_process import BPMNProcess, BPMNProcessStatus
    try:
        proc = db.query(BPMNProcess).filter(
            BPMNProcess.key == clave, BPMNProcess.status == BPMNProcessStatus.published,
            BPMNProcess.is_active == True,  # noqa: E712
        ).first()
        if proc is None:
            return None
        from app.services.bpmn_engine import iniciar
        return iniciar(db, proc, actor, variables).id
    except Exception:
        db.rollback()
        logger.exception("externos: no se pudo arrancar el proceso BPM %s", clave)
        return None


def dar_de_baja(db: Session, worker, actor, motivo: str = "fin_contrato") -> None:
    """Baja completa del externo (no confirma: lo hace quien llama)."""
    from app.models.enterprise import SubcontractorAssignment
    from app.models.user import User
    from app.services.alm_integracion import personas as alm_personas
    from app.services.audit import audit_log
    from app.services.externos.asignaciones import terminar
    for a in db.query(SubcontractorAssignment).filter(
            SubcontractorAssignment.worker_id == worker.id,
            SubcontractorAssignment.is_active == True).all():  # noqa: E712
        terminar(db, a, None, actor, auditar=False)
    worker.is_active = False
    worker.has_access = False
    user = db.get(User, worker.user_id) if worker.user_id else None
    if user is not None and user.is_active:
        alm_personas.al_desactivar(db, user, motivo, actor, tolerante=True)
        user.is_active = False
        revocar_sesiones(db, user.id)
    audit_log(db, actor, "DEACTIVATE", "subcontractor_workers", worker.id, worker.name)


def caducar_accesos(db: Session, org_id: Optional[str] = None, hoy: Optional[date] = None) -> dict:
    """Trabajo diario: avisos previos, accesos caducados y asignaciones vencidas."""
    from app.models.enterprise import SubcontractorAssignment, SubcontractorWorker
    from app.services.audit import audit_log
    from app.services.externos.asignaciones import terminar
    from app.services.notifications import notify_user
    from app.services.settings_service import get_runtime_int
    hoy = hoy or timeutil.today()
    dias = int(get_runtime_int(db, "EXTERNOS_AVISO_CADUCIDAD_DIAS", org_id) or 14)
    avisados = caducados = cerradas = 0
    activos = db.query(SubcontractorWorker).filter(
        SubcontractorWorker.is_active == True, SubcontractorWorker.has_access == True,  # noqa: E712
        SubcontractorWorker.access_until.isnot(None)).all()
    for w in activos:
        if w.access_until < hoy:
            w.has_access = False
            if w.user_id:
                revocar_sesiones(db, w.user_id)
            audit_log(db, None, "UPDATE", "subcontractor_workers", w.id, f"{w.name}: acceso caducado")
            if w.internal_owner_id:
                notify_user(db, w.internal_owner_id, "system",
                            f"Acceso de {w.name} caducado", f"Fin de acceso: {w.access_until}.",
                            resource="subcontractor_workers", resource_id=w.id, action_url="/subcontractors")
            caducados += 1
        elif w.access_until <= hoy + timedelta(days=dias) and w.access_expiry_notified_at is None:
            for uid in {w.user_id, w.internal_owner_id} - {None}:
                notify_user(db, uid, "system",
                            f"El acceso de {w.name} caduca el {w.access_until}",
                            "Si el contrato se amplia, el responsable interno debe ampliar el fin de acceso.",
                            resource="subcontractor_workers", resource_id=w.id, action_url="/subcontractors")
            w.access_expiry_notified_at = hoy
            avisados += 1
    for a in db.query(SubcontractorAssignment).filter(
            SubcontractorAssignment.is_active == True,  # noqa: E712
            SubcontractorAssignment.end_date.isnot(None), SubcontractorAssignment.end_date < hoy).all():
        terminar(db, a, a.end_date, None)
        cerradas += 1
    return {"avisados": avisados, "caducados": caducados, "asignaciones_cerradas": cerradas}
