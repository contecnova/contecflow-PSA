"""PIR: alta, cuestionario, flujo (enviar, aprobar, devolver, cerrar, reabrir, descartar, borrar) y acciones.

Docs: docs/PIR.md.

Estados: `programado` (creada, sin empezar) → `en_curso` (alguien la está
rellenando) → `enviado` (pendiente de aprobar) → `aprobado` → `cerrado`.
`descartado` solo si no era obligatoria. «Vencida» no es un estado guardado: es
`programado`/`en_curso` con la fecha prevista ya pasada (`vencida()`); el trabajo
de fondo avisa una vez (`aviso_vencido_en`).

GRC:
- `audit_log` de crear, editar, enviar, aprobar, devolver, cerrar, reabrir,
  descartar y borrar (recurso `pir`).
- Segregación: si la empresa la exige (`pir_configuracion.segregacion`), quien
  implantó o gestionó el cambio (dueño, implantador) o el proyecto (PM), o el
  responsable de la propia PIR, no la aprueba ni la cierra
  (`exigir_que_no_sea_suyo`: 403 y la infracción queda en GRC).
- Aislamiento: todo se filtra por la empresa activa; las personas sin rol de
  gestión ven solo las PIR en las que son responsables o participantes.
- Retención y bloqueo legal: tipo `pir_reviews` de `app/db/bloqueo_legal.py`.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.codigos_de_error import error
from app.models.pir import PirAccion, PirRevision
from app.services.pir.plantillas import config, org_de, resolver

logger = logging.getLogger("contecflow.pir")

ORIGENES = ("change", "project")
MOTIVOS = ("implantacion", "cierre", "go_live", "manual", "migrada")
ESTADOS = ("programado", "en_curso", "enviado", "aprobado", "cerrado", "descartado")
ABIERTOS = ("programado", "en_curso")
PENDIENTES = ("programado", "en_curso", "enviado")
HECHOS = ("aprobado", "cerrado")
RESULTADOS = ("exito", "exito_parcial", "fallo")
CUMPLIMIENTO = ("si", "no", "parcial")
ESTADOS_DE_ACCION = ("abierta", "hecha", "descartada")
GESTORES = ("admin", "pm", "team_lead", "hr")


# ── Utilidades ───────────────────────────────────────────────────────────────

def _rol(usuario) -> str:
    return str(getattr(getattr(usuario, "role", None), "value", getattr(usuario, "role", "")) or "")


def _es_gestor(usuario) -> bool:
    return bool(getattr(usuario, "is_superadmin", False)) or _rol(usuario) in GESTORES


def _tiene(db: Session, usuario, capacidad: str) -> bool:
    from app.core.capacidades import tiene
    try:
        return tiene(db, usuario, capacidad)
    except KeyError:
        return False


def _json(raw, defecto=None) -> Any:
    try:
        v = json.loads(raw) if raw else defecto
    except (TypeError, ValueError):
        return defecto
    return v if v is not None else defecto


def _dump(v) -> Optional[str]:
    return json.dumps(v, ensure_ascii=False, default=str) if v is not None else None


def _hoy() -> date:
    return timeutil.today()


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _valor(x):
    return getattr(x, "value", x)


def _fecha(v) -> Optional[date]:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError as exc:
        raise error(422, "pir_campo_no_valido", campo="fecha") from exc


def _num(v, campo: str) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError) as exc:
        raise error(422, "pir_campo_no_valido", campo=campo) from exc


def vencida(pir: PirRevision, hoy: Optional[date] = None) -> bool:
    """Abierta y con la fecha prevista ya pasada."""
    hoy = hoy or _hoy()
    return pir.estado in ABIERTOS and pir.fecha_prevista is not None and pir.fecha_prevista < hoy


def _usuarios_de_la_empresa(db: Session, org: Optional[str], ids) -> list[str]:
    from app.models.user import User
    ids = [str(i) for i in (ids or []) if i]
    if not ids:
        return []
    q = db.query(User.id).filter(User.id.in_(ids), User.is_active.is_(True))
    if org:
        q = q.filter(User.organization_id == org)
    validos = {r[0] for r in q.all()}
    if len(validos) != len(set(ids)):
        raise error(404, "no_encontrado", que="usuario")
    return [i for i in dict.fromkeys(ids)]


def _nombre(db: Session, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    from app.models.user import User
    return db.query(User.full_name).filter(User.id == user_id).scalar()


def _avisar(db: Session, user_id: Optional[str], clave: str, pir: PirRevision, **params) -> None:
    """Aviso en la aplicación en el idioma de quien lo recibe (no rompe el flujo si falla)."""
    if not user_id:
        return
    try:
        from app.services.notifications import notify_user
        # Tipo `system`: `notifications.type` es un enum de la base (otro valor exigiría migrarlo en Postgres).
        notify_user(db, user_id, "system", pir.codigo, None, "pir", pir.id, f"/pir?id={pir.id}",
                    aviso={"titulo": f"pir.aviso.{clave}", "cuerpo": f"pir.aviso.{clave}_cuerpo",
                           "params": {"codigo": pir.codigo, "titulo": pir.titulo, **params}})
    except Exception:
        logger.warning("PIR %s: no se pudo avisar a %s", pir.codigo, user_id, exc_info=True)


# ── Origen ───────────────────────────────────────────────────────────────────

def _cambio(db: Session, usuario, change_id: str):
    from app.models.service_desk import ITSMChangeRequest
    if usuario is None:
        ch = db.get(ITSMChangeRequest, change_id)
    else:
        from app.services.service_desk.change_service import get_change_by_id
        ch = get_change_by_id(db, usuario, change_id)
        if ch is not None and not getattr(usuario, "is_superadmin", False) and ch.organization_id \
                and ch.organization_id != org_de(usuario):
            ch = None
    if ch is None:
        raise error(404, "no_encontrado", que="solicitud_de_cambio")
    return ch


def _proyecto(db: Session, usuario, project_id: str):
    from app.models.project import Project
    if usuario is None:
        p = db.get(Project, project_id)
        if p is None:
            raise error(404, "no_encontrado", que="proyecto")
        return p
    from app.services.project_service import get_project_scoped_or_404
    p = get_project_scoped_or_404(db, project_id, usuario)
    if not getattr(usuario, "is_superadmin", False) and p.organization_id and p.organization_id != org_de(usuario):
        raise error(404, "no_encontrado", que="proyecto")
    return p


def _origen(db: Session, pir: PirRevision):
    from app.models.project import Project
    from app.models.service_desk import ITSMChangeRequest
    if pir.origen_tipo == "change" and pir.change_id:
        return db.get(ITSMChangeRequest, pir.change_id)
    if pir.project_id:
        return db.get(Project, pir.project_id)
    return None


def implicados(db: Session, pir: PirRevision) -> set[str]:
    """Quien implantó o gestionó el origen, y el responsable de la PIR: no la aprueban (segregación)."""
    o = _origen(db, pir)
    gente = {pir.responsable_id}
    if pir.origen_tipo == "change" and o is not None:
        gente |= {o.owner_id, o.implementer_id}
    elif o is not None:
        gente |= {o.pm_id}
    return {g for g in gente if g}


# ── Alta ─────────────────────────────────────────────────────────────────────

def _beneficios_del_proyecto(db: Session, project_id: str) -> list[dict]:
    from app.models.clientes_internos import ProjectBenefit
    filas = db.query(ProjectBenefit).filter(ProjectBenefit.project_id == project_id).order_by(ProjectBenefit.name).all()
    return [{"benefit_id": b.id, "nombre": b.name, "unidad": b.unit, "linea_base": b.baseline, "previsto": b.target,
             "conseguido": b.actual, "comentario": ""} for b in filas]


def crear(db: Session, usuario, origen_tipo: str, origen_id: str, *, motivo: str = "manual",
          milestone_id: Optional[str] = None, fecha_prevista: Optional[date] = None,
          responsable_id: Optional[str] = None, titulo: Optional[str] = None,
          obligatorio: Optional[bool] = None) -> PirRevision:
    """Crea (sin confirmar) la PIR de un cambio o proyecto con el cuestionario de su plantilla.

    `usuario=None` es el sistema (programación automática): no se comprueba el
    alcance de nadie. Una programación automática repetida (mismo origen, motivo
    e hito) devuelve la PIR que ya existe.
    """
    from app.services.audit import audit_log
    from app.services.formato_regional import idioma_de_salida
    from app.services.numbering import next_numbered_code
    from app.services.textos_de_salida import texto
    if origen_tipo not in ORIGENES:
        raise error(422, "pir_campo_no_valido", campo="origen_tipo")
    if motivo not in MOTIVOS:
        raise error(422, "pir_campo_no_valido", campo="motivo")
    if origen_tipo == "change":
        o = _cambio(db, usuario, origen_id)
        org, tipo, ref, nombre = o.organization_id, _valor(o.change_type), o.number, o.title
        responsable_def = o.owner_id or o.implementer_id or o.requester_id
        filtro = PirRevision.change_id == o.id
    else:
        o = _proyecto(db, usuario, origen_id)
        org, tipo, ref, nombre = o.organization_id, o.project_type, o.code, o.name
        responsable_def = o.pm_id
        filtro = PirRevision.project_id == o.id
        if milestone_id:
            from app.models.financial import ProjectMilestone
            if db.query(ProjectMilestone.id).filter(ProjectMilestone.id == milestone_id,
                                                    ProjectMilestone.project_id == o.id).first() is None:
                raise error(404, "no_encontrado", que="hito")
    if org is None and usuario is not None:
        org = org_de(usuario)
    if motivo != "manual":
        ya = db.query(PirRevision).filter(filtro, PirRevision.motivo == motivo,
                                          PirRevision.milestone_id.is_(None) if not milestone_id
                                          else PirRevision.milestone_id == milestone_id,
                                          PirRevision.estado != "descartado").first()
        if ya is not None:
            return ya
    idioma = idioma_de_salida(db, org_id=org)
    r = resolver(db, org, origen_tipo, tipo, idioma)
    if responsable_id:
        _usuarios_de_la_empresa(db, org, [responsable_id])
    pir = PirRevision(
        organization_id=org, origen_tipo=origen_tipo, motivo=motivo, tipo=tipo, plantilla_id=r["plantilla_id"],
        change_id=o.id if origen_tipo == "change" else None, project_id=o.id if origen_tipo == "project" else None,
        milestone_id=milestone_id, estado="programado",
        obligatorio=r["obligatorio"] if obligatorio is None else bool(obligatorio),
        fecha_prevista=fecha_prevista or (_hoy() + timedelta(days=r["dias"])),
        responsable_id=responsable_id or responsable_def,
        titulo=(titulo or texto("pir.titulo", idioma, ref=ref, nombre=nombre))[:300],
        criterios=_dump([{**c, "resultado": None, "comentario": ""} for c in r["criterios"]]),
        preguntas=_dump([{**p, "respuesta": ""} for p in r["preguntas"]]),
        beneficios=_dump(_beneficios_del_proyecto(db, o.id)) if origen_tipo == "project" else None,
        creado_por=getattr(usuario, "id", None),
    )
    pir.codigo = next_numbered_code(db, "pir", prefix="PIR", padding=4)
    db.add(pir)
    db.flush()
    audit_log(db, usuario, "CREATE", "pir", pir.id, pir.codigo,
              new_values={"origen": origen_tipo, "origen_ref": ref, "motivo": motivo, "obligatorio": pir.obligatorio,
                          "fecha_prevista": pir.fecha_prevista.isoformat(), "responsable_id": pir.responsable_id})
    if pir.responsable_id and pir.responsable_id != getattr(usuario, "id", None):
        _avisar(db, pir.responsable_id, "asignada", pir, fecha=pir.fecha_prevista.isoformat())
    return pir


def programar_a_mano(db: Session, usuario, datos: dict) -> dict:
    pir = crear(db, usuario, datos.get("origen_tipo") or "", str(datos.get("origen_id") or ""),
                motivo="manual", milestone_id=datos.get("milestone_id") or None,
                fecha_prevista=_fecha(datos.get("fecha_prevista")), responsable_id=datos.get("responsable_id") or None,
                titulo=datos.get("titulo") or None)
    db.commit()
    return serializar(db, pir, usuario, detalle=True)


# ── Lectura ──────────────────────────────────────────────────────────────────

def _de_la_empresa(db: Session, usuario):
    q = db.query(PirRevision)
    if not getattr(usuario, "is_superadmin", False):
        q = q.filter(PirRevision.organization_id == org_de(usuario))
    return q


def visibles(db: Session, usuario):
    """Las de la empresa activa; sin rol de gestión, solo aquellas en las que participa."""
    q = _de_la_empresa(db, usuario)
    if _es_gestor(usuario):
        return q
    return q.filter(or_(PirRevision.responsable_id == usuario.id, PirRevision.creado_por == usuario.id,
                        PirRevision.participantes.like(f'%"{usuario.id}"%')))


def cargar(db: Session, usuario, pir_id: str) -> PirRevision:
    pir = visibles(db, usuario).filter(PirRevision.id == pir_id).first()
    if pir is None:
        raise error(404, "no_encontrado", que="pir")
    return pir


def _ref_origen(db: Session, pir: PirRevision) -> tuple[Optional[str], Optional[str]]:
    o = _origen(db, pir)
    if o is None:
        return None, None
    return (o.number, o.title) if pir.origen_tipo == "change" else (o.code, o.name)


def puede_editar(db: Session, usuario, pir: PirRevision) -> bool:
    if pir.estado not in ABIERTOS:
        return False
    if _tiene(db, usuario, "pir.gestionar"):
        return True
    return usuario.id in ({pir.responsable_id, pir.creado_por} | set(_json(pir.participantes, [])))


def puede_aprobar(db: Session, usuario, pir: PirRevision) -> bool:
    if not _tiene(db, usuario, "pir.aprobar"):
        return False
    return not (config(db, pir.organization_id).segregacion and usuario.id in implicados(db, pir))


def _acciones(db: Session, pir: PirRevision) -> list[dict]:
    from app.models.task import Task
    salida = []
    for a in db.query(PirAccion).filter(PirAccion.pir_id == pir.id).order_by(PirAccion.created_at).all():
        tarea = db.get(Task, a.task_id) if a.task_id else None
        salida.append({"id": a.id, "descripcion": a.descripcion, "responsable_id": a.responsable_id,
                       "responsable": _nombre(db, a.responsable_id),
                       "fecha_limite": a.fecha_limite.isoformat() if a.fecha_limite else None, "estado": a.estado,
                       "project_id": a.project_id, "task_id": a.task_id, "task_code": getattr(tarea, "code", None),
                       "task_status": _valor(getattr(tarea, "status", None)),
                       "vencida": bool(a.fecha_limite and a.fecha_limite < _hoy() and a.estado == "abierta")})
    return salida


def _lecciones(db: Session, pir: PirRevision) -> list[dict]:
    from app.models.lecciones import Leccion
    return [{"id": l.id, "codigo": l.codigo, "titulo": l.titulo, "estado": l.estado, "tipo": l.tipo}
            for l in db.query(Leccion).filter(Leccion.origen_tipo == "pir", Leccion.origen_id == pir.id)
            .order_by(Leccion.created_at).all()]


def _incidencias(db: Session, pir: PirRevision) -> list[dict]:
    from app.models.service_desk import Ticket
    ids = [str(i) for i in _json(pir.incidencias, [])]
    if not ids:
        return []
    filas = {t.id: t for t in db.query(Ticket).filter(Ticket.id.in_(ids)).all()}
    return [{"id": i, "number": getattr(filas.get(i), "number", None), "title": getattr(filas.get(i), "title", None),
             "status": _valor(getattr(filas.get(i), "status", None))} for i in ids]


def serializar(db: Session, pir: PirRevision, usuario=None, detalle: bool = False) -> dict:
    ref, nombre = _ref_origen(db, pir)
    hoy = _hoy()
    d = {
        "id": pir.id, "codigo": pir.codigo, "titulo": pir.titulo, "origen_tipo": pir.origen_tipo,
        "change_id": pir.change_id, "project_id": pir.project_id, "milestone_id": pir.milestone_id,
        "origen_ref": ref, "origen_nombre": nombre, "motivo": pir.motivo, "tipo": pir.tipo,
        "estado": pir.estado, "vencida": vencida(pir, hoy), "obligatorio": bool(pir.obligatorio),
        "fecha_prevista": pir.fecha_prevista.isoformat() if pir.fecha_prevista else None,
        "fecha_real": pir.fecha_real.isoformat() if pir.fecha_real else None,
        "dias_restantes": (pir.fecha_prevista - hoy).days if pir.fecha_prevista and pir.estado in ABIERTOS else None,
        "responsable_id": pir.responsable_id, "responsable": _nombre(db, pir.responsable_id),
        "resultado": pir.resultado, "objetivos_cumplidos": pir.objetivos_cumplidos,
        "hubo_marcha_atras": pir.hubo_marcha_atras,
        "created_at": pir.created_at.isoformat() if pir.created_at else None,
    }
    if not detalle:
        return d
    d.update({
        "participantes": _json(pir.participantes, []), "resumen": pir.resumen,
        "criterios": _json(pir.criterios, []), "preguntas": _json(pir.preguntas, []), "kpis": _json(pir.kpis, []),
        "incidencias": _incidencias(db, pir), "marcha_atras_detalle": pir.marcha_atras_detalle,
        "beneficios": _json(pir.beneficios, []), "satisfaccion": _json(pir.satisfaccion, []),
        "satisfaccion_media": pir.satisfaccion_media,
        "enviado_por": _nombre(db, pir.enviado_por), "enviado_en": pir.enviado_en.isoformat() if pir.enviado_en else None,
        "aprobado_por": _nombre(db, pir.aprobado_por),
        "aprobado_en": pir.aprobado_en.isoformat() if pir.aprobado_en else None,
        "comentario_aprobacion": pir.comentario_aprobacion,
        "cerrado_por": _nombre(db, pir.cerrado_por), "cerrado_en": pir.cerrado_en.isoformat() if pir.cerrado_en else None,
        "reaperturas": pir.reaperturas or 0, "cuenta_en_modelo": bool(pir.cuenta_en_modelo),
        "acciones": _acciones(db, pir), "lecciones": _lecciones(db, pir),
    })
    if usuario is not None:
        gestiona = _tiene(db, usuario, "pir.gestionar")
        aprueba = puede_aprobar(db, usuario, pir)
        d["permisos"] = {
            "editar": puede_editar(db, usuario, pir),
            "enviar": pir.estado in ABIERTOS and puede_editar(db, usuario, pir),
            "aprobar": pir.estado == "enviado" and aprueba,
            "devolver": pir.estado == "enviado" and _tiene(db, usuario, "pir.aprobar"),
            "cerrar": pir.estado == "aprobado" and aprueba,
            "reabrir": pir.estado in ("aprobado", "cerrado", "descartado") and _tiene(db, usuario, "pir.aprobar"),
            "descartar": pir.estado in ABIERTOS and not pir.obligatorio and gestiona,
            "borrar": _tiene(db, usuario, "pir.administrar"),
            "acciones": gestiona or usuario.id == pir.responsable_id,
            "segregacion": bool(config(db, pir.organization_id).segregacion and usuario.id in implicados(db, pir)),
        }
    return d


def detalle(db: Session, usuario, pir_id: str) -> dict:
    return serializar(db, cargar(db, usuario, pir_id), usuario, detalle=True)


def listar(db: Session, usuario, *, origen_tipo: Optional[str] = None, origen_id: Optional[str] = None,
           estado: Optional[str] = None, resultado: Optional[str] = None, solo_mias: bool = False,
           solo_obligatorias: bool = False, q: Optional[str] = None, page: int = 1, page_size: int = 50) -> dict:
    qry = visibles(db, usuario)
    if origen_tipo:
        qry = qry.filter(PirRevision.origen_tipo == origen_tipo)
    if origen_id:
        qry = qry.filter(or_(PirRevision.change_id == origen_id, PirRevision.project_id == origen_id))
    hoy = _hoy()
    if estado == "vencido":
        qry = qry.filter(PirRevision.estado.in_(ABIERTOS), PirRevision.fecha_prevista < hoy)
    elif estado == "pendiente":
        qry = qry.filter(PirRevision.estado.in_(PENDIENTES))
    elif estado:
        qry = qry.filter(PirRevision.estado == estado)
    if resultado:
        qry = qry.filter(PirRevision.resultado == resultado)
    if solo_mias:
        qry = qry.filter(or_(PirRevision.responsable_id == usuario.id,
                             PirRevision.participantes.like(f'%"{usuario.id}"%')))
    if solo_obligatorias:
        qry = qry.filter(PirRevision.obligatorio.is_(True))
    if q:
        patron = f"%{q.strip().lower()}%"
        from sqlalchemy import func
        qry = qry.filter(func.lower(PirRevision.titulo).like(patron) | func.lower(PirRevision.codigo).like(patron))
    total = qry.count()
    filas = qry.order_by(PirRevision.fecha_prevista.asc().nullslast(), PirRevision.created_at.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [serializar(db, p) for p in filas], "total": total, "page": page, "page_size": page_size}


def mias_pendientes(db: Session, usuario) -> list[dict]:
    """Las PIR asignadas a quien pregunta (responsable o participante) sin terminar: bandeja y Mi trabajo."""
    filas = _de_la_empresa(db, usuario).filter(
        PirRevision.estado.in_(PENDIENTES),
        or_(PirRevision.responsable_id == usuario.id, PirRevision.participantes.like(f'%"{usuario.id}"%'))) \
        .order_by(PirRevision.fecha_prevista.asc().nullslast()).limit(200).all()
    if _tiene(db, usuario, "pir.aprobar"):
        # Las enviadas que podría aprobar (sin ser implicado) también le tocan.
        por_aprobar = [p for p in _de_la_empresa(db, usuario).filter(PirRevision.estado == "enviado").limit(200).all()
                       if puede_aprobar(db, usuario, p)]
        vistos = {p.id for p in filas}
        filas += [p for p in por_aprobar if p.id not in vistos]
    return [serializar(db, p) for p in filas]


def resumen_de_cambio(db: Session, change_id: str) -> dict:
    """Para la ficha del cambio y la compatibilidad con `pir_notes`/`pir_success`/`pir_date` (migración 206)."""
    filas = db.query(PirRevision).filter(PirRevision.change_id == change_id, PirRevision.estado != "descartado") \
        .order_by(PirRevision.created_at.desc()).all()
    ultima = filas[0] if filas else None
    obligatoria_pendiente = any(p.obligatorio and p.estado not in HECHOS for p in filas)
    return {
        "pir_id": getattr(ultima, "id", None), "pir_estado": getattr(ultima, "estado", None),
        "pir_vencida": bool(ultima and vencida(ultima)),
        "pir_obligatoria_pendiente": obligatoria_pendiente,
        "pir_notes": getattr(ultima, "resumen", None),
        "pir_success": None if ultima is None or ultima.resultado is None else ultima.resultado != "fallo",
        "pir_date": str(ultima.fecha_real) if ultima is not None and ultima.fecha_real else None,
    }


# ── Cuestionario ─────────────────────────────────────────────────────────────

def _criterios(actuales: list, nuevos: list) -> list:
    por_clave = {c.get("clave"): c for c in actuales if isinstance(c, dict)}
    salida = []
    for it in nuevos or []:
        if not isinstance(it, dict):
            raise error(422, "pir_campo_no_valido", campo="criterios")
        clave = str(it.get("clave") or "").strip()
        base = dict(por_clave.get(clave) or {"clave": clave, "texto": str(it.get("texto") or "").strip()[:500]})
        if not base["clave"] or not base.get("texto"):
            raise error(422, "pir_campo_no_valido", campo="criterios")
        res = it.get("resultado")
        if res not in (None, "") and res not in CUMPLIMIENTO:
            raise error(422, "pir_campo_no_valido", campo="criterios.resultado")
        base["resultado"] = res or None
        base["comentario"] = str(it.get("comentario") or "")[:2000]
        salida.append(base)
    return salida


def _preguntas(actuales: list, nuevas: list) -> list:
    por_clave = {p.get("clave"): p for p in actuales if isinstance(p, dict)}
    salida = []
    for it in nuevas or []:
        if not isinstance(it, dict):
            raise error(422, "pir_campo_no_valido", campo="preguntas")
        clave = str(it.get("clave") or "").strip()
        base = dict(por_clave.get(clave) or {"clave": clave, "texto": str(it.get("texto") or "").strip()[:500]})
        if not base["clave"] or not base.get("texto"):
            raise error(422, "pir_campo_no_valido", campo="preguntas")
        base["respuesta"] = str(it.get("respuesta") or "")[:4000]
        salida.append(base)
    return salida


def _kpis(items: list) -> list:
    salida = []
    for it in items or []:
        if not isinstance(it, dict) or not str(it.get("nombre") or "").strip():
            raise error(422, "pir_campo_no_valido", campo="kpis")
        salida.append({"nombre": str(it["nombre"]).strip()[:200], "unidad": str(it.get("unidad") or "")[:30],
                       "antes": _num(it.get("antes"), "kpis.antes"), "despues": _num(it.get("despues"), "kpis.despues"),
                       "objetivo": _num(it.get("objetivo"), "kpis.objetivo")})
    return salida


def _tickets(db: Session, org: Optional[str], ids: list) -> list[str]:
    from app.models.service_desk import Ticket
    ids = [str(i) for i in dict.fromkeys(ids or []) if i]
    if not ids:
        return []
    q = db.query(Ticket.id).filter(Ticket.id.in_(ids))
    if org:
        q = q.filter(Ticket.organization_id == org)
    if {r[0] for r in q.all()} != set(ids):
        raise error(404, "no_encontrado", que="ticket")
    return ids


def _satisfaccion(items: list) -> tuple[list, Optional[float]]:
    salida, notas = [], []
    for it in items or []:
        if not isinstance(it, dict) or not str(it.get("interesado") or "").strip():
            raise error(422, "pir_campo_no_valido", campo="satisfaccion")
        p = it.get("puntuacion")
        if p not in (None, ""):
            p = int(p)
            if not 1 <= p <= 5:
                raise error(422, "pir_campo_no_valido", campo="satisfaccion.puntuacion")
            notas.append(p)
        salida.append({"interesado": str(it["interesado"]).strip()[:200], "rol": str(it.get("rol") or "")[:100],
                       "puntuacion": p if p not in (None, "") else None,
                       "comentario": str(it.get("comentario") or "")[:2000]})
    return salida, (round(sum(notas) / len(notas), 2) if notas else None)


def _beneficios(db: Session, usuario, pir: PirRevision, items: list) -> list:
    """Conseguido frente a previsto; con `actualizar` escribe el valor real en el beneficio del proyecto."""
    from app.models.clientes_internos import ProjectBenefit
    actuales = {b.get("benefit_id"): b for b in _json(pir.beneficios, []) if isinstance(b, dict)}
    salida = []
    for it in items or []:
        if not isinstance(it, dict):
            raise error(422, "pir_campo_no_valido", campo="beneficios")
        bid = it.get("benefit_id")
        b = db.get(ProjectBenefit, bid) if bid else None
        if bid and (b is None or b.project_id != pir.project_id):
            raise error(404, "no_encontrado", que="beneficio")
        base = dict(actuales.get(bid) or {"benefit_id": bid, "nombre": getattr(b, "name", None) or str(it.get("nombre") or "")[:200],
                                          "unidad": getattr(b, "unit", None), "linea_base": getattr(b, "baseline", None),
                                          "previsto": getattr(b, "target", None)})
        if not base.get("nombre"):
            raise error(422, "pir_campo_no_valido", campo="beneficios")
        if not bid and "previsto" in it:
            base["previsto"] = _num(it.get("previsto"), "beneficios.previsto")
        base["conseguido"] = _num(it.get("conseguido"), "beneficios.conseguido")
        base["comentario"] = str(it.get("comentario") or "")[:2000]
        salida.append(base)
        if b is not None and it.get("actualizar") and base["conseguido"] is not None and b.actual != base["conseguido"]:
            from app.services.audit import audit_log
            antes = b.actual
            b.actual, b.measured_at = base["conseguido"], _hoy()
            audit_log(db, usuario, "UPDATE", "project_benefit", b.id, b.name, old_values={"actual": antes},
                      new_values={"actual": b.actual, "origen": f"pir:{pir.codigo}"})
    return salida


_SIMPLES = ("resumen", "marcha_atras_detalle")


def guardar(db: Session, usuario, pir_id: str, datos: dict) -> dict:
    from app.services.audit import audit_log
    pir = cargar(db, usuario, pir_id)
    if not puede_editar(db, usuario, pir):
        raise error(409 if pir.estado not in ABIERTOS else 403, "pir_no_editable", estado=pir.estado)
    gestiona = _tiene(db, usuario, "pir.gestionar")
    cambios = []
    if "titulo" in datos and str(datos["titulo"] or "").strip():
        pir.titulo = str(datos["titulo"]).strip()[:300]
        cambios.append("titulo")
    for campo in ("fecha_prevista", "responsable_id"):
        if campo in datos:
            if not gestiona:
                raise error(403, "pir_sin_permiso")
            if campo == "fecha_prevista":
                nueva = _fecha(datos[campo])
                if nueva is None:
                    raise error(422, "pir_campo_no_valido", campo=campo)
                if nueva != pir.fecha_prevista:
                    pir.aviso_previo_en = pir.aviso_vencido_en = None
                pir.fecha_prevista = nueva
            else:
                pir.responsable_id = (_usuarios_de_la_empresa(db, pir.organization_id, [datos[campo]]) or [None])[0]
            cambios.append(campo)
    if "participantes" in datos:
        pir.participantes = _dump(_usuarios_de_la_empresa(db, pir.organization_id, datos["participantes"] or []))
        cambios.append("participantes")
    if "objetivos_cumplidos" in datos:
        v = datos["objetivos_cumplidos"] or None
        if v is not None and v not in CUMPLIMIENTO:
            raise error(422, "pir_campo_no_valido", campo="objetivos_cumplidos")
        pir.objetivos_cumplidos = v
        cambios.append("objetivos_cumplidos")
    if "resultado" in datos:
        v = datos["resultado"] or None
        if v is not None and v not in RESULTADOS:
            raise error(422, "pir_campo_no_valido", campo="resultado")
        pir.resultado = v
        cambios.append("resultado")
    for campo in _SIMPLES:
        if campo in datos:
            setattr(pir, campo, (str(datos[campo]) if datos[campo] is not None else None))
            cambios.append(campo)
    if "hubo_marcha_atras" in datos:
        pir.hubo_marcha_atras = None if datos["hubo_marcha_atras"] is None else bool(datos["hubo_marcha_atras"])
        cambios.append("hubo_marcha_atras")
    if "criterios" in datos:
        pir.criterios = _dump(_criterios(_json(pir.criterios, []), datos["criterios"]))
        cambios.append("criterios")
    if "preguntas" in datos:
        pir.preguntas = _dump(_preguntas(_json(pir.preguntas, []), datos["preguntas"]))
        cambios.append("preguntas")
    if "kpis" in datos:
        pir.kpis = _dump(_kpis(datos["kpis"]))
        cambios.append("kpis")
    if "incidencias" in datos:
        pir.incidencias = _dump(_tickets(db, pir.organization_id, datos["incidencias"]))
        cambios.append("incidencias")
    if "satisfaccion" in datos:
        lista, media = _satisfaccion(datos["satisfaccion"])
        pir.satisfaccion, pir.satisfaccion_media = _dump(lista), media
        cambios.append("satisfaccion")
    if "beneficios" in datos:
        if pir.origen_tipo != "project":
            raise error(422, "pir_campo_no_valido", campo="beneficios")
        pir.beneficios = _dump(_beneficios(db, usuario, pir, datos["beneficios"]))
        cambios.append("beneficios")
    if cambios and pir.estado == "programado":
        pir.estado = "en_curso"
    if cambios:
        audit_log(db, usuario, "UPDATE", "pir", pir.id, pir.codigo, metadata={"campos": cambios, "estado": pir.estado})
    db.commit()
    return serializar(db, pir, usuario, detalle=True)


# ── Flujo ────────────────────────────────────────────────────────────────────

def _faltan(pir: PirRevision) -> list[str]:
    faltan = []
    if not pir.resultado:
        faltan.append("resultado")
    if not pir.objetivos_cumplidos:
        faltan.append("objetivos_cumplidos")
    if any(not c.get("resultado") for c in _json(pir.criterios, []) if isinstance(c, dict)):
        faltan.append("criterios")
    if pir.origen_tipo == "change" and pir.hubo_marcha_atras is None:
        faltan.append("hubo_marcha_atras")
    return faltan


def enviar(db: Session, usuario, pir_id: str) -> dict:
    from app.services.audit import audit_log
    pir = cargar(db, usuario, pir_id)
    if pir.estado not in ABIERTOS:
        raise error(409, "pir_transicion_no_permitida", desde=pir.estado, hasta="enviado")
    if not puede_editar(db, usuario, pir):
        raise error(403, "pir_sin_permiso")
    faltan = _faltan(pir)
    if faltan:
        raise error(422, "pir_incompleta", faltan=", ".join(faltan))
    antes = pir.estado
    pir.estado, pir.enviado_por, pir.enviado_en = "enviado", usuario.id, _ahora()
    pir.fecha_real = pir.fecha_real or _hoy()
    audit_log(db, usuario, "SUBMIT", "pir", pir.id, pir.codigo, old_values={"estado": antes},
              new_values={"estado": pir.estado, "resultado": pir.resultado, "a_tiempo": not vencida_al_enviar(pir)})
    db.commit()
    return serializar(db, pir, usuario, detalle=True)


def vencida_al_enviar(pir: PirRevision) -> bool:
    return bool(pir.fecha_prevista and pir.fecha_real and pir.fecha_real > pir.fecha_prevista)


def _exigir_segregacion(db: Session, usuario, pir: PirRevision) -> None:
    if config(db, pir.organization_id).segregacion and usuario.id in implicados(db, pir):
        from app.services.approval_engine._base import exigir_que_no_sea_suyo
        exigir_que_no_sea_suyo(db, usuario.id, usuario, "pir", pir.id)


def _efecto_en_modelo(db: Session, pir: PirRevision, usuario, aplicar: bool) -> None:
    """Un cambio estándar con PIR «fallo» suma un fallo a su modelo del catálogo (y lo deshace al reabrir)."""
    if pir.origen_tipo != "change" or not pir.change_id:
        return
    from app.services.service_desk import cambios_estandar_service as cat
    ch = _origen(db, pir)
    if ch is None:
        return
    if aplicar and pir.resultado == "fallo" and not pir.cuenta_en_modelo:
        pir.cuenta_en_modelo = cat.anotar_fallo_de_pir(db, ch, usuario)
    elif not aplicar and pir.cuenta_en_modelo:
        cat.deshacer_fallo_de_pir(db, ch, usuario)
        pir.cuenta_en_modelo = False


def aprobar(db: Session, usuario, pir_id: str, comentario: Optional[str] = None) -> dict:
    from app.services.audit import audit_log
    pir = cargar(db, usuario, pir_id)
    if pir.estado != "enviado":
        raise error(409, "pir_transicion_no_permitida", desde=pir.estado, hasta="aprobado")
    _exigir_segregacion(db, usuario, pir)
    pir.estado, pir.aprobado_por, pir.aprobado_en = "aprobado", usuario.id, _ahora()
    pir.comentario_aprobacion = (comentario or "").strip() or None
    _efecto_en_modelo(db, pir, usuario, aplicar=True)
    audit_log(db, usuario, "APPROVE", "pir", pir.id, pir.codigo, old_values={"estado": "enviado"},
              new_values={"estado": pir.estado, "resultado": pir.resultado, "cuenta_en_modelo": pir.cuenta_en_modelo},
              metadata={"comentario": pir.comentario_aprobacion})
    _avisar(db, pir.responsable_id, "aprobada", pir)
    db.commit()
    return serializar(db, pir, usuario, detalle=True)


def devolver(db: Session, usuario, pir_id: str, comentario: str) -> dict:
    from app.services.audit import audit_log
    pir = cargar(db, usuario, pir_id)
    if pir.estado != "enviado":
        raise error(409, "pir_transicion_no_permitida", desde=pir.estado, hasta="en_curso")
    if not (comentario or "").strip():
        raise error(422, "campos_obligatorios", campos="comentario")
    pir.estado, pir.comentario_aprobacion = "en_curso", comentario.strip()
    audit_log(db, usuario, "REJECT", "pir", pir.id, pir.codigo, old_values={"estado": "enviado"},
              new_values={"estado": pir.estado}, metadata={"comentario": pir.comentario_aprobacion})
    _avisar(db, pir.responsable_id, "devuelta", pir, comentario=pir.comentario_aprobacion)
    db.commit()
    return serializar(db, pir, usuario, detalle=True)


def cerrar(db: Session, usuario, pir_id: str) -> dict:
    from app.services.audit import audit_log
    pir = cargar(db, usuario, pir_id)
    if pir.estado != "aprobado":
        raise error(409, "pir_transicion_no_permitida", desde=pir.estado, hasta="cerrado")
    _exigir_segregacion(db, usuario, pir)
    pir.estado, pir.cerrado_por, pir.cerrado_en = "cerrado", usuario.id, _ahora()
    audit_log(db, usuario, "UPDATE", "pir", pir.id, pir.codigo, old_values={"estado": "aprobado"},
              new_values={"estado": pir.estado}, metadata={"accion": "cerrar"})
    db.commit()
    return serializar(db, pir, usuario, detalle=True)


def reabrir(db: Session, usuario, pir_id: str, motivo: str) -> dict:
    from app.services.audit import audit_log
    pir = cargar(db, usuario, pir_id)
    if pir.estado not in ("aprobado", "cerrado", "descartado"):
        raise error(409, "pir_transicion_no_permitida", desde=pir.estado, hasta="en_curso")
    if not (motivo or "").strip():
        raise error(422, "campos_obligatorios", campos="motivo")
    antes = pir.estado
    _efecto_en_modelo(db, pir, usuario, aplicar=False)
    pir.estado = "en_curso"
    pir.aprobado_por = pir.aprobado_en = pir.cerrado_por = pir.cerrado_en = None
    pir.reaperturas = (pir.reaperturas or 0) + 1
    audit_log(db, usuario, "REOPEN", "pir", pir.id, pir.codigo, old_values={"estado": antes},
              new_values={"estado": pir.estado, "reaperturas": pir.reaperturas}, metadata={"motivo": motivo.strip()})
    _avisar(db, pir.responsable_id, "reabierta", pir, motivo=motivo.strip())
    db.commit()
    return serializar(db, pir, usuario, detalle=True)


def descartar(db: Session, usuario, pir_id: str, motivo: str) -> dict:
    from app.services.audit import audit_log
    pir = cargar(db, usuario, pir_id)
    if pir.estado not in ABIERTOS:
        raise error(409, "pir_transicion_no_permitida", desde=pir.estado, hasta="descartado")
    if pir.obligatorio:
        raise error(409, "pir_obligatoria_no_descartable")
    if not (motivo or "").strip():
        raise error(422, "campos_obligatorios", campos="motivo")
    antes = pir.estado
    pir.estado = "descartado"
    audit_log(db, usuario, "UPDATE", "pir", pir.id, pir.codigo, old_values={"estado": antes},
              new_values={"estado": pir.estado}, metadata={"accion": "descartar", "motivo": motivo.strip()})
    db.commit()
    return serializar(db, pir, usuario, detalle=True)


def borrar(db: Session, usuario, pir_id: str) -> None:
    """Borrado real (solo `pir.administrar`). Un bloqueo legal lo impide (`before_flush`)."""
    from app.services.audit import audit_log
    pir = cargar(db, usuario, pir_id)
    _efecto_en_modelo(db, pir, usuario, aplicar=False)
    audit_log(db, usuario, "DELETE", "pir", pir.id, pir.codigo,
              old_values=serializar(db, pir), metadata={"acciones": db.query(PirAccion).filter(PirAccion.pir_id == pir.id).count()})
    db.delete(pir)
    db.commit()


# ── Acciones de mejora (→ tareas) ────────────────────────────────────────────

def _proyecto_de_la_accion(db: Session, pir: PirRevision, pedido: Optional[str]) -> Optional[str]:
    if pedido:
        return pedido
    if pir.project_id:
        return pir.project_id
    return config(db, pir.organization_id).proyecto_acciones_id


def crear_accion(db: Session, usuario, pir_id: str, datos: dict) -> dict:
    """Acción de mejora con responsable y fecha; nace como tarea en el proyecto de la PIR (o el elegido,
    o el de mejora continua de la configuración). Sin proyecto, se guarda sin tarea y se dice."""
    from app.services.audit import audit_log
    pir = cargar(db, usuario, pir_id)
    if not (_tiene(db, usuario, "pir.gestionar") or usuario.id == pir.responsable_id):
        raise error(403, "pir_sin_permiso")
    if pir.estado == "descartado":
        raise error(409, "pir_no_editable", estado=pir.estado)
    descripcion = str(datos.get("descripcion") or "").strip()
    if len(descripcion) < 3:
        raise error(422, "campos_obligatorios", campos="descripcion")
    responsable = datos.get("responsable_id") or None
    if responsable:
        _usuarios_de_la_empresa(db, pir.organization_id, [responsable])
    limite = _fecha(datos.get("fecha_limite"))
    project_id = _proyecto_de_la_accion(db, pir, datos.get("project_id") or None)
    a = PirAccion(organization_id=pir.organization_id, pir_id=pir.id, descripcion=descripcion[:4000],
                  responsable_id=responsable, fecha_limite=limite, estado="abierta", project_id=project_id,
                  creado_por=usuario.id)
    db.add(a)
    db.flush()
    if project_id:
        from app.schemas.tasks import TaskCreate
        from app.services.task_service import create_task_record
        from app.services.textos_de_salida import texto
        from app.services.formato_regional import idioma_de_salida
        idioma = idioma_de_salida(db, org_id=pir.organization_id)
        tarea = create_task_record(db, TaskCreate(
            project_id=project_id, title=f"[{pir.codigo}] {descripcion}"[:255],
            description=texto("pir.tarea_descripcion", idioma, codigo=pir.codigo, titulo=pir.titulo),
            assignee_id=responsable, due_date=limite, tags="pir"), usuario)   # confirma
        a = db.get(PirAccion, a.id)
        a.task_id = tarea.id
    audit_log(db, usuario, "CREATE", "pir_accion", a.id, pir.codigo,
              new_values={"descripcion": a.descripcion, "responsable_id": responsable, "task_id": a.task_id,
                          "fecha_limite": limite.isoformat() if limite else None})
    if responsable and responsable != usuario.id:
        _avisar(db, responsable, "accion", pir, accion=descripcion[:120])
    db.commit()
    return {"accion": next(x for x in _acciones(db, pir) if x["id"] == a.id), "sin_tarea": a.task_id is None}


def editar_accion(db: Session, usuario, pir_id: str, accion_id: str, datos: dict) -> dict:
    from app.services.audit import audit_log
    pir = cargar(db, usuario, pir_id)
    a = db.query(PirAccion).filter(PirAccion.id == accion_id, PirAccion.pir_id == pir.id).first()
    if a is None:
        raise error(404, "no_encontrado", que="accion")
    if not (_tiene(db, usuario, "pir.gestionar") or usuario.id in (pir.responsable_id, a.responsable_id)):
        raise error(403, "pir_sin_permiso")
    antes = {"estado": a.estado, "responsable_id": a.responsable_id,
             "fecha_limite": a.fecha_limite.isoformat() if a.fecha_limite else None}
    if "estado" in datos:
        if datos["estado"] not in ESTADOS_DE_ACCION:
            raise error(422, "pir_campo_no_valido", campo="estado")
        a.estado = datos["estado"]
    if "responsable_id" in datos:
        a.responsable_id = (_usuarios_de_la_empresa(db, pir.organization_id, [datos["responsable_id"]]) or [None])[0] \
            if datos["responsable_id"] else None
    if "fecha_limite" in datos:
        a.fecha_limite = _fecha(datos["fecha_limite"])
    audit_log(db, usuario, "UPDATE", "pir_accion", a.id, pir.codigo, old_values=antes,
              new_values={"estado": a.estado, "responsable_id": a.responsable_id,
                          "fecha_limite": a.fecha_limite.isoformat() if a.fecha_limite else None})
    db.commit()
    return next(x for x in _acciones(db, pir) if x["id"] == a.id)


# ── Lecciones aprendidas ─────────────────────────────────────────────────────

def hechos_para_leccion(db: Session, usuario, pir_id: str) -> dict:
    """Lo que `lecciones.hechos_de("pir", id)` guarda con la lección (el acceso a la PIR manda)."""
    pir = cargar(db, usuario, pir_id)
    ref, nombre = _ref_origen(db, pir)
    criterios = [f"{c.get('texto')}: {c.get('resultado') or '—'}" for c in _json(pir.criterios, []) if isinstance(c, dict)]
    hechos = [
        {"clave": "leccion.hecho.pir_origen", "valor": f"{ref} — {nombre}" if ref else None},
        {"clave": "leccion.hecho.pir_resultado", "valor": pir.resultado},
        {"clave": "leccion.hecho.pir_objetivos", "valor": pir.objetivos_cumplidos},
        {"clave": "leccion.hecho.pir_marcha_atras", "valor": True if pir.hubo_marcha_atras else None},
        {"clave": "leccion.hecho.pir_incidencias", "valor": len(_json(pir.incidencias, [])) or None},
        {"clave": "leccion.hecho.pir_criterios", "valor": criterios or None},
        {"clave": "leccion.hecho.pir_satisfaccion", "valor": pir.satisfaccion_media},
    ]
    ambito: dict = {"proyecto_id": pir.project_id}
    if pir.project_id:
        from app.models.project import Project
        p = db.get(Project, pir.project_id)
        if p is not None:
            ambito.update(cliente_id=p.client_id, tipo_proyecto=p.project_type, etiquetas=p.tags)
    if pir.change_id:
        o = _origen(db, pir)
        cis = _json(getattr(o, "affected_cis", None), [])
        if cis:
            ambito["ci_id"] = str(cis[0])
    return {"ref": pir.codigo, "titulo": pir.titulo, "texto": f"{pir.titulo}. {pir.resumen or ''}",
            "ambito": ambito, "hechos": [{**h, "etiqueta": h["clave"]} for h in hechos if h["valor"] not in (None, "", [])]}


def crear_leccion(db: Session, usuario, pir_id: str, datos: dict) -> dict:
    """Una lección aprendida en el módulo de lecciones, con la PIR como origen."""
    from app.services import lecciones
    cargar(db, usuario, pir_id)
    campos = {k: datos.get(k) for k in ("titulo", "tipo", "categoria", "severidad", "que_paso", "causa", "impacto",
                                         "recomendacion", "etiquetas") if datos.get(k) not in (None, "")}
    return lecciones.crear(db, usuario, {**campos, "origen_tipo": "pir", "origen_id": pir_id,
                                         "enviar_a_revision": bool(datos.get("enviar_a_revision"))})
