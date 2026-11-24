"""Cupos: como mucho N personas ausentes por (día × turno × grupo), sin carreras.

Un cupo es un resultado propio del dominio `ausencias` (`{"tipo": "cupo", …}`,
ver `politicas/dominios/ausencias.py`). Cada uno tiene una `clave` estable (la
pantalla la genera al crearlo y viaja con las versiones de la política), así
que sus plazas no se pierden al publicar una versión nueva.

Plazas (`huecos_de_cupo`): una fila por (empresa, clave, fecha, turno, grupo).
Quien ocupa o espera, en `reservas_de_cupo`, con `pedida_en` (el momento de la
petición: el orden de llegada).

Concurrencia (lo que impide que dos personas se lleven la última plaza):

1. La ausencia ya está guardada y confirmada; la reserva va en una transacción
   nueva.
2. Se crean las filas de plaza que falten con `INSERT … ON CONFLICT DO NOTHING`
   (dos peticiones a la vez no chocan por la clave única).
3. Se BLOQUEAN las filas: `SELECT … FOR UPDATE` en PostgreSQL, por id (siempre
   en el mismo orden: sin interbloqueos). En SQLite, que no tiene bloqueo de
   fila, un cerrojo del proceso más un `UPDATE` de la versión (que toma el
   cerrojo de escritura de la base): SQLite es solo para desarrollo y pruebas,
   un único proceso.
4. Con las filas bloqueadas se cuentan las reservas que ocupan (READ COMMITTED
   ve lo confirmado por quien soltó el bloqueo) y se decide.
5. Se confirma: el bloqueo se suelta.

Una petición es atómica: o tiene plaza en TODOS sus días/turnos/cupos, o espera
en todos (o se rechaza). Al liberarse una plaza se promueve, por orden de
llegada, la primera petición en espera que ya cabe entera.
"""
from __future__ import annotations

import threading
import uuid
from contextlib import contextmanager, nullcontext
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, or_, update
from sqlalchemy.orm import Session

from app.models.ausencias import HuecoDeCupo, ReservaDeCupo

TIPO = "cupo"
AGRUPACIONES = ("empresa", "equipo", "departamento", "ubicacion", "rol", "turno", "grupo")
MOMENTOS = ("solicitud", "aprobacion")

_CERROJO_SQLITE = threading.RLock()


def _dialecto(db: Session) -> str:
    return db.get_bind().dialect.name


@contextmanager
def seccion(db: Session):
    """La sección crítica de una reserva o promoción (ver cabecera, punto 3).

    Si algo falla dentro, se deshace la transacción ANTES de soltar el cerrojo:
    si no, la conexión seguía con el cerrojo de escritura de SQLite (o los
    `FOR UPDATE` de PostgreSQL) y las demás peticiones esperaban hasta
    «database is locked».
    """
    cerrojo = _CERROJO_SQLITE if _dialecto(db) == "sqlite" else nullcontext()
    with cerrojo:
        try:
            yield
        except BaseException:
            db.rollback()
            raise


