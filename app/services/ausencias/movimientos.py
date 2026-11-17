"""Ajustes de saldo (RRHH) y saldos por persona en días y horas (rev. 180).

Un ajuste suma o resta a un saldo (`vacaciones` o el id de un tipo con saldo
propio o bolsa), en su unidad, con fecha de efecto, caducidad opcional y nota.
Los de la bolsa (`origen = bolsa`) los escribe `ausencias/bolsa.py`: aquí no se
tocan a mano. Todo queda en la auditoría.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.codigos_de_error import error as error_con_codigo
from app.models.horario import MovimientoDeSaldo


def movimiento_dict(m: MovimientoDeSaldo) -> dict:
    return {"id": m.id, "user_id": m.user_id, "saldo_clave": m.saldo_clave, "fecha": m.fecha.isoformat(),
            "cantidad": m.cantidad, "unidad": m.unidad, "origen": m.origen, "referencia": m.referencia,
            "caduca": m.caduca.isoformat() if m.caduca else None, "nota": m.nota, "created_by": m.created_by,
            "created_at": m.created_at.isoformat() if m.created_at else None}


def listar(db: Session, user_id: str, saldo_clave: Optional[str] = None, limite: int = 500) -> list[dict]:
    q = db.query(MovimientoDeSaldo).filter(MovimientoDeSaldo.user_id == user_id)
    if saldo_clave:
        q = q.filter(MovimientoDeSaldo.saldo_clave == saldo_clave)
    return [movimiento_dict(m) for m in q.order_by(MovimientoDeSaldo.fecha.desc()).limit(limite).all()]


def _saldo_valido(db: Session, clave: str) -> str:
    """La unidad del saldo `clave` (error si no existe)."""
    from app.models.ausencias import TipoDeAusencia
    from app.services.ausencias import catalogo, saldos
    if clave == "vacaciones":
        tipo = next((t for t in catalogo.tipos(db) if t.descuenta_saldo and t.saldo == "vacaciones"), None)
    else:
        tipo = db.query(TipoDeAusencia).filter(TipoDeAusencia.id == clave, TipoDeAusencia.descuenta_saldo.is_(True),
                                               TipoDeAusencia.saldo.in_(("propio", "bolsa"))).first()
    if tipo is None:
        raise error_con_codigo(422, "saldo_no_existe")
    return saldos.unidad_de(saldos.gobernante(db, tipo))


def crear(db: Session, usuario, datos: dict) -> dict:
    from app.models.user import User
    from app.services.audit import audit_log
    uid = datos.get("user_id")
    if not uid or db.query(User.id).filter(User.id == uid).first() is None:
        raise error_con_codigo(422, "persona_no_existe_en_empresa")
    clave = str(datos.get("saldo_clave") or "")
    unidad = _saldo_valido(db, clave)
    try:
        cantidad = float(datos.get("cantidad"))
    except (TypeError, ValueError):
        raise error_con_codigo(422, "cantidad_no_numerica")
    if cantidad == 0:
        raise error_con_codigo(422, "cantidad_cero")
    fecha = datos.get("fecha") or timeutil.today()
    fecha = fecha if isinstance(fecha, date) else date.fromisoformat(str(fecha)[:10])
    caduca = datos.get("caduca")
    caduca = None if not caduca else (caduca if isinstance(caduca, date) else date.fromisoformat(str(caduca)[:10]))
    if caduca and caduca < fecha:
        raise error_con_codigo(422, "caduca_antes_de_empezar")
    nota = (datos.get("nota") or "").strip()
    if not nota:
        raise error_con_codigo(422, "ajuste_sin_motivo")
    m = MovimientoDeSaldo(id=str(uuid.uuid4()), organization_id=getattr(usuario, "organization_id", None), user_id=uid,
                          saldo_clave=clave, fecha=fecha, cantidad=cantidad, unidad=datos.get("unidad") or unidad,
                          origen="manual", caduca=caduca, nota=nota[:500], created_by=usuario.id)
    if m.unidad not in ("dias", "horas"):
        raise error_con_codigo(422, "unidad_de_saldo_no_valida")
    db.add(m)
    audit_log(db, usuario, "CREATE", "absence_balance_adjustment", m.id, None, new_values=movimiento_dict(m))
    db.commit()
    return movimiento_dict(m)


def borrar(db: Session, usuario, movimiento_id: str) -> None:
    from app.services.audit import audit_log
    m = db.query(MovimientoDeSaldo).filter(MovimientoDeSaldo.id == movimiento_id).first()
    if m is None:
        raise error_con_codigo(404, "ajuste_no_encontrado")
    if m.origen != "manual":
        raise error_con_codigo(422, "ajuste_de_bolsa_no_borrable")
    audit_log(db, usuario, "DELETE", "absence_balance_adjustment", m.id, None, old_values=movimiento_dict(m))
    db.delete(m)
    db.commit()


def saldos_de_personas(db: Session, viewer, ref: Optional[date] = None, user_ids: Optional[list[str]] = None,
                       equipo: Optional[str] = None, departamento: Optional[str] = None) -> list[dict]:
    """Los saldos de cada persona (en su unidad y su equivalente) para la pantalla de RRHH."""
    from app.models.user import User
    from app.services.ausencias import saldos
    from app.services.politica_de_visibilidad import ids_de_personas_visibles
    q = db.query(User).filter(User.is_active.is_(True))
    if user_ids:
        q = q.filter(User.id.in_(user_ids))
    if equipo:
        q = q.filter(User.team == equipo)
    if departamento:
        q = q.filter(User.department == departamento)
    visibles = ids_de_personas_visibles(db, viewer)
    if visibles is not None:
        q = q.filter(User.id.in_(visibles))
    return [{"user_id": u.id, "nombre": u.full_name, "equipo": u.team, "departamento": u.department,
             "saldos": saldos.todos(db, u.id, ref or timeutil.today())}
            for u in q.order_by(User.full_name).limit(500).all()]
