"""Turnos, rotaciones, cambios por día, festivos y cobertura (el cuadrante).

- Un TURNO tiene horario (puede cruzar la medianoche), días de la semana en que
  opera, equipo/departamento/oficina y cuántas personas hacen falta
  (`personas_requeridas`: la cobertura mínima). Si no `trabaja_festivos`, un
  festivo de la empresa (o de su país, `Holiday.applies_to`) no opera.
- Una ROTACIÓN (`PatronDeTurnos`) es un ciclo de N días (turno o libre por
  día) que empieza en `inicio`; cada persona entra con un `desfase` (para que
  rote escalonada) y unas fechas.
- Un CAMBIO (`AsignacionDeTurno`) fija el turno (o libre) de una persona un
  día y manda sobre la rotación y sobre el festivo.

`efectivo` calcula el turno de cada persona y día. Quien no tiene cuadrante en
un periodo trabaja según su jornada (rev. 180: `app/services/horario`, la única
fuente del horario efectivo de una persona en un día).

Rev. 180: un turno puede ser PARTIDO (`tramos`: [[inicio, fin], …]) y tener una
pausa no retribuida (`pausa_minutos`); sus horas son las de los tramos menos la
pausa. Los festivos valen por SEDE: los de la empresa, los de la sede de la
persona (o la del turno) y los de su país/ciudad.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, time, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.ausencias import AsignacionDeTurno, MiembroDePatron, PatronDeTurnos, Turno
from app.services.horario import tramos as tr

MAX_DIAS_DE_CUADRANTE = 120
MAX_CICLO = 366


def _json(v, defecto):
    try:
        return json.loads(v) if v else defecto
    except ValueError:
        return defecto


def _org(db: Session, usuario=None) -> Optional[str]:
    return getattr(usuario, "organization_id", None) or (db.info or {}).get("organization_id")


def _fecha(v, nombre: str) -> date:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        raise ErrorDeDominio(422, f"Fecha no válida en «{nombre}»: {v}")


def _hora(v, nombre: str) -> time:
    if isinstance(v, time):
        return v
    try:
        h, m = str(v).split(":")[:2]
        return time(int(h), int(m))
    except (TypeError, ValueError):
        raise ErrorDeDominio(422, f"Hora no válida en «{nombre}» (HH:MM): {v}")


def dias(desde: date, hasta: date) -> list[date]:
    return [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]


def _rango(desde: date, hasta: date) -> None:
    if hasta < desde:
        raise ErrorDeDominio(422, "La fecha final es anterior a la inicial")
    if (hasta - desde).days + 1 > MAX_DIAS_DE_CUADRANTE:
        raise ErrorDeDominio(422, f"Como mucho {MAX_DIAS_DE_CUADRANTE} días de una vez")


# ── Turnos ───────────────────────────────────────────────────────────────────

def tramos_de_turno(t: Turno) -> tuple:
    """Los tramos del turno (partido: los suyos; si no, inicio–fin, cruzando la medianoche si toca)."""
    lista = _json(getattr(t, "tramos", None), [])
    if lista:
        try:
            return tr.de_lista(lista)
        except ValueError:
            pass
    return (tr.desde_texto(t.hora_inicio, t.hora_fin),)


def duracion_horas(t: Turno) -> float:
    """Horas de trabajo del turno: sus tramos menos la pausa no retribuida."""
    bruto = tr.total_horas(tramos_de_turno(t))
    return round(max(0.0, bruto - (int(getattr(t, "pausa_minutos", 0) or 0)) / 60), 2)


def turno_dict(t: Turno) -> dict:
    tramos = tramos_de_turno(t)
    return {"id": t.id, "nombre": t.nombre, "color": t.color, "hora_inicio": t.hora_inicio.strftime("%H:%M"),
            "hora_fin": t.hora_fin.strftime("%H:%M"), "cruza_medianoche": any(x.fin > tr.DIA for x in tramos),
            "tramos": tr.a_lista(tramos), "partido": len(tramos) > 1,
            "pausa_minutos": int(getattr(t, "pausa_minutos", 0) or 0),
            "duracion_horas": duracion_horas(t), "dias_semana": _json(t.dias_semana, []), "equipo": t.equipo,
            "departamento": t.departamento, "office_id": t.office_id,
            "personas_requeridas": t.personas_requeridas, "trabaja_festivos": bool(t.trabaja_festivos),
            "activo": bool(t.activo), "orden": t.orden}


def turnos(db: Session, *, incluir_inactivos: bool = False) -> list[Turno]:
    q = db.query(Turno)
    if not incluir_inactivos:
        q = q.filter(Turno.activo.is_(True))
    return q.order_by(Turno.orden, Turno.hora_inicio, Turno.nombre).all()


def turno(db: Session, turno_id: str) -> Turno:
    t = db.query(Turno).filter(Turno.id == turno_id).first()
    if t is None:
        raise ErrorDeDominio(404, "Turno no encontrado")
    return t


def guardar_turno(db: Session, usuario, datos: dict, turno_id: Optional[str] = None) -> dict:
    from app.models.advanced_config import Office
    t = turno(db, turno_id) if turno_id else Turno(id=str(uuid.uuid4()), organization_id=_org(db, usuario))
    nombre = (datos.get("nombre") or "").strip()
    if not nombre:
        raise ErrorDeDominio(422, "El turno necesita un nombre")
    dias_semana = sorted({int(d) for d in datos.get("dias_semana") or []})
    if any(d < 1 or d > 7 for d in dias_semana):
        raise ErrorDeDominio(422, "Días de la semana del 1 (lunes) al 7 (domingo)")
    tramos_in = [x for x in (datos.get("tramos") or []) if x and (x[0] or x[1])]
    if tramos_in:
        try:
            tramos = tr.de_lista(tramos_in)
        except (ValueError, TypeError, IndexError) as exc:
            raise ErrorDeDominio(422, f"Tramos del turno no válidos: {exc}")
        if tramos[-1].fin - tramos[0].inicio > tr.DIA:
            raise ErrorDeDominio(422, "Un turno no puede durar más de un día")
        inicio, fin = _hora(tr.hhmm(tramos[0].inicio), "inicio"), _hora(tr.hhmm(tramos[-1].fin), "fin")
    else:
        inicio, fin = _hora(datos.get("hora_inicio"), "inicio"), _hora(datos.get("hora_fin"), "fin")
        if inicio == fin:
            raise ErrorDeDominio(422, "El turno empieza y acaba a la misma hora")
        tramos = (tr.desde_texto(inicio, fin),)
    pausa = int(datos.get("pausa_minutos") or 0)
    if pausa < 0 or pausa >= tr.total_horas(tramos) * 60:
        raise ErrorDeDominio(422, "La pausa tiene que ser menor que la duración del turno")
    requeridas = int(datos.get("personas_requeridas") or 0)
    if requeridas < 0:
        raise ErrorDeDominio(422, "Las personas requeridas no pueden ser negativas")
    if datos.get("office_id") and db.query(Office.id).filter(Office.id == datos["office_id"]).first() is None:
        raise ErrorDeDominio(422, "Esa oficina no existe")
    t.nombre, t.color = nombre[:80], datos.get("color") or t.color or "#4f8cff"
    t.hora_inicio, t.hora_fin = inicio, fin
    t.tramos = json.dumps(tr.a_lista(tramos)) if len(tramos) > 1 else None
    t.pausa_minutos = pausa
    t.dias_semana = json.dumps(dias_semana) if dias_semana else None
    t.equipo = (datos.get("equipo") or None)
    t.departamento = (datos.get("departamento") or None)
    t.office_id = datos.get("office_id") or None
    t.personas_requeridas = requeridas
    t.trabaja_festivos = bool(datos.get("trabaja_festivos"))
    t.activo = bool(datos.get("activo", True))
    t.orden = int(datos.get("orden") if datos.get("orden") is not None else (t.orden or 100))
    if turno_id is None:
        db.add(t)
    db.commit()
    return turno_dict(t)


def borrar_turno(db: Session, usuario, turno_id: str) -> dict:
    """En uso (cuadrante, rotación o ausencia) se desactiva; si no, se borra."""
    from app.models.resources import Absence
    t = turno(db, turno_id)
    en_rotacion = any(t.id in (_json(p.ciclo, []) or []) for p in db.query(PatronDeTurnos).all())
    en_uso = en_rotacion or db.query(AsignacionDeTurno.id).filter(AsignacionDeTurno.turno_id == t.id).first() \
        or db.query(Absence.id).filter(Absence.shift_id == t.id).first()
    if en_uso:
        t.activo = False
        resultado = {"desactivado": True}
    else:
        db.delete(t)
        resultado = {"eliminado": True}
    db.commit()
    return resultado


# ── Festivos ─────────────────────────────────────────────────────────────────

def festivos(db: Session, desde: date, hasta: date) -> list:
    from app.models.settings import Holiday
    return db.query(Holiday).filter(Holiday.date >= desde, Holiday.date <= hasta).all()


def _festivo_para(festivos_del_dia: list, pais_de_oficina: Optional[str]) -> bool:
    """Un festivo sin `applies_to` vale para todos; con él, solo para ese país u oficina."""
    for h in festivos_del_dia:
        destino = (h.applies_to or "").strip().upper()
        if not destino or (pais_de_oficina and destino == pais_de_oficina.upper()):
            return True
    return False


def _paises_de_oficinas(db: Session) -> dict:
    from app.models.advanced_config import Office
    return {o.id: (o.country or o.name or "") for o in db.query(Office).all()}


def _oficinas(db: Session) -> dict:
    from app.models.advanced_config import Office
    return {o.id: o for o in db.query(Office).all()}


def _festivo_de_sede(festivos_del_dia: list, oficina) -> bool:
    """Festivo de la empresa, de esa sede o de su país/ciudad (rev. 180)."""
    from app.services.horario.efectivo import _festivo
    return _festivo(festivos_del_dia, oficina) is not None


def opera(t: Turno, d: date, festivos_por_dia: dict, paises: dict) -> bool:
    """Si el turno funciona ese día (días de la semana y festivos): cuenta su cobertura.

    `paises`: {office_id: Office} (rev. 180) o {office_id: país} (lo de antes)."""
    semana = _json(t.dias_semana, [])
    if semana and d.isoweekday() not in semana:
        return False
    if t.trabaja_festivos:
        return True
    oficina = paises.get(t.office_id)
    if oficina is not None and not isinstance(oficina, str):
        return not _festivo_de_sede(festivos_por_dia.get(d, []), oficina)
    return not _festivo_para(festivos_por_dia.get(d, []), oficina)


# ── Rotaciones ───────────────────────────────────────────────────────────────

def patron_dict(p: PatronDeTurnos) -> dict:
    return {"id": p.id, "nombre": p.nombre, "ciclo": _json(p.ciclo, []), "inicio": p.inicio.isoformat(),
            "activo": bool(p.activo),
            "miembros": [{"id": m.id, "user_id": m.user_id, "desde": m.desde.isoformat(),
                          "hasta": m.hasta.isoformat() if m.hasta else None, "desfase": m.desfase}
                         for m in sorted(p.miembros or [], key=lambda m: (m.desfase, m.desde))]}


def patrones(db: Session) -> list[PatronDeTurnos]:
    return db.query(PatronDeTurnos).order_by(PatronDeTurnos.nombre).all()


def patron(db: Session, patron_id: str) -> PatronDeTurnos:
    p = db.query(PatronDeTurnos).filter(PatronDeTurnos.id == patron_id).first()
    if p is None:
        raise ErrorDeDominio(404, "Rotación no encontrada")
    return p


def _solapan(a_desde, a_hasta, b_desde, b_hasta) -> bool:
    return a_desde <= (b_hasta or date.max) and b_desde <= (a_hasta or date.max)


def guardar_patron(db: Session, usuario, datos: dict, patron_id: Optional[str] = None) -> dict:
    from app.models.user import User
    p = patron(db, patron_id) if patron_id else PatronDeTurnos(id=str(uuid.uuid4()), organization_id=_org(db, usuario))
    nombre = (datos.get("nombre") or "").strip()
    if not nombre:
        raise ErrorDeDominio(422, "La rotación necesita un nombre")
    ciclo = list(datos.get("ciclo") or [])
    if not 1 <= len(ciclo) <= MAX_CICLO:
        raise ErrorDeDominio(422, f"El ciclo tiene de 1 a {MAX_CICLO} días")
    validos = {t.id for t in turnos(db, incluir_inactivos=True)}
    if any(x and x not in validos for x in ciclo):
        raise ErrorDeDominio(422, "El ciclo usa un turno que no existe")
    miembros = datos.get("miembros") or []
    for m in miembros:
        if db.query(User.id).filter(User.id == m.get("user_id")).first() is None:
            raise ErrorDeDominio(422, "Una persona de la rotación no existe en tu empresa")
        if m.get("hasta") and _fecha(m["hasta"], "hasta") < _fecha(m.get("desde"), "desde"):
            raise ErrorDeDominio(422, "Una persona sale de la rotación antes de entrar")
    # Una persona no puede estar en dos rotaciones activas a la vez.
    otros = db.query(MiembroDePatron).join(PatronDeTurnos, PatronDeTurnos.id == MiembroDePatron.patron_id).filter(
        PatronDeTurnos.activo.is_(True), MiembroDePatron.patron_id != p.id).all()
    for m in miembros:
        d0, d1 = _fecha(m.get("desde"), "desde"), _fecha(m["hasta"], "hasta") if m.get("hasta") else None
        for o in otros:
            if o.user_id == m["user_id"] and _solapan(d0, d1, o.desde, o.hasta):
                raise ErrorDeDominio(422, {"message": "Esa persona ya está en otra rotación en esas fechas",
                                           "errors": [f"user:{m['user_id']}"]})
    p.nombre, p.ciclo = nombre[:120], json.dumps([x or None for x in ciclo])
    p.inicio = _fecha(datos.get("inicio"), "inicio")
    p.activo = bool(datos.get("activo", True))
    if patron_id is None:
        db.add(p)
    p.miembros.clear()
    for m in miembros:
        p.miembros.append(MiembroDePatron(
            id=str(uuid.uuid4()), organization_id=p.organization_id, user_id=m["user_id"],
            desde=_fecha(m.get("desde"), "desde"), hasta=_fecha(m["hasta"], "hasta") if m.get("hasta") else None,
            desfase=int(m.get("desfase") or 0) % len(ciclo)))
    db.commit()
    return patron_dict(p)


def borrar_patron(db: Session, usuario, patron_id: str) -> None:
    db.delete(patron(db, patron_id))
    db.commit()


# ── Cambios por día ──────────────────────────────────────────────────────────

def asignar(db: Session, usuario, cambios: list[dict]) -> int:
    """Fija (o quita, `quitar: true`) el turno de personas en días: la pantalla
    manda los cambios al soltar o al pulsar en el cuadrante. `turno_id` vacío =
    libre ese día."""
    from app.models.user import User
    validos = {t.id for t in turnos(db, incluir_inactivos=True)}
    hechos = 0
    for c in cambios:
        uid, d = c.get("user_id"), _fecha(c.get("fecha"), "fecha")
        if db.query(User.id).filter(User.id == uid).first() is None:
            raise ErrorDeDominio(422, "Esa persona no existe en tu empresa")
        tid = c.get("turno_id") or None
        if tid and tid not in validos:
            raise ErrorDeDominio(422, "Ese turno no existe")
        fila = db.query(AsignacionDeTurno).filter(AsignacionDeTurno.user_id == uid, AsignacionDeTurno.fecha == d).first()
        if c.get("quitar"):
            if fila is not None:
                db.delete(fila)
                hechos += 1
            continue
        if fila is None:
            fila = AsignacionDeTurno(id=str(uuid.uuid4()), organization_id=_org(db, usuario), user_id=uid, fecha=d,
                                     created_by=usuario.id)
            db.add(fila)
        fila.turno_id, fila.nota = tid, (c.get("nota") or None)
        hechos += 1
    db.commit()
    return hechos


# ── El cuadrante efectivo ────────────────────────────────────────────────────

def plan_crudo(db: Session, desde: date, hasta: date, user_ids: Optional[Iterable[str]] = None) -> dict:
    """{(user_id, fecha): (turno_id | None, origen)} de rotaciones y cambios, SIN
    mirar festivos (eso lo hace el horario efectivo). origen = rotacion | cambio."""
    ids = set(user_ids) if user_ids is not None else None
    todos = {t.id: t for t in turnos(db, incluir_inactivos=True)}
    salida: dict = {}
    q = db.query(MiembroDePatron, PatronDeTurnos).join(PatronDeTurnos, PatronDeTurnos.id == MiembroDePatron.patron_id) \
        .filter(PatronDeTurnos.activo.is_(True), MiembroDePatron.desde <= hasta)
    if ids is not None:
        q = q.filter(MiembroDePatron.user_id.in_(ids))
    for m, p in q.all():
        if m.hasta and m.hasta < desde:
            continue
        ciclo = _json(p.ciclo, [])
        if not ciclo:
            continue
        for d in dias(max(desde, m.desde), min(hasta, m.hasta or hasta)):
            tid = ciclo[((d - p.inicio).days + (m.desfase or 0)) % len(ciclo)]
            t = todos.get(tid) if tid else None
            salida[(m.user_id, d)] = ((t.id if t is not None and t.activo else None), "rotacion")
    q = db.query(AsignacionDeTurno).filter(AsignacionDeTurno.fecha >= desde, AsignacionDeTurno.fecha <= hasta)
    if ids is not None:
        q = q.filter(AsignacionDeTurno.user_id.in_(ids))
    for a in q.all():
        salida[(a.user_id, a.fecha)] = (a.turno_id, "cambio")
    return salida


def efectivo(db: Session, desde: date, hasta: date, user_ids: Optional[Iterable[str]] = None) -> dict:
    """{(user_id, fecha): (turno_id | None, origen)}; origen = rotacion | cambio | festivo.

    Solo están las personas con cuadrante ese día (rotación o cambio). Un
    festivo de la sede de la persona (o del turno) deja libre la rotación si el
    turno no trabaja festivos.
    """
    from app.models.user import User
    ids = set(user_ids) if user_ids is not None else None
    todos = {t.id: t for t in turnos(db, incluir_inactivos=True)}
    por_dia: dict = {}
    for h in festivos(db, desde, hasta):
        por_dia.setdefault(h.date, []).append(h)
    oficinas = _oficinas(db) if por_dia else {}
    sedes: dict = {}
    if por_dia:
        q = db.query(User.id, User.office_id)
        if ids is not None:
            q = q.filter(User.id.in_(ids))
        sedes = dict(q.all())
    salida: dict = {}
    q = db.query(MiembroDePatron, PatronDeTurnos).join(PatronDeTurnos, PatronDeTurnos.id == MiembroDePatron.patron_id) \
        .filter(PatronDeTurnos.activo.is_(True), MiembroDePatron.desde <= hasta)
    if ids is not None:
        q = q.filter(MiembroDePatron.user_id.in_(ids))
    for m, p in q.all():
        if m.hasta and m.hasta < desde:
            continue
        ciclo = _json(p.ciclo, [])
        if not ciclo:
            continue
        for d in dias(max(desde, m.desde), min(hasta, m.hasta or hasta)):
            tid = ciclo[((d - p.inicio).days + (m.desfase or 0)) % len(ciclo)]
            t = todos.get(tid) if tid else None
            if t is None or not t.activo:
                salida[(m.user_id, d)] = (None, "rotacion")
            elif not t.trabaja_festivos and _festivo_de_sede(por_dia.get(d, []),
                                                             oficinas.get(sedes.get(m.user_id) or t.office_id)):
                salida[(m.user_id, d)] = (None, "festivo")
            else:
                salida[(m.user_id, d)] = (t.id, "rotacion")
    q = db.query(AsignacionDeTurno).filter(AsignacionDeTurno.fecha >= desde, AsignacionDeTurno.fecha <= hasta)
    if ids is not None:
        q = q.filter(AsignacionDeTurno.user_id.in_(ids))
    for a in q.all():
        salida[(a.user_id, a.fecha)] = (a.turno_id, "cambio")
    return salida


def dias_que_cuentan(db: Session, user_id: str, inicio: date, fin: date, turno_id: Optional[str] = None) -> list[dict]:
    """Los días de una ausencia que cuentan, con su turno, su sede y su horario.

    Rev. 180: salen del horario efectivo (`app/services/horario`): los días en
    que le toca trabajar (turno del cuadrante, jornada asignada o la de la
    empresa), sin festivos de su sede ni días fuera de contrato. Si se pide un
    turno, solo los de ese turno; sin cuadrante, los días en que ese turno opera
    (con su horario). Cada día lleva `tramos` (horario teórico), `horas` (las
    del horario menos la pausa) y `pausa_minutos`.
    """
    from app.services.horario import efectivo as hor
    plan = hor.horario(db, user_id, inicio, fin, estados_ausencia=None)
    todos = {t.id: t for t in turnos(db, incluir_inactivos=True)}
    t_pedido = todos.get(turno_id) if turno_id else None
    con_cuadrante = any(x.origen in ("rotacion", "cambio") for x in plan.values())
    por_dia: dict = {}
    oficinas: dict = {}
    if t_pedido is not None and not con_cuadrante:
        for h in festivos(db, inicio, fin):
            por_dia.setdefault(h.date, []).append(h)
        oficinas = _oficinas(db)
    from app.models.user import User
    sede = db.query(User.office_id).filter(User.id == user_id).scalar()
    salida: list[dict] = []
    for d in dias(inicio, fin):
        x = plan.get(d)
        if x is None:
            continue
        if t_pedido is not None and not con_cuadrante:
            if not opera(t_pedido, d, por_dia, oficinas) or x.fuera_de_contrato:
                continue
            tramos = tramos_de_turno(t_pedido)
            salida.append({"fecha": d, "turno": t_pedido.id, "office_id": sede or t_pedido.office_id,
                           "tramos": tramos, "horas": duracion_horas(t_pedido),
                           "pausa_minutos": int(t_pedido.pausa_minutos or 0)})
            continue
        if not x.laborable:
            continue
        if turno_id and x.turno_id != turno_id:
            continue
        oficina = sede or (todos[x.turno_id].office_id if x.turno_id in todos else None)
        salida.append({"fecha": d, "turno": x.turno_id, "office_id": oficina, "tramos": x.tramos,
                       "horas": round(x.horas_teoricas, 4), "pausa_minutos": x.pausa_minutos})
    return salida


def cuadrante(db: Session, desde: date, hasta: date, *, equipo: Optional[str] = None,
              departamento: Optional[str] = None, user_ids: Optional[list[str]] = None) -> dict:
    """El cuadrante para la pantalla: personas, días, celda por persona y día, festivos."""
    from app.models.user import User
    _rango(desde, hasta)
    q = db.query(User).filter(User.is_active.is_(True))
    if equipo:
        q = q.filter(User.team == equipo)
    if departamento:
        q = q.filter(User.department == departamento)
    if user_ids:
        q = q.filter(User.id.in_(user_ids))
    personas = q.order_by(User.full_name).all()
    plan = efectivo(db, desde, hasta, [u.id for u in personas])
    celdas: dict = {}
    for (uid, d), (tid, origen) in plan.items():
        celdas.setdefault(uid, {})[d.isoformat()] = {"turno_id": tid, "origen": origen}
    return {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "dias": [d.isoformat() for d in dias(desde, hasta)],
            "personas": [{"id": u.id, "nombre": u.full_name, "equipo": u.team, "departamento": u.department}
                         for u in personas],
            "celdas": celdas, "turnos": [turno_dict(t) for t in turnos(db)],
            "festivos": [{"fecha": h.date.isoformat(), "nombre": h.name, "ambito": h.applies_to}
                         for h in festivos(db, desde, hasta)]}


def cobertura(db: Session, desde: date, hasta: date, *, equipo: Optional[str] = None,
              departamento: Optional[str] = None, simular: Optional[dict] = None) -> dict:
    """Por día y turno: requeridas, asignadas, ausentes (aprobadas), pendientes,
    en espera y disponibles. `simular` = {"user_id", "dias": [{fecha, turno}]}
    resta además esa ausencia (la vista previa y el impacto para quien aprueba).
    """
    from app.models.resources import Absence, AbsenceStatus
    from app.models.user import User
    _rango(desde, hasta)
    lista = [t for t in turnos(db) if (not equipo or not t.equipo or t.equipo == equipo)
             and (not departamento or not t.departamento or t.departamento == departamento)]
    q = db.query(User.id, User.full_name).filter(User.is_active.is_(True))
    if equipo:
        q = q.filter(User.team == equipo)
    if departamento:
        q = q.filter(User.department == departamento)
    nombres = dict(q.all())
    plan = efectivo(db, desde, hasta, list(nombres))
    por_dia: dict = {}
    for h in festivos(db, desde, hasta):
        por_dia.setdefault(h.date, []).append(h)
    paises = _oficinas(db)
    ausencias = db.query(Absence.user_id, Absence.start_date, Absence.end_date, Absence.status, Absence.start_time).filter(
        Absence.is_active.is_(True), Absence.user_id.in_(list(nombres)), Absence.start_date <= hasta,
        Absence.end_date >= desde,
        Absence.status.in_([AbsenceStatus.approved, AbsenceStatus.pending, AbsenceStatus.waitlisted])).all()
    estado_de: dict = {}
    parciales: dict = {}
    for uid, ini, fin, st, hora in ausencias:
        st = getattr(st, "value", st)
        for d in dias(max(ini, desde), min(fin, hasta)):
            if hora is not None:
                # Rev. 180: una ausencia por horas no quita a la persona del turno entero.
                parciales.setdefault((uid, d), set()).add(st)
                continue
            previo = estado_de.get((uid, d))
            if previo != "approved":
                estado_de[(uid, d)] = st
    simulados = {(simular["user_id"], _fecha(x["fecha"], "fecha")) for x in (simular or {}).get("dias", [])
                 if not x.get("parcial")}
    celdas = []
    for d in dias(desde, hasta):
        for t in lista:
            asignados = [uid for uid in nombres if plan.get((uid, d), (None,))[0] == t.id]
            aprobadas = [uid for uid in asignados if estado_de.get((uid, d)) == "approved"]
            pendientes = [uid for uid in asignados if estado_de.get((uid, d)) == "pending"]
            espera = [uid for uid in asignados if estado_de.get((uid, d)) == "waitlisted"]
            requeridas = t.personas_requeridas if opera(t, d, por_dia, paises) else 0
            disponibles = len(asignados) - len(aprobadas)
            con_esta = disponibles - (1 if any((u, d) in simulados for u in asignados if u not in aprobadas) else 0)
            if not asignados and not requeridas:
                continue
            celdas.append({
                "fecha": d.isoformat(), "turno_id": t.id, "requeridas": requeridas, "asignadas": len(asignados),
                "ausentes": len(aprobadas), "pendientes": len(pendientes), "en_espera": len(espera),
                "disponibles": disponibles, "con_esta": con_esta if simular else None,
                "estado": "falta" if disponibles < requeridas else ("justo" if disponibles == requeridas and requeridas else "ok"),
                "parciales": sum(1 for u in asignados if (u, d) in parciales and u not in aprobadas),
                "ausentes_nombres": [nombres[u] for u in aprobadas],
                "pendientes_nombres": [nombres[u] for u in pendientes + espera],
            })
    return {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "turnos": [turno_dict(t) for t in lista],
            "celdas": celdas, "festivos": [{"fecha": h.date.isoformat(), "nombre": h.name} for h in festivos(db, desde, hasta)]}