def _fecha(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def huecos_de(cupo: dict, ausencia: dict) -> list[tuple]:
    """Las plazas que necesita una ausencia en un cupo: [(fecha, turno, grupo)].

    `ausencia` es `ctx["_ausencia"]` del dominio: usuario, equipo,
    departamento, rol, grupos y los días que cuentan con su turno y oficina.
    Agrupar por «grupo» solo aplica a quien está en ese grupo (si no, ninguna).

    Rev. 180 — cupo por FRANJA HORARIA (`franja_minutos` > 0): cada día se
    cuenta por franjas de ese tamaño; una ausencia ocupa solo las franjas que
    toca de su horario (`minutos` del día: [[inicio, fin], …]), así que dos
    personas con permiso de 9 a 11 y de 15 a 17 no compiten por la misma plaza.
    La franja viaja en el grupo («grupo@HH:MM»): la clave única no cambia.
    """
    from app.services.horario import tramos as tr
    agrupar = cupo.get("agrupar_por") or "empresa"
    por_turno = bool(cupo.get("por_turno")) or agrupar == "turno"
    tam = int(cupo.get("franja_minutos") or 0)
    if agrupar == "grupo" and cupo.get("grupo_id") not in (ausencia.get("grupos") or []):
        return []
    salida: list[tuple] = []
    for d in ausencia.get("dias") or []:
        turno = (d.get("turno") or "") if por_turno else ""
        grupo = {"empresa": "", "turno": "", "grupo": cupo.get("grupo_id") or "",
                 "equipo": ausencia.get("equipo") or "", "departamento": ausencia.get("departamento") or "",
                 "rol": ausencia.get("rol") or "", "ubicacion": d.get("office_id") or ""}[agrupar]
        grupo = str(grupo)[:150]
        claves = [grupo]
        if tam > 0 and d.get("minutos"):
            ocupa = [tr.Tramo(int(a), int(b)) for a, b in d["minutos"] if int(b) > int(a)]
            claves = [f"{grupo}@{tr.hhmm(f)}" for f in tr.franjas(ocupa, tam)] or [grupo]
        for g in claves:
            clave = (_fecha(d["fecha"]), turno, g[:160])
            if clave not in salida:
                salida.append(clave)
    return salida


def separar_grupo(g: str) -> tuple[Optional[str], Optional[str]]:
    """«grupo@HH:MM» → (grupo, franja)."""
    if not g:
        return None, None
    base, _, franja = g.partition("@")
    return (base or None), (franja or None)


def _filtro(clave: str, huecos: list[tuple]):
    return and_(HuecoDeCupo.clave == clave,
                or_(*[and_(HuecoDeCupo.fecha == f, HuecoDeCupo.turno == t, HuecoDeCupo.grupo == g) for f, t, g in huecos]))


def ocupacion(db: Session, clave: str, huecos: list[tuple], excluir: Optional[str] = None) -> list[dict]:
    """Lectura sin bloqueo (vista previa, evaluación, disponibilidad)."""
    if not huecos:
        return []
    filas = {(h.fecha, h.turno, h.grupo): h for h in db.query(HuecoDeCupo).filter(_filtro(clave, huecos)).all()}
    cuentas: dict = {}
    if filas:
        q = db.query(ReservaDeCupo.hueco_id, ReservaDeCupo.estado, func.count(ReservaDeCupo.id)).filter(
            ReservaDeCupo.hueco_id.in_([h.id for h in filas.values()]), ReservaDeCupo.estado.in_(("ocupa", "espera")))
        if excluir:
            q = q.filter(ReservaDeCupo.absence_id != excluir)
        for hid, estado, n in q.group_by(ReservaDeCupo.hueco_id, ReservaDeCupo.estado).all():
            cuentas[(hid, estado)] = n
    salida = []
    for f, t, g in huecos:
        h = filas.get((f, t, g))
        grupo, franja = separar_grupo(g)
        salida.append({"fecha": f.isoformat(), "turno": t or None, "grupo": grupo, "franja": franja,
                       "ocupadas": cuentas.get((h.id, "ocupa"), 0) if h else 0,
                       "espera": cuentas.get((h.id, "espera"), 0) if h else 0})
    return salida


def _asegurar(db: Session, org: Optional[str], clave: str, huecos: list[tuple], capacidad: int) -> None:
    # 24-11-2026 (migración 208): el insert de núcleo no pasa por el sellado del
    # flush; sin empresa (de la ausencia o de la sesión) se corta con el mismo
    # código que el sellado, en vez de un IntegrityError de NOT NULL.
    org = org or (getattr(db, "info", None) or {}).get("organization_id")
    if not org:
        from app.core.codigos_de_error import error
        raise error(500, "fila_sin_empresa", tabla="huecos_de_cupo")
    filas = [{"id": str(uuid.uuid4()), "organization_id": org, "clave": clave, "fecha": f, "turno": t, "grupo": g,
              "capacidad": capacidad, "ocupadas": 0, "version": 0} for f, t, g in huecos]
    if not filas:
        return
    if _dialecto(db) == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
        db.execute(insert(HuecoDeCupo.__table__).values(filas).on_conflict_do_nothing(constraint="uq_huecos_de_cupo"))
    else:
        from sqlalchemy.dialects.sqlite import insert
        db.execute(insert(HuecoDeCupo.__table__).values(filas).on_conflict_do_nothing())


def _bloquear(db: Session, pares: list[tuple]) -> list[HuecoDeCupo]:
    """Bloquea (y relee) las filas de plaza de [(clave, huecos)], por id."""
    q = db.query(HuecoDeCupo).filter(or_(*[_filtro(c, h) for c, h in pares if h])).order_by(HuecoDeCupo.id)
    if _dialecto(db) == "postgresql":
        filas = q.with_for_update().populate_existing().all()
    else:
        filas = q.populate_existing().all()
        if filas:
            db.execute(update(HuecoDeCupo).where(HuecoDeCupo.id.in_([h.id for h in filas]))
                       .values(version=HuecoDeCupo.version + 1))
    return filas


def _ocupan(db: Session, ids: list[str], excluir: Optional[str] = None) -> dict:
    q = db.query(ReservaDeCupo.hueco_id, func.count(ReservaDeCupo.id)).filter(
        ReservaDeCupo.hueco_id.in_(ids), ReservaDeCupo.estado == "ocupa")
    if excluir:
        q = q.filter(ReservaDeCupo.absence_id != excluir)
    return dict(q.group_by(ReservaDeCupo.hueco_id).all())


# ── Ausencias que ya existían (rev. 167) ─────────────────────────────────────
#
# Un cupo cuenta también las ausencias anteriores a él: cuando se crea la fila
# de una plaza (o se publica la política) se «siembran» sus reservas con las
# ausencias aprobadas —y pendientes, si la plaza se da al pedir— de ese día que
# encajan en el cupo (misma regla, mismo turno y grupo). Es idempotente: una
# ausencia que ya tiene reserva en esa plaza no se vuelve a contar.

def _estados_que_cuentan(cupo: dict) -> tuple:
    from app.models.resources import AbsenceStatus
    if (cupo.get("momento") or "solicitud") == "aprobacion":
        return (AbsenceStatus.approved,)
    return (AbsenceStatus.approved, AbsenceStatus.pending)


def _sembrar(db: Session, h: HuecoDeCupo, cupo: dict, excluir: Optional[str], org: Optional[str]) -> int:
    """Reservas `ocupa` para las ausencias existentes que caen en esta plaza. No confirma."""
    from app.models.resources import Absence
    from app.services import politicas
    ya = {a for (a,) in db.query(ReservaDeCupo.absence_id).filter(ReservaDeCupo.hueco_id == h.id)}
    q = db.query(Absence).filter(Absence.is_active.is_(True), Absence.status.in_(_estados_que_cuentan(cupo)),
                                 Absence.start_date <= h.fecha, Absence.end_date >= h.fecha)
    if excluir:
        q = q.filter(Absence.id != excluir)
    n = 0
    for a in q.all():
        if a.id in ya:
            continue
        ev = politicas.evaluar(db, "ausencias", a, organization_id=a.organization_id)
        mio = next((c for c in (ev["resultado"].get("propios") or [])
                    if c.get("tipo") == TIPO and c.get("clave") == cupo.get("clave")), None)
        if mio is None or (h.fecha, h.turno, h.grupo) not in huecos_de(mio, ev["contexto"].get("_ausencia") or {}):
            continue
        db.add(ReservaDeCupo(id=str(uuid.uuid4()), organization_id=org or a.organization_id, hueco_id=h.id,
                             absence_id=a.id, estado="ocupa", por_encima=False,
                             pedida_en=a.requested_at or a.created_at or ahora()))
        n += 1
    if n:
        db.flush()
    return n


def sembrar_politica(db: Session, politica: dict) -> int:
    """Al publicar una política con cupos: cuenta en ellos las ausencias que ya
    existen (de hoy en adelante). Confirma."""
    from app.core import timeutil
    from app.models.resources import Absence
    from app.services import politicas
    claves = {r.get("clave") for regla in politica.get("reglas") or [] for r in regla.get("resultados") or []
              if (r or {}).get("tipo") == TIPO and r.get("clave")}
    if not claves:
        return 0
    n = 0
    for a in db.query(Absence).filter(Absence.is_active.is_(True), Absence.end_date >= timeutil.today()).all():
        if getattr(a.status, "value", a.status) not in ("approved", "pending"):
            continue
        ev = politicas.evaluar(db, "ausencias", a, organization_id=a.organization_id)
        aus = ev["contexto"].get("_ausencia") or {}
        for c in ev["resultado"].get("propios") or []:
            if c.get("tipo") != TIPO or c.get("clave") not in claves:
                continue
            if getattr(a.status, "value", a.status) not in [getattr(x, "value", x) for x in _estados_que_cuentan(c)]:
                continue
            huecos = huecos_de(c, aus)
            if not huecos:
                continue
            with seccion(db):
                _asegurar(db, a.organization_id, c["clave"], huecos, int(c.get("maximo") or 0))
                for h in _bloquear(db, [(c["clave"], huecos)]):
                    if db.query(ReservaDeCupo.id).filter(ReservaDeCupo.hueco_id == h.id,
                                                         ReservaDeCupo.absence_id == a.id).first() is None:
                        db.add(ReservaDeCupo(id=str(uuid.uuid4()), organization_id=a.organization_id, hueco_id=h.id,
                                             absence_id=a.id, estado="ocupa", por_encima=False,
                                             pedida_en=a.requested_at or a.created_at or ahora()))
                        n += 1
                db.flush()
                for hid, k in _ocupan(db, [h.id for h in _bloquear(db, [(c["clave"], huecos)])]).items():
                    db.query(HuecoDeCupo).filter(HuecoDeCupo.id == hid).update({"ocupadas": k})
                db.commit()
    return n


def _si_lleno(cupo: dict) -> str:
    """Qué pasa si no hay plaza: `bloquear`, `esperar` o `exceder` (cupo blando)."""
    tipos = {(r or {}).get("tipo") for r in cupo.get("si_lleno") or []}
    if "block" in tipos:
        return "bloquear"
    if "waitlist" in tipos:
        return "esperar"
    return "exceder"


def reservar(db: Session, absence_id: str, pedida_en: datetime, peticiones: list[dict],
             org: Optional[str]) -> dict:
    """Reserva las plazas de una ausencia en todos sus cupos, o la pone en espera.

    `peticiones`: [{"cupo": {...resultado cupo...}, "huecos": [(fecha, turno, grupo)]}].
    Devuelve {"resultado": ocupa | espera | lleno | sin_cupo, "llenos": [...], "cupo": el que manda}.
    Confirma (commit).
    """
    peticiones = [p for p in peticiones if p["huecos"]]
    if not peticiones:
        return {"resultado": "sin_cupo", "llenos": []}
    with seccion(db):
        for p in peticiones:
            _asegurar(db, org, p["cupo"]["clave"], p["huecos"], int(p["cupo"].get("maximo") or 0))
        filas = _bloquear(db, [(p["cupo"]["clave"], p["huecos"]) for p in peticiones])
        por_clave = {(h.clave, h.fecha, h.turno, h.grupo): h for h in filas}
        # Plazas recién creadas (sin ninguna reserva): cuentan las ausencias que ya había.
        con_reservas = {hid for (hid,) in db.query(ReservaDeCupo.hueco_id).filter(
            ReservaDeCupo.hueco_id.in_([h.id for h in filas])).distinct()}
        for p in peticiones:
            for f, t, g in p["huecos"]:
                h = por_clave[(p["cupo"]["clave"], f, t, g)]
                if h.id not in con_reservas:
                    _sembrar(db, h, p["cupo"], absence_id, org)
                    con_reservas.add(h.id)
        ocupan = _ocupan(db, [h.id for h in filas], excluir=absence_id)
        llenos, peor = [], None
        for p in peticiones:
            maximo = int(p["cupo"].get("maximo") or 0)
            for f, t, g in p["huecos"]:
                h = por_clave[(p["cupo"]["clave"], f, t, g)]
                h.capacidad = maximo
                if ocupan.get(h.id, 0) >= maximo:
                    llenos.append({"clave": h.clave, "fecha": f.isoformat(), "turno": t or None, "grupo": g or None,
                                   "ocupadas": ocupan.get(h.id, 0), "maximo": maximo})
                    accion = _si_lleno(p["cupo"])
                    if peor is None or ("bloquear", "esperar", "exceder").index(accion) < \
                            ("bloquear", "esperar", "exceder").index(peor[0]):
                        peor = (accion, p["cupo"])
        if peor and peor[0] == "bloquear":
            db.commit()
            return {"resultado": "lleno", "llenos": llenos, "cupo": peor[1]}
        estado = "espera" if peor and peor[0] == "esperar" else "ocupa"
        for p in peticiones:
            for f, t, g in p["huecos"]:
                h = por_clave[(p["cupo"]["clave"], f, t, g)]
                existente = db.query(ReservaDeCupo).filter(ReservaDeCupo.hueco_id == h.id,
                                                           ReservaDeCupo.absence_id == absence_id).first()
                encima = estado == "ocupa" and ocupan.get(h.id, 0) >= int(p["cupo"].get("maximo") or 0)
                if existente is None:
                    db.add(ReservaDeCupo(id=str(uuid.uuid4()), organization_id=org, hueco_id=h.id,
                                         absence_id=absence_id, estado=estado, pedida_en=pedida_en, por_encima=encima))
                else:
                    existente.estado, existente.por_encima = estado, encima
                if estado == "ocupa":
                    ocupan[h.id] = ocupan.get(h.id, 0) + 1
                    h.ocupadas = ocupan[h.id]
        db.commit()
        return {"resultado": estado, "llenos": llenos, "cupo": peor[1] if peor else None}


def liberar(db: Session, absence_id: str) -> set:
    """Suelta las plazas (ocupadas o en espera) de una ausencia. Devuelve los
    huecos donde quedó una plaza libre. Confirma."""
    with seccion(db):
        reservas = db.query(ReservaDeCupo).filter(ReservaDeCupo.absence_id == absence_id,
                                                  ReservaDeCupo.estado.in_(("ocupa", "espera"))).all()
        libres = {r.hueco_id for r in reservas if r.estado == "ocupa"}
        if libres:
            _bloquear_ids(db, sorted(libres))
        for r in reservas:
            r.estado = "liberada"
        db.flush()
        for hid, n in _ocupan(db, list(libres)).items():
            db.query(HuecoDeCupo).filter(HuecoDeCupo.id == hid).update({"ocupadas": n})
        for hid in libres - set(_ocupan(db, list(libres))):
            db.query(HuecoDeCupo).filter(HuecoDeCupo.id == hid).update({"ocupadas": 0})
        db.commit()
    return libres


def _bloquear_ids(db: Session, ids: list[str]) -> list[HuecoDeCupo]:
    q = db.query(HuecoDeCupo).filter(HuecoDeCupo.id.in_(ids)).order_by(HuecoDeCupo.id)
    if _dialecto(db) == "postgresql":
        return q.with_for_update().populate_existing().all()
    filas = q.populate_existing().all()
    db.execute(update(HuecoDeCupo).where(HuecoDeCupo.id.in_(ids)).values(version=HuecoDeCupo.version + 1))
    return filas


def en_espera_en(db: Session, hueco_ids: Optional[set] = None) -> list[str]:
    """Ausencias en espera (en esos huecos, o en cualquiera), por orden de llegada."""
    q = db.query(ReservaDeCupo.absence_id, func.min(ReservaDeCupo.pedida_en)).filter(ReservaDeCupo.estado == "espera")
    if hueco_ids is not None:
        q = q.filter(ReservaDeCupo.hueco_id.in_(list(hueco_ids)))
    return [a for a, _ in q.group_by(ReservaDeCupo.absence_id).order_by(func.min(ReservaDeCupo.pedida_en),
                                                                         ReservaDeCupo.absence_id).all()]


def intentar_promover(db: Session, absence_id: str) -> bool:
    """Si una ausencia en espera ya cabe en TODAS sus plazas, pasa a ocuparlas. Confirma."""
    with seccion(db):
        reservas = db.query(ReservaDeCupo).filter(ReservaDeCupo.absence_id == absence_id,
                                                  ReservaDeCupo.estado == "espera").all()
        if not reservas:
            return False
        filas = {h.id: h for h in _bloquear_ids(db, sorted({r.hueco_id for r in reservas}))}
        ocupan = _ocupan(db, list(filas))
        if any(ocupan.get(hid, 0) >= filas[hid].capacidad for hid in filas):
            db.commit()
            return False
        for r in reservas:
            r.estado = "ocupa"
            filas[r.hueco_id].ocupadas = ocupan.get(r.hueco_id, 0) + 1
        db.commit()
        return True


def posicion(db: Session, absence_id: str) -> Optional[int]:
    """Puesto en la lista de espera (1 = la siguiente), el peor de sus plazas."""
    reservas = db.query(ReservaDeCupo).filter(ReservaDeCupo.absence_id == absence_id,
                                              ReservaDeCupo.estado == "espera").all()
    if not reservas:
        return None
    peor = 0
    for r in reservas:
        delante = db.query(func.count(ReservaDeCupo.id)).filter(
            ReservaDeCupo.hueco_id == r.hueco_id, ReservaDeCupo.estado == "espera",
            or_(ReservaDeCupo.pedida_en < r.pedida_en,
                and_(ReservaDeCupo.pedida_en == r.pedida_en, ReservaDeCupo.absence_id < r.absence_id))).scalar() or 0
        peor = max(peor, delante + 1)
    return peor


def reservas_de(db: Session, absence_id: str) -> list[dict]:
    filas = db.query(ReservaDeCupo).filter(ReservaDeCupo.absence_id == absence_id,
                                           ReservaDeCupo.estado != "liberada").all()
    return [{"clave": r.hueco.clave, "fecha": r.hueco.fecha.isoformat(), "turno": r.hueco.turno or None,
             "grupo": r.hueco.grupo or None, "estado": r.estado, "por_encima": bool(r.por_encima),
             "capacidad": r.hueco.capacidad} for r in filas]


def ahora() -> datetime:
    return datetime.now(timezone.utc)
