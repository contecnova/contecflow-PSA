"""Lecturas de horas extra: visibilidad, listas, ciclo completo, bandeja, resumen y nómina (18-11-2026).

Mínimo privilegio (la misma idea que `politica_de_visibilidad`):

- administración y RRHH (y el superadministrador) ven toda su empresa;
- un responsable ve a quien depende de él en su cadena (`manager_id`, hasta 10
  niveles) y, si es PM, las peticiones de los proyectos que dirige;
- quien tiene que aprobar (o ya votó) una solicitud ve ESA petición;
- el resto, empleado o subcontratado, solo lo suyo (y lo que pidió para otro).

A quien no ve, 404 (no se confirma que existe).
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.codigos_de_error import error as error_con_codigo
from app.models.horas_extra import EventoDeHorasExtra, PeticionDeHorasExtra
from app.services.horas_extra import calculo, config, solicitudes

CAMPOS_DE_LIMITE = ("horas_en_dia", "horas_en_semana", "horas_en_mes", "horas_en_anio", "horas_en_anio_pago")


def _rol(u) -> str:
    return str(getattr(getattr(u, "role", None), "value", getattr(u, "role", None)) or "")


def es_responsable(u) -> bool:
    return solicitudes.es_gestion(u) or _rol(u) in ("pm", "team_lead")


def subordinados(db: Session, usuario, niveles: int = 10) -> set[str]:
    from app.models.user import User
    hijos: dict = defaultdict(set)
    for uid, jefe in db.query(User.id, User.manager_id).filter(User.manager_id.isnot(None)).all():
        hijos[jefe].add(uid)
    salida, frontera = set(), {usuario.id}
    for _ in range(niveles):
        frontera = {h for f in frontera for h in hijos.get(f, ())} - salida - {usuario.id}
        if not frontera:
            break
        salida |= frontera
    return salida


def _proyectos_que_dirige(db: Session, usuario) -> set[str]:
    from app.models.project import Project
    if _rol(usuario) != "pm":
        return set()
    return {p for (p,) in db.query(Project.id).filter(Project.pm_id == usuario.id).all()}


def acotar(q, db: Session, usuario):
    """Filtra una consulta de peticiones a lo que este usuario puede ver."""
    if solicitudes.es_gestion(usuario):
        return q
    personas = subordinados(db, usuario) | {usuario.id}
    conds = [PeticionDeHorasExtra.user_id.in_(personas), PeticionDeHorasExtra.solicitante_id == usuario.id]
    proyectos = _proyectos_que_dirige(db, usuario)
    if proyectos:
        conds.append(PeticionDeHorasExtra.project_id.in_(proyectos))
    return q.filter(or_(*conds))


def _es_aprobador(db: Session, usuario, p) -> bool:
    from app.services.politicas import catalogo
    from app.services.politicas.servicio import _es_aprobador as es
    return es(db, usuario, catalogo.dominio("horas_extra"), p.id)


def visible(db: Session, usuario, peticion_id: str) -> PeticionDeHorasExtra:
    p = acotar(db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.id == peticion_id), db, usuario).first()
    if p is not None:
        return p
    p = db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.id == peticion_id).first()
    if p is not None and _es_aprobador(db, usuario, p):
        return p
    raise error_con_codigo(404, "horas_extra_no_encontrada")


def personas_visibles(db: Session, usuario) -> Optional[set[str]]:
    """None = todas (gestión)."""
    if solicitudes.es_gestion(usuario):
        return None
    return subordinados(db, usuario) | {usuario.id}


# ── Serializar ───────────────────────────────────────────────────────────────

def _nombres(db: Session, ids) -> dict:
    from app.models.user import User
    ids = {i for i in ids if i}
    return dict(db.query(User.id, User.full_name).filter(User.id.in_(ids)).all()) if ids else {}


def _proyectos(db: Session, ids) -> dict:
    from app.models.project import Project
    ids = {i for i in ids if i}
    return dict(db.query(Project.id, Project.name).filter(Project.id.in_(ids)).all()) if ids else {}


def _pendientes_en_bandeja(db: Session, ids) -> set:
    from app.models.billing_reports import ApprovalRequest
    ids = list({i for i in ids if i})
    if not ids:
        return set()
    return {e for (e,) in db.query(ApprovalRequest.entity_id).filter(
        ApprovalRequest.entity_type == solicitudes.TIPO_DE_APROBACION, ApprovalRequest.entity_id.in_(ids),
        ApprovalRequest.status == "pending").all()}


def serializar(db: Session, usuario, filas: list, reales: Optional[dict] = None) -> list[dict]:
    nombres = _nombres(db, [x for p in filas for x in (p.user_id, p.solicitante_id, p.sustituto_id, p.decidido_por,
                                                         p.liquidada_por)])
    proyectos = _proyectos(db, [p.project_id for p in filas])
    en_bandeja = _pendientes_en_bandeja(db, [p.id for p in filas])
    hoy = timeutil.today()
    gestion = solicitudes.es_gestion(usuario)
    subs = None
    salida = []
    for p in filas:
        try:
            msj = json.loads(p.avisos or "{}")
        except ValueError:
            msj = {}
        mia = usuario.id in (p.user_id, p.solicitante_id)
        if not mia and not gestion and subs is None:
            subs = subordinados(db, usuario)
        puede_revisar = p.estado == "pendiente" and not mia and (gestion or p.id in en_bandeja
                                                                 or p.user_id in (subs or set()))
        salida.append({
            "id": p.id, "user_id": p.user_id, "persona": nombres.get(p.user_id), "solicitante_id": p.solicitante_id,
            "solicitante": nombres.get(p.solicitante_id), "origen": p.origen, "tipo": p.tipo,
            "clase_dia": p.clase_dia, "fecha": p.fecha.isoformat(),
            "hora_inicio": p.hora_inicio.strftime("%H:%M") if p.hora_inicio else None,
            "hora_fin": p.hora_fin.strftime("%H:%M") if p.hora_fin else None, "horas": p.horas,
            "horas_autorizadas": p.horas_autorizadas,
            "horas_reales": (reales or {}).get((p.user_id, p.fecha)),
            "motivo": p.motivo, "project_id": p.project_id, "proyecto": proyectos.get(p.project_id),
            "ticket_id": p.ticket_id, "sustituto_id": p.sustituto_id, "sustituto": nombres.get(p.sustituto_id),
            "compensacion": p.compensacion, "factor": p.factor, "horas_ponderadas": calculo.horas_ponderadas(p),
            "estado": p.estado,
            "liquidacion": {"en": p.liquidada_en.isoformat(), "referencia": p.referencia_pago,
                            "por": nombres.get(p.liquidada_por)} if p.liquidada_en else None,
            "avisos": msj.get("avisos") or [], "bloqueos": msj.get("bloqueos") or [],
            "decidido_por": nombres.get(p.decidido_por),
            "decidido_en": p.decidido_en.isoformat() if p.decidido_en else None,
            "motivo_rechazo": p.motivo_rechazo, "created_at": p.created_at.isoformat() if p.created_at else None,
            "en_aprobacion": p.id in en_bandeja,
            "puede_cancelar": mia and (p.estado == "pendiente" or (p.estado == "aprobada" and p.fecha > hoy
                                                                    and p.liquidada_en is None)),
            "puede_editar": mia and p.estado == "pendiente" and p.origen == "previa",
            "puede_revisar": puede_revisar,
        })
    return salida


def _reales(db: Session, filas: list) -> dict:
    """Exceso real imputado (sobre su horario) de cada (persona, día) de las filas."""
    if not filas:
        return {}
    desde, hasta = min(p.fecha for p in filas), max(p.fecha for p in filas)
    if (hasta - desde).days > 400:
        return {}
    ids = {p.user_id for p in filas}
    return {(r["user_id"], r["fecha"]): r["exceso_real"] for r in calculo.excesos(db, desde, hasta, ids)}


# ── Listas ───────────────────────────────────────────────────────────────────

def _filtrar(q, filtros: dict):
    from app.models.user import User
    if filtros.get("desde"):
        q = q.filter(PeticionDeHorasExtra.fecha >= filtros["desde"])
    if filtros.get("hasta"):
        q = q.filter(PeticionDeHorasExtra.fecha <= filtros["hasta"])
    for campo in ("estado", "origen", "tipo", "compensacion", "user_id", "project_id"):
        if filtros.get(campo):
            q = q.filter(getattr(PeticionDeHorasExtra, campo) == filtros[campo])
    if filtros.get("equipo") or filtros.get("departamento"):
        q = q.join(User, User.id == PeticionDeHorasExtra.user_id)
        if filtros.get("equipo"):
            q = q.filter(User.team == filtros["equipo"])
        if filtros.get("departamento"):
            q = q.filter(User.department == filtros["departamento"])
    return q


def mias(db: Session, usuario, filtros: dict) -> list[dict]:
    q = db.query(PeticionDeHorasExtra).filter(or_(PeticionDeHorasExtra.user_id == usuario.id,
                                                  PeticionDeHorasExtra.solicitante_id == usuario.id))
    filas = _filtrar(q, filtros).order_by(PeticionDeHorasExtra.fecha.desc(), PeticionDeHorasExtra.created_at.desc()) \
        .limit(500).all()
    return serializar(db, usuario, filas, _reales(db, filas))


def listar(db: Session, usuario, filtros: dict) -> dict:
    q = acotar(db.query(PeticionDeHorasExtra), db, usuario)
    filas = _filtrar(q, filtros).order_by(PeticionDeHorasExtra.fecha.desc(), PeticionDeHorasExtra.created_at.desc()) \
        .limit(2000).all()
    items = serializar(db, usuario, filas, _reales(db, filas))
    vivas = [p for p in filas if p.estado in calculo.VIVOS]
    return {"items": items, "totales": {
        "peticiones": len(filas), "horas": round(sum(p.horas for p in filas), 2),
        "autorizadas": round(sum(calculo.horas_vivas(p) for p in vivas if p.estado == "aprobada"), 2),
        "pendientes": round(sum(p.horas for p in vivas if p.estado == "pendiente"), 2),
        "ponderadas_pago": round(sum(calculo.horas_ponderadas(p) for p in vivas
                                     if p.estado == "aprobada" and p.compensacion == "pago"), 2)}}


# ── El ciclo completo ────────────────────────────────────────────────────────

def _aprobacion(db: Session, p) -> Optional[dict]:
    from app.models.billing_reports import ApprovalRequest, FinancialApprovalAuditLog
    from app.services.approval_engine import pasos as _pasos
    req = db.query(ApprovalRequest).filter(ApprovalRequest.entity_type == solicitudes.TIPO_DE_APROBACION,
                                           ApprovalRequest.entity_id == p.id) \
        .order_by(ApprovalRequest.created_at.desc()).first()
    if req is None:
        return None
    pasos = _pasos.pasos_de(db, req)
    nombres = _nombres(db, [d.approver_id for d in req.decisions or []])
    escalados = db.query(FinancialApprovalAuditLog).filter(FinancialApprovalAuditLog.request_id == req.id,
                                                           FinancialApprovalAuditLog.action == "timeout") \
        .order_by(FinancialApprovalAuditLog.created_at).all()
    return {"id": req.id, "estado": req.status, "paso_actual": req.current_step,
            "pasos": [{"orden": s.step_order, "nombre": s.name, "tipo": getattr(s, "kind", None) or "approve",
                       "aprobador": s.approver_type, "rol": s.approver_role} for s in pasos],
            "decisiones": [{"orden": d.step_order, "decision": d.decision, "nota": d.note,
                            "quien": nombres.get(d.approver_id),
                            "cuando": d.decided_at.isoformat() if getattr(d, "decided_at", None) else None}
                           for d in sorted(req.decisions or [], key=lambda d: (d.step_order, str(d.id)))],
            "escalados": [{"accion": e.decision, "cuando": e.created_at.isoformat() if e.created_at else None,
                           "nota": e.note, "paso": e.step_order} for e in escalados]}


def _evaluaciones(db: Session, p) -> list[dict]:
    from app.models.politicas import EvaluacionDePolitica

    def _j(v, d):
        try:
            return json.loads(v) if v else d
        except ValueError:
            return d
    filas = db.query(EvaluacionDePolitica).filter(EvaluacionDePolitica.dominio == solicitudes.DOMINIO,
                                                  EvaluacionDePolitica.entidad_id == p.id) \
        .order_by(EvaluacionDePolitica.created_at.desc()).limit(20).all()
    return [{"momento": f.momento, "decision": f.decision, "resultado": _j(f.resultado, {}),
             "explicacion": (_j(f.explicacion, {}) or {}).get("politicas") or [],
             "created_at": f.created_at.isoformat() if f.created_at else None} for f in filas]


def detalle(db: Session, usuario, p) -> dict:
    from app.models.imputation import Imputation
    eventos = db.query(EventoDeHorasExtra).filter(EventoDeHorasExtra.peticion_id == p.id) \
        .order_by(EventoDeHorasExtra.created_at, EventoDeHorasExtra.id).all()
    nombres = _nombres(db, [e.actor_id for e in eventos])
    cfg = config.actual(db)
    d = calculo.dia(db, p.user_id, p.fecha)
    e = calculo.estado_del_dia(db, p.user_id, p.fecha, cfg["tolerancia_minutos"], d=d)
    imps = db.query(Imputation).filter(Imputation.user_id == p.user_id, Imputation.date == p.fecha,
                                       Imputation.is_active.is_(True)).all()
    proyectos = _proyectos(db, [i.project_id for i in imps])
    mov = None
    if p.compensacion == "bolsa" and cfg.get("tipo_bolsa_id"):
        from app.models.horario import MovimientoDeSaldo
        m = db.query(MovimientoDeSaldo).filter(MovimientoDeSaldo.user_id == p.user_id,
                                               MovimientoDeSaldo.saldo_clave == cfg["tipo_bolsa_id"],
                                               MovimientoDeSaldo.origen == "bolsa",
                                               MovimientoDeSaldo.fecha == p.fecha).first()
        mov = {"cantidad": m.cantidad, "fecha": m.fecha.isoformat()} if m else None
    ficha = serializar(db, usuario, [p], {(p.user_id, p.fecha): e["exceso_real"]})[0]
    from app.services.horario import tramos as tr
    return {
        "peticion": ficha,
        "linea_de_tiempo": [{"tipo": x.tipo, "quien": nombres.get(x.actor_id),
                             "cuando": x.created_at.isoformat() if x.created_at else None,
                             "datos": json.loads(x.datos or "{}")} for x in eventos],
        "evaluaciones": _evaluaciones(db, p),
        "aprobacion": _aprobacion(db, p),
        "dia": {"horario_horas": e["horario"], "tramos": tr.a_lista(d.libres) if d is not None else [],
                "festivo": d.festivo if d is not None else None, "imputado": e["imputado"],
                "exceso_real": e["exceso_real"], "autorizadas_del_dia": e["autorizadas"]},
        "imputaciones": [{"id": i.id, "proyecto": proyectos.get(i.project_id), "horas": i.hours,
                          "descripcion": i.description, "aprobada": bool(i.is_approved)} for i in imps],
        "compensacion": {"tipo": p.compensacion, "horas_ponderadas": calculo.horas_ponderadas(p),
                         "movimiento_bolsa": mov, "liquidacion": ficha["liquidacion"]},
        "puede_gestionar": solicitudes.es_gestion(usuario),
    }


# ── Bandeja ──────────────────────────────────────────────────────────────────

def bandeja(db: Session, usuario) -> list[dict]:
    """Lo que este usuario decide: solicitudes `overtime` en las que le toca el paso y, sin
    flujo, las pendientes de quien depende de él (RRHH y administración, todas)."""
    from app.services.approval_engine import fuentes
    from app.services.approval_engine.requests import get_pending_for_user
    filas, vistas = [], set()
    for req, paso in get_pending_for_user(db, usuario):
        if req.entity_type != solicitudes.TIPO_DE_APROBACION:
            continue
        p = db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.id == req.entity_id).first()
        if p is None or usuario.id in (p.user_id, p.solicitante_id):
            continue
        vistas.add(p.id)
        filas.append({"solicitud_id": req.id, "paso": paso.name, "p": p})
    if es_responsable(usuario):
        subs = None if solicitudes.es_gestion(usuario) else subordinados(db, usuario)
        for p in db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.estado == "pendiente").all():
            if p.id in vistas or usuario.id in (p.user_id, p.solicitante_id):
                continue
            if subs is not None and p.user_id not in subs:
                continue
            if fuentes.estado(db, solicitudes.TIPO_DE_APROBACION, p.id) == "pending":
                continue
            filas.append({"solicitud_id": None, "paso": None, "p": p})
    salida = []
    for x in filas:
        p = x["p"]
        acum = calculo.acumulados(db, p.user_id, p.fecha, calculo.horas_vivas(p), p.compensacion, excluir_id=p.id)
        from app.models.user import User
        u = db.query(User).filter(User.id == p.user_id).first()
        restante, _ = calculo.presupuesto_restante(db, u, p.fecha, p.project_id, calculo.horas_vivas(p), p.id)
        salida.append({"solicitud_id": x["solicitud_id"], "paso": x["paso"], "sin_flujo": x["solicitud_id"] is None,
                       "peticion": serializar(db, usuario, [p], _reales(db, [p]))[0],
                       "contexto": {"acumulados": acum, "presupuesto_restante": restante,
                                    "descanso_horas": calculo.descanso(db, p.user_id, p.fecha, calculo.franja_de(p),
                                                                       calculo.horas_vivas(p)),
                                    "dias_seguidos": calculo.dias_seguidos(db, p.user_id, p.fecha)}})
    return sorted(salida, key=lambda f: f["peticion"]["fecha"])


# ── Límites publicados, resumen, sin autorizar, nómina ───────────────────────

def _condiciones(nodo):
    if isinstance(nodo, dict):
        if nodo.get("tipo") == "condicion":
            yield nodo
        for h in nodo.get("hijos") or []:
            yield from _condiciones(h)


def limites_publicados(db: Session, org: Optional[str] = None) -> list[dict]:
    """Umbrales de las reglas PUBLICADAS sobre los acumulados (`horas_en_*` con > o ≥).

    Es una lectura de las reglas, no un límite propio: si una regla dice
    «Horas en el año (pagadas) > 80 → bloquear», el resumen enseña 80 como
    límite de ese campo con su efecto. Si hay varias, cuenta la menor.
    """
    from app.services.politicas import motor
    politicas, _ = motor.publicadas(db, org or (db.info or {}).get("organization_id"), solicitudes.DOMINIO)
    mejores: dict = {}
    for pol in politicas:
        for r in pol.get("reglas") or []:
            if r.get("activa") is False:
                continue
            tipos = [x.get("tipo") for x in r.get("resultados") or []]
            efecto = "block" if "block" in tipos else "warn" if "warn" in tipos else \
                "review" if "add_approval_levels" in tipos else "otro"
            for c in _condiciones(r.get("condicion")):
                if c.get("campo") in CAMPOS_DE_LIMITE and c.get("operador") in ("gt", "gte"):
                    try:
                        umbral = float(c.get("valor"))
                    except (TypeError, ValueError):
                        continue
                    previo = mejores.get(c["campo"])
                    if previo is None or umbral < previo["umbral"]:
                        mejores[c["campo"]] = {"campo": c["campo"], "umbral": umbral, "politica": pol.get("nombre"),
                                               "regla": r.get("nombre"), "efecto": efecto}
    return [mejores[k] for k in CAMPOS_DE_LIMITE if k in mejores]


def _consumo_de_persona(filas: list, fecha: date) -> dict:
    per = calculo._periodos(fecha)
    vivas = [p for p in filas if p.estado in calculo.VIVOS]
    salida = {}
    for campo, clave in (("horas_en_dia", "dia"), ("horas_en_semana", "semana"), ("horas_en_mes", "mes"),
                         ("horas_en_anio", "anio")):
        a, b = per[clave]
        if clave == "dia":
            # El peor día del periodo consultado (el límite diario se aplica a cada día).
            por_dia: dict = defaultdict(float)
            for p in vivas:
                por_dia[p.fecha] += calculo.horas_vivas(p)
            salida[campo] = round(max(por_dia.values() or [0.0]), 2)
            continue
        salida[campo] = round(sum(calculo.horas_vivas(p) for p in vivas if a <= p.fecha <= b), 2)
    a, b = per["anio"]
    salida["horas_en_anio_pago"] = round(sum(calculo.horas_vivas(p) for p in vivas
                                             if a <= p.fecha <= b and p.compensacion == "pago"), 2)
    return salida


def resumen(db: Session, usuario, desde: date, hasta: date, agrupar: str = "persona") -> dict:
    from app.models.user import User
    if agrupar not in ("persona", "equipo", "departamento", "proyecto"):
        agrupar = "persona"
    cfg = config.actual(db)
    q = acotar(db.query(PeticionDeHorasExtra), db, usuario).filter(PeticionDeHorasExtra.fecha >= desde,
                                                                   PeticionDeHorasExtra.fecha <= hasta)
    filas = q.all()
    visibles = personas_visibles(db, usuario)
    excesos = calculo.excesos(db, desde, hasta, visibles, cfg["tolerancia_minutos"])
    ids = {p.user_id for p in filas} | {e["user_id"] for e in excesos}
    usuarios = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()} if ids else {}
    proyectos = _proyectos(db, [p.project_id for p in filas])

    def clave_de(user_id, project_id=None):
        u = usuarios.get(user_id)
        if agrupar == "persona":
            return user_id, getattr(u, "full_name", None) or user_id
        if agrupar == "equipo":
            return getattr(u, "team", None) or "—", getattr(u, "team", None) or "—"
        if agrupar == "departamento":
            return getattr(u, "department", None) or "—", getattr(u, "department", None) or "—"
        return project_id or "—", proyectos.get(project_id) or "—"

    grupos: dict = {}

    def fila(k, etiqueta):
        return grupos.setdefault(k, {"clave": k, "etiqueta": etiqueta, "peticiones": 0, "horas_pedidas": 0.0,
                                     "horas_aprobadas": 0.0, "horas_pendientes": 0.0, "horas_rechazadas": 0.0,
                                     "horas_reales": 0.0, "horas_sin_autorizar": 0.0, "horas_pago": 0.0,
                                     "horas_bolsa": 0.0, "horas_ponderadas_pago": 0.0, "presupuesto": None,
                                     "limites": [], "_filas": []})
    for p in filas:
        g = fila(*clave_de(p.user_id, p.project_id))
        g["peticiones"] += 1
        g["horas_pedidas"] += p.horas
        g["_filas"].append(p)
        if p.estado == "aprobada":
            h = calculo.horas_vivas(p)
            g["horas_aprobadas"] += h
            if p.compensacion == "pago":
                g["horas_pago"] += h
                g["horas_ponderadas_pago"] += calculo.horas_ponderadas(p)
            elif p.compensacion == "bolsa":
                g["horas_bolsa"] += h
        elif p.estado == "pendiente":
            g["horas_pendientes"] += p.horas
        elif p.estado == "rechazada":
            g["horas_rechazadas"] += p.horas
    if agrupar != "proyecto":
        for e in excesos:
            g = fila(*clave_de(e["user_id"]))
            g["horas_reales"] += e["exceso_real"]
            g["horas_sin_autorizar"] += e["sin_autorizar"]
    limites = limites_publicados(db)
    pres = config.presupuestos(db, solo_activos=True)
    for k, g in grupos.items():
        if agrupar == "persona" and limites:
            # El acumulado anual cuenta todo el año de `hasta`, no solo el periodo consultado.
            anio = [p for p in db.query(PeticionDeHorasExtra).filter(
                PeticionDeHorasExtra.user_id == k, PeticionDeHorasExtra.fecha >= date(hasta.year, 1, 1),
                PeticionDeHorasExtra.fecha <= hasta).all()]
            consumo = _consumo_de_persona(anio, hasta)
            g["limites"] = [{**lim, "consumo": consumo.get(lim["campo"], 0.0),
                             "pct": round(100 * consumo.get(lim["campo"], 0.0) / lim["umbral"], 1)
                             if lim["umbral"] else None} for lim in limites]
        ambito = {"equipo": "equipo", "departamento": "departamento", "proyecto": "proyecto"}.get(agrupar)
        if ambito:
            p = next((x for x in pres if x.ambito == ambito and x.valor == k
                      and (x.anio is None or x.anio == hasta.year)), None)
            if p is not None:
                consumido = calculo.consumo_de(db, p, hasta)
                g["presupuesto"] = {"horas": p.horas, "restantes": round(p.horas - consumido, 2)}
        for c in ("horas_pedidas", "horas_aprobadas", "horas_pendientes", "horas_rechazadas", "horas_reales",
                  "horas_sin_autorizar", "horas_pago", "horas_bolsa", "horas_ponderadas_pago"):
            g[c] = round(g[c], 2)
        g.pop("_filas", None)
    return {"agrupar": agrupar, "filas": sorted(grupos.values(), key=lambda g: -g["horas_aprobadas"]),
            "limites_publicados": limites}


def sin_autorizar(db: Session, usuario, desde: date, hasta: date, user_id: Optional[str] = None) -> list[dict]:
    cfg = config.actual(db)
    visibles = personas_visibles(db, usuario)
    ids = visibles
    if user_id:
        if visibles is not None and user_id not in visibles:
            return []
        ids = {user_id}
    filas = [e for e in calculo.excesos(db, desde, hasta, ids, cfg["tolerancia_minutos"]) if e["sin_autorizar"] > 0]
    nombres = _nombres(db, [e["user_id"] for e in filas])
    return [{**e, "fecha": e["fecha"].isoformat(), "persona": nombres.get(e["user_id"])} for e in filas]


def nomina(db: Session, desde: date, hasta: date, liquidadas: Optional[bool] = None) -> list[dict]:
    q = db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.estado == "aprobada",
                                              PeticionDeHorasExtra.compensacion == "pago",
                                              PeticionDeHorasExtra.fecha >= desde, PeticionDeHorasExtra.fecha <= hasta)
    if liquidadas is True:
        q = q.filter(PeticionDeHorasExtra.liquidada_en.isnot(None))
    elif liquidadas is False:
        q = q.filter(PeticionDeHorasExtra.liquidada_en.is_(None))
    filas = q.order_by(PeticionDeHorasExtra.fecha, PeticionDeHorasExtra.user_id).all()
    nombres = _nombres(db, [x for p in filas for x in (p.user_id, p.liquidada_por)])
    reales = _reales(db, filas)
    return [{"id": p.id, "user_id": p.user_id, "persona": nombres.get(p.user_id), "fecha": p.fecha.isoformat(),
             "tipo": p.tipo, "horas_autorizadas": calculo.horas_vivas(p),
             "horas_reales": reales.get((p.user_id, p.fecha)), "factor": p.factor,
             "horas_ponderadas": calculo.horas_ponderadas(p),
             "liquidacion": {"en": p.liquidada_en.isoformat(), "referencia": p.referencia_pago,
                             "por": nombres.get(p.liquidada_por)} if p.liquidada_en else None} for p in filas]


def mis_datos(db: Session, user_id: str) -> list[dict]:
    """Todas las peticiones de la persona (RGPD acceso y portabilidad) con su línea de tiempo."""
    filas = db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.user_id == user_id) \
        .order_by(PeticionDeHorasExtra.fecha, PeticionDeHorasExtra.id).all()
    eventos: dict = defaultdict(list)
    if filas:
        for e in db.query(EventoDeHorasExtra).filter(EventoDeHorasExtra.peticion_id.in_([p.id for p in filas])) \
                .order_by(EventoDeHorasExtra.created_at).all():
            eventos[e.peticion_id].append({"tipo": e.tipo, "cuando": str(e.created_at)[:19] if e.created_at else None})
    return [{"fecha": str(p.fecha), "origen": p.origen, "tipo": p.tipo, "horas": p.horas,
             "horas_autorizadas": p.horas_autorizadas, "compensacion": p.compensacion, "factor": p.factor,
             "estado": p.estado, "motivo": p.motivo, "project_id": p.project_id,
             "hora_inicio": p.hora_inicio.strftime("%H:%M") if p.hora_inicio else None,
             "hora_fin": p.hora_fin.strftime("%H:%M") if p.hora_fin else None,
             "liquidada": str(p.liquidada_en)[:19] if p.liquidada_en else None,
             "eventos": eventos.get(p.id, [])} for p in filas]


def ultimos_dias(dias: int = 30) -> tuple[date, date]:
    hoy = timeutil.today()
    return hoy - timedelta(days=dias), hoy - timedelta(days=1)


def cumplimiento(db: Session, org: str, user_ids: list[str]) -> dict:
    """Medidas para el informe de cumplimiento (`informe_de_cumplimiento`), con la empresa
    EXPLÍCITA (el informe corre sin filtro de tenant): personas por encima o cerca (≥ 80 %) de
    los límites publicados en el año, y horas fuera de horario sin autorizar en los últimos 30 días."""
    from app.models.horas_extra import ConfigDeHorasExtra
    f = db.query(ConfigDeHorasExtra).filter(ConfigDeHorasExtra.organization_id == org).first()
    tolerancia = int(f.tolerancia_minutos or 0) if f is not None else 15
    desde, hasta = ultimos_dias(30)
    ids = set(user_ids)
    excesos = [e for e in calculo.excesos(db, desde, hasta, ids, tolerancia) if e["sin_autorizar"] > 0]
    limites = limites_publicados(db, org)
    hoy = timeutil.today()
    por_persona: dict = defaultdict(list)
    if ids:
        for p in db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.organization_id == org,
                                                       PeticionDeHorasExtra.fecha >= date(hoy.year, 1, 1),
                                                       PeticionDeHorasExtra.fecha <= hoy).all():
            por_persona[p.user_id].append(p)
    encima, cerca = set(), set()
    for uid, filas in por_persona.items():
        consumo = _consumo_de_persona(filas, hoy)
        for lim in limites:
            c = consumo.get(lim["campo"], 0.0)
            if lim["umbral"] and c > lim["umbral"]:
                encima.add(uid)
            elif lim["umbral"] and c >= 0.8 * lim["umbral"]:
                cerca.add(uid)
    pendientes_viejas = db.query(PeticionDeHorasExtra).filter(
        PeticionDeHorasExtra.organization_id == org, PeticionDeHorasExtra.origen == "posterior",
        PeticionDeHorasExtra.estado == "pendiente", PeticionDeHorasExtra.fecha < desde).count()
    return {"activo": bool(f.activo) if f is not None else False,
            "control": f.control_imputacion if f is not None else None,
            "limites_publicados": len(limites), "personas_por_encima": len(encima),
            "personas_cerca": len(cerca - encima),
            "dias_sin_autorizar_30d": len(excesos),
            "horas_sin_autorizar_30d": round(sum(e["sin_autorizar"] for e in excesos), 2),
            "personas_sin_autorizar_30d": len({e["user_id"] for e in excesos}),
            "declaraciones_pendientes_de_mas_de_30d": pendientes_viejas}
