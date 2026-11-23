"""El contexto de una petición de horas extra para el motor de políticas (18-11-2026).

Cada clave es un campo del dominio `horas_extra`
(`app/services/politicas/dominios/horas_extra.py`). Solo lee. `_peticion`
lleva lo que la vista previa y la bandeja enseñan además de las reglas.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.services.horas_extra import calculo


def _rol(u):
    return str(getattr(getattr(u, "role", None), "value", getattr(u, "role", None)) or "") or None


def _inicio(p, m, zona=timezone.utc) -> datetime:
    """Cuándo empiezan: la franja, o el final de su horario, o las 00:00 del día.

    M23 (auditoría 22-11-2026): la franja es hora LOCAL de la persona; antes se
    tomaba como UTC y la antelación salía desplazada de 1 a 8 horas.
    """
    minutos = 0
    if p.hora_inicio is not None:
        minutos = p.hora_inicio.hour * 60 + p.hora_inicio.minute
    elif m["dia"] is not None and m["dia"].libres:
        minutos = max(t.fin for t in m["dia"].libres)
    local = datetime(p.fecha.year, p.fecha.month, p.fecha.day) + timedelta(minutes=minutos)
    return local.replace(tzinfo=zona).astimezone(timezone.utc)


def _zona(u):
    from app.core.timeutil import zone_for_user
    return zone_for_user(u) if u is not None else timezone.utc


def contexto(db: Session, p) -> dict:
    from app.models.advanced_config import Office
    from app.models.user import User
    from app.services.ausencias.reglas import grupos_de
    u = db.query(User).filter(User.id == p.user_id).first()
    m = medir_cache(db, p)
    rol = _rol(u)
    horas = float(p.horas or 0)
    acum = calculo.acumulados(db, p.user_id, p.fecha, horas, p.compensacion, excluir_id=p.id)
    restante, presupuestos = calculo.presupuesto_restante(db, u, p.fecha, p.project_id, horas, excluir_id=p.id)
    estado = calculo.estado_del_dia(db, p.user_id, p.fecha, 0, d=m["dia"])
    pedido = p.created_at if isinstance(p.created_at, datetime) else datetime.now(timezone.utc)
    if pedido.tzinfo is None:
        pedido = pedido.replace(tzinfo=timezone.utc)
    oficina = getattr(u, "office_id", None)
    o = db.query(Office).filter(Office.id == oficina).first() if oficina else None
    grupos = grupos_de(db, p.user_id)
    descanso = calculo.descanso(db, p.user_id, p.fecha, calculo.franja_de(p), horas)
    seguidos = calculo.dias_seguidos(db, p.user_id, p.fecha)
    return {
        "tipo": p.tipo, "origen": p.origen, "clase_dia": m["clase"], "fecha": p.fecha,
        "hora_inicio": p.hora_inicio.strftime("%H:%M") if p.hora_inicio else None,
        "hora_fin": p.hora_fin.strftime("%H:%M") if p.hora_fin else None,
        "horas": horas, "horas_fuera_de_horario": m["horas_fuera"], "horario_del_dia": m["horario_horas"],
        "imputado_del_dia": estado["imputado"], "exceso_imputado": estado["exceso_real"],
        "horas_en_dia": acum["dia"], "horas_en_semana": acum["semana"], "horas_en_mes": acum["mes"],
        "horas_en_anio": acum["anio"], "horas_en_anio_pago": acum["anio_pago"],
        "antelacion_horas": round((_inicio(p, m, _zona(u)) - pedido).total_seconds() / 3600, 2),
        "descanso_horas": descanso, "dias_seguidos": seguidos, "presupuesto_restante": restante,
        "compensacion": p.compensacion, "factor": float(p.factor or 1.0),
        "proyecto": p.project_id, "ticket": p.ticket_id, "motivo": p.motivo, "sustituto": p.sustituto_id,
        "persona": p.user_id, "pide_otro": bool(p.solicitante_id and p.solicitante_id != p.user_id),
        "rol": rol, "departamento": getattr(u, "department", None), "equipo": getattr(u, "team", None),
        "sede": oficina, "grupos": grupos, "tipo_de_contrato": getattr(u, "employment_type", None),
        "_sujeto": {"usuario_id": p.user_id, "rol": rol, "departamento": getattr(u, "department", None),
                    "equipo": getattr(u, "team", None), "grupos": grupos,
                    "pais": ((o.country or "").upper()[:2] or None) if o is not None else None,
                    "ciudad": (o.city or None) if o is not None else None},
        "_fecha": p.fecha,
        "_peticion": {"horario": {"horas": m["horario_horas"], "tramos": m["tramos"], "festivo": m["festivo"]},
                      "franja_horas": m["franja_horas"], "horas_dentro": m["horas_dentro"],
                      "acumulados": acum, "presupuestos": presupuestos},
    }


def medir_cache(db: Session, p) -> dict:
    """`calculo.medir` una vez por objeto (la vista previa y la evaluación lo piden a la vez)."""
    clave = (p.user_id, p.fecha, p.hora_inicio, p.hora_fin)
    previo = getattr(p, "_medida", None)
    if previo is not None and previo[0] == clave:
        return previo[1]
    m = calculo.medir(db, p)
    try:
        p._medida = (clave, m)
    except AttributeError:
        pass
    return m
