"""Lecciones aprendidas: capturar, validar, recomendar y medir (revisión 2026-11).

Mejora continua en cuatro piezas:

1. **Capturar desde los hechos.** Una lección nace de un origen —proyecto
   cerrado, ticket resuelto, problema, incidente grave, sprint con
   retrospectiva, incidente de seguridad— o a mano. Los HECHOS del origen se
   miden aquí (desvío de plazo, horas y coste contra presupuesto, cambios,
   riesgos materializados, tiempo de resolución, SLA, causa raíz…) y se
   guardan con la lección. La IA, si está activada, propone el borrador sobre
   esos hechos; la persona lo corrige. Sin IA, el borrador lleva los hechos y
   los campos de juicio vacíos.
2. **Pendientes.** Lo cerrado en los últimos `LESSONS_PENDING_LOOKBACK_DAYS`
   días sin ninguna lección: es la lista de trabajo de la mejora continua.
3. **Recomendar en el momento de actuar.** Dado un proyecto, un ticket o un
   proyecto que aún se está creando, se puntúan las lecciones (validadas, si
   así se configura) por cliente, tipo de proyecto, etiquetas, servicio o CI y
   parecido del texto, con pesos de Admin; cada recomendación dice POR QUÉ se
   recomienda y cita su origen: «Evita: … — porque en PRJ-0007 pasó: …».
4. **Medir.** Quien la recibe dice si le sirvió (`util`, `aplicada`,
   `no_aplica`); las acciones de mejora tienen responsable y plazo. Los
   indicadores salen de ahí, no de un contador que se incremente al mostrar.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from app.models.service_desk._enums import ESTADOS_DE_INCIDENTE_MAYOR_RESUELTOS, ESTADOS_DE_PROBLEMA_RESUELTOS
from app.core.errores import ErrorDeDominio


from app.core import timeutil
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.lecciones import Leccion, LeccionAccion, LeccionUso

logger = logging.getLogger("contecflow.lecciones")

ORIGENES = ("project", "ticket", "problem", "major_incident", "sprint", "security_incident", "manual")
ESTADOS = ("borrador", "en_revision", "validada", "archivada")
TIPOS = ("evitar", "repetir")
SEVERIDADES = ("baja", "media", "alta")
VALORES_DE_USO = ("util", "aplicada", "no_aplica")
ESTADOS_DE_ACCION = ("abierta", "en_curso", "hecha", "descartada")


# ── Ajustes ───────────────────────────────────────────────────────────────────

def _aj(db: Session, clave: str, org: Optional[str], tipo: str = "float"):
    from app.services import settings_service as s
    return {"float": s.get_runtime_float, "int": s.get_runtime_int, "bool": s.get_runtime_bool,
            "str": s.get_runtime_str}[tipo](db, clave, org)


def categorias(db: Session, org: Optional[str]) -> list[str]:
    return [c.strip() for c in str(_aj(db, "LESSONS_CATEGORIES", org, "str") or "").split(",") if c.strip()]


def _rol(usuario) -> str:
    return str(getattr(getattr(usuario, "role", None), "value", getattr(usuario, "role", "")))


def puede_validar(db: Session, usuario) -> bool:
    roles = {r.strip() for r in str(_aj(db, "LESSONS_VALIDATOR_ROLES", usuario.organization_id, "str") or "").split(",")}
    return _rol(usuario) in roles


# ── Texto y parecido ──────────────────────────────────────────────────────────

def _palabras(texto: str) -> set[str]:
    from app.services.service_desk.kb_calidad import _palabras as p
    return p(texto)


def _vector(texto: str) -> Optional[list]:
    try:
        from app.services.service_desk.kb_calidad import _vector as v
        return v(texto)
    except Exception:   # sin modelo de embeddings: se compara por palabras
        logger.debug("lecciones: sin vector", exc_info=True)
        return None


def _texto_de(l: Leccion) -> str:
    return " ".join(x for x in (l.titulo, l.que_paso, l.causa, l.recomendacion) if x)


def _etiquetas(s: Optional[str]) -> set[str]:
    return {e.strip().lower() for e in (s or "").split(",") if e.strip()}


def _parecido_texto(vec: Optional[list], palabras: set, l: Leccion) -> float:
    if vec and l.vector:
        from app.services.semantic_classifier import _cosine
        try:
            return max(0.0, float(_cosine(vec, json.loads(l.vector))))
        except (ValueError, TypeError):
            pass
    otras = _palabras(_texto_de(l))
    if not palabras or not otras:
        return 0.0
    return len(palabras & otras) / len(palabras | otras)


# ── Hechos de cada origen ─────────────────────────────────────────────────────

def _dias(a, b) -> Optional[int]:
    return (b - a).days if a and b else None


def _horas(a, b) -> Optional[float]:
    if not a or not b:
        return None
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return round((b - a).total_seconds() / 3600, 1)


def _h(etiqueta: str, valor: Any) -> Optional[dict]:
    if valor is None or valor == "" or valor == []:
        return None
    return {"etiqueta": etiqueta, "valor": valor}


def _hechos_proyecto(db: Session, usuario, id_: str) -> dict:
    from app.models.imputation import Imputation
    from app.models.pipeline import Risk
    from app.models.resources import ChangeRequest
    from app.models.sprints import Sprint
    from app.models.user import User
    from app.services.project_service import get_project_scoped_or_404
    p = get_project_scoped_or_404(db, id_, usuario)
    horas, coste = 0.0, 0.0
    tarifas = dict(db.query(User.id, User.hourly_rate).all())
    for i in db.query(Imputation).filter(Imputation.project_id == p.id).all():
        horas += float(i.hours or 0)
        if i.cost_amount is not None:
            coste += float(i.cost_amount)
        else:
            coste += float(i.hours or 0) * float(i.hourly_rate_snapshot or tarifas.get(i.user_id) or 0)
    cambios = db.query(ChangeRequest).filter(ChangeRequest.project_id == p.id).all()
    riesgos = db.query(Risk).filter(Risk.project_id == p.id).all()
    materializados = [r.title for r in riesgos if getattr(r.status, "value", r.status) == "materialized"]
    retros = [s for s in db.query(Sprint).filter(Sprint.project_id == p.id).all() if s.to_improve or s.went_well]
    fin = p.end_date_real
    hechos = [
        _h("Estado", getattr(p.status, "value", p.status)),
        _h("Inicio", p.start_date and p.start_date.isoformat()),
        _h("Fin previsto", p.end_date_planned and p.end_date_planned.isoformat()),
        _h("Fin real", fin and fin.isoformat()),
        _h("Desvío de plazo (días)", _dias(p.end_date_planned, fin)),
        _h("Horas presupuestadas", p.budget_hours),
        _h("Horas imputadas", round(horas, 1)),
        _h("Desvío de horas (%)", round((horas - p.budget_hours) / p.budget_hours * 100, 1) if p.budget_hours else None),
        _h("Presupuesto", p.budget_amount),
        _h("Coste imputado", round(coste, 2)),
        _h("Desvío de coste (%)", round((coste - p.budget_amount) / p.budget_amount * 100, 1) if p.budget_amount else None),
        _h("Solicitudes de cambio", len(cambios) or None),
        _h("Coste de los cambios", round(sum(float(c.cost_impact or 0) for c in cambios), 2) or None),
        _h("Días añadidos por cambios", sum(int(c.schedule_impact_days or 0) for c in cambios) or None),
        _h("Riesgos identificados", len(riesgos) or None),
        _h("Riesgos materializados", materializados),
        _h("Qué mejorar (retrospectivas)", [s.to_improve for s in retros if s.to_improve]),
        _h("Qué salió bien (retrospectivas)", [s.went_well for s in retros if s.went_well]),
    ]
    return {"ref": p.code, "titulo": p.name, "texto": f"{p.name}. {p.description or ''}",
            "ambito": {"proyecto_id": p.id, "cliente_id": p.client_id,
                       "tipo_proyecto": getattr(p.project_type, "value", p.project_type), "etiquetas": p.tags},
            "hechos": [x for x in hechos if x]}


def _hechos_ticket(db: Session, usuario, id_: str) -> dict:
    from app.services.service_desk.scoping import get_scoped_ticket_or_404
    t = get_scoped_ticket_or_404(db, usuario, id_)
    fin = t.resolved_at or t.closed_at
    hechos = [
        _h("Tipo", getattr(t.ticket_type, "value", t.ticket_type)),
        _h("Prioridad", getattr(t.priority, "value", t.priority)),
        _h("Estado", getattr(t.status, "value", t.status)),
        _h("Horas hasta resolver", _horas(t.created_at, fin)),
        _h("SLA de resolución incumplido", True if t.sla_resolution_breached else None),
        _h("Resolución", t.resolution),
    ]
    cliente = t.client_id
    if not cliente and t.project_id:
        from app.models.project import Project
        cliente = db.query(Project.client_id).filter(Project.id == t.project_id).scalar()
    return {"ref": t.number, "titulo": t.title, "texto": f"{t.title}. {t.description or ''} {t.resolution or ''}",
            "ambito": {"proyecto_id": t.project_id, "cliente_id": cliente, "servicio_id": t.service_item_id,
                       "ci_id": t.ci_id},
            "hechos": [x for x in hechos if x]}


def _hechos_problema(db: Session, usuario, id_: str) -> dict:
    from app.models.service_desk.problems import Problem
    from app.models.service_desk.tickets import Ticket
    from app.services.service_desk.scoping import scope_problem_query
    p = scope_problem_query(db.query(Problem), db, usuario).filter(Problem.id == id_).first()
    if p is None:
        raise ErrorDeDominio(404, "Problema no encontrado")
    tickets = db.query(func.count(Ticket.id)).filter(Ticket.problem_id == p.id).scalar() or 0
    hechos = [
        _h("Estado", getattr(p.status, "value", p.status)),
        _h("Tipo de causa", p.rca_type),
        _h("Causa raíz", p.root_cause),
        _h("Solución temporal", p.workaround),
        _h("Solución definitiva", p.fix_description),
        _h("Tickets vinculados", tickets or None),
    ]
    return {"ref": p.number, "titulo": p.title, "texto": f"{p.title}. {p.description or ''} {p.root_cause or ''}",
            "ambito": {"ci_id": getattr(p, "ci_id", None)}, "hechos": [x for x in hechos if x]}


def _hechos_incidente_grave(db: Session, usuario, id_: str) -> dict:
    from app.models.service_desk.problems import MajorIncident
    from app.models.service_desk.tickets import Ticket
    m = db.query(MajorIncident).filter(MajorIncident.id == id_).first()
    if m is None:
        raise ErrorDeDominio(404, "Incidente grave no encontrado")
    tickets = db.query(func.count(Ticket.id)).filter(Ticket.major_incident_id == m.id).scalar() or 0
    hechos = [
        _h("Severidad", m.severity),
        _h("Estado", getattr(m.status, "value", m.status)),
        _h("Horas hasta resolver", _horas(m.declared_at, m.resolved_at)),
        _h("Impacto", m.impact_statement),
        _h("Resolución", m.resolution_summary),
        _h("Tickets afectados", tickets or None),
    ]
    return {"ref": m.number, "titulo": m.title, "texto": f"{m.title}. {m.impact_statement or ''} {m.resolution_summary or ''}",
            "ambito": {}, "hechos": [x for x in hechos if x]}


def _hechos_sprint(db: Session, usuario, id_: str) -> dict:
    from app.models.sprints import Sprint
    from app.services.project_service import get_project_scoped_or_404
    s = db.query(Sprint).filter(Sprint.id == id_).first()
    if s is None:
        raise ErrorDeDominio(404, "Sprint no encontrado")
    p = get_project_scoped_or_404(db, s.project_id, usuario)
    hechos = [
        _h("Proyecto", p.code),
        _h("Puntos planificados", s.planned_points),
        _h("Puntos completados", s.completed_points),
        _h("Velocidad", s.velocity),
        _h("Qué salió bien", s.went_well),
        _h("Qué mejorar", s.to_improve),
        _h("Acciones acordadas", s.action_items),
    ]
    return {"ref": f"{p.code} · {s.name}", "titulo": s.name, "texto": f"{s.name}. {s.to_improve or ''} {s.went_well or ''}",
            "ambito": {"proyecto_id": p.id, "cliente_id": p.client_id,
                       "tipo_proyecto": getattr(p.project_type, "value", p.project_type), "etiquetas": p.tags},
            "hechos": [x for x in hechos if x]}


def _hechos_incidente_seguridad(db: Session, usuario, id_: str) -> dict:
    from app.models.security_observability import SecurityIncident
    if _rol(usuario) != "admin":
        raise ErrorDeDominio(403, "Los incidentes de seguridad sólo los abre un administrador")
    i = db.query(SecurityIncident).filter(SecurityIncident.id == id_,
                                          SecurityIncident.org_id == usuario.organization_id).first()
    if i is None:
        raise ErrorDeDominio(404, "Incidente de seguridad no encontrado")
    hechos = [
        _h("Severidad", i.severity),
        _h("Estado", i.status),
        _h("Minutos hasta detectar", round(i.mttd_seconds / 60) if i.mttd_seconds else None),
        _h("Minutos hasta resolver", round(i.mttr_seconds / 60) if i.mttr_seconds else None),
        _h("Causa raíz", i.root_cause),
        _h("Remedio", i.remediation_note),
        _h("Lecciones anotadas en el incidente", i.lessons_learned),
    ]
    return {"ref": f"SEC-{i.id[:8]}", "titulo": i.title, "texto": f"{i.title}. {i.root_cause or ''} {i.lessons_learned or ''}",
            "ambito": {}, "hechos": [x for x in hechos if x]}


_HECHOS = {"project": _hechos_proyecto, "ticket": _hechos_ticket, "problem": _hechos_problema,
           "major_incident": _hechos_incidente_grave, "sprint": _hechos_sprint,
           "security_incident": _hechos_incidente_seguridad}


def hechos_de(db: Session, usuario, origen_tipo: str, origen_id: str) -> dict:
    if origen_tipo not in _HECHOS:
        raise ErrorDeDominio(400, f"Origen desconocido: {origen_tipo}")
    return _HECHOS[origen_tipo](db, usuario, origen_id)


# ── Borrador ──────────────────────────────────────────────────────────────────

_SISTEMA = (
    "Eres responsable de mejora continua en una empresa de servicios profesionales. Con los HECHOS medidos de un "
    "proyecto, ticket o incidente, redacta UNA lección aprendida útil para casos futuros. No inventes datos que no "
    "estén en los hechos; si algo no se sabe, déjalo vacío. Contesta SOLO un JSON con las claves: titulo (máx. 120 "
    "caracteres), tipo ('evitar' o 'repetir'), categoria (una de: {categorias}), severidad ('baja','media','alta'), "
    "que_paso, causa, impacto, recomendacion (en imperativo, concreta), etiquetas (lista de palabras clave)."
)


def _json_de(texto: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        return d if isinstance(d, dict) else None
    except ValueError:
        return None


def _resumen(h: dict) -> str:
    return "\n".join(f"- {x['etiqueta']}: {'; '.join(map(str, x['valor'])) if isinstance(x['valor'], list) else x['valor']}"
                     for x in h["hechos"])


def borrador(db: Session, usuario, origen_tipo: str, origen_id: str) -> dict:
    """Hechos medidos + propuesta de lección. `ia` dice si la propuesta es de la IA o sólo de los hechos."""
    h = hechos_de(db, usuario, origen_tipo, origen_id)
    cats = categorias(db, usuario.organization_id)
    base = {"titulo": f"{h['ref']}: {h['titulo']}"[:300], "tipo": "evitar", "categoria": cats[0] if cats else "",
            "severidad": "media", "que_paso": _resumen(h), "causa": "", "impacto": "", "recomendacion": "",
            "etiquetas": h["ambito"].get("etiquetas") or ""}
    salida = {"origen_tipo": origen_tipo, "origen_id": origen_id, "origen_ref": h["ref"], "hechos": h["hechos"],
              "ambito": h["ambito"], "propuesta": base, "ia": False, "aviso": None}
    if not _aj(db, "LESSONS_AI_DRAFT_ENABLED", usuario.organization_id, "bool"):
        salida["aviso"] = "Borrador con IA desactivado (LESSONS_AI_DRAFT_ENABLED)"
        return salida
    from app.services.ai_provider_service import call_ai, es_aviso_de_ia
    try:
        texto = call_ai(db, [{"role": "user", "content": f"Origen: {h['ref']} — {h['titulo']}\nHechos:\n{_resumen(h)}"}],
                        system=_SISTEMA.format(categorias=", ".join(cats)), module="lessons_learned",
                        user_id=usuario.id, organization_id=usuario.organization_id, is_superadmin=False,
                        max_tokens=int(_aj(db, "LESSONS_AI_MAX_TOKENS", usuario.organization_id, "int")))
    except Exception as e:   # presupuesto agotado, proveedor caído…: se sigue sin IA y se dice
        logger.warning("lecciones: borrador sin IA (%s)", e)
        salida["aviso"] = f"La IA no ha podido proponer: {e}"[:300]
        return salida
    if es_aviso_de_ia(texto):
        salida["aviso"] = texto[:300]
        return salida
    d = _json_de(texto)
    if not d:
        salida["aviso"] = ("La IA no devolvió una propuesta legible (¿cortada por LESSONS_AI_MAX_TOKENS?); "
                           "se deja el borrador con los hechos")
        return salida
    prop = dict(base)
    for k in ("titulo", "que_paso", "causa", "impacto", "recomendacion"):
        if isinstance(d.get(k), str) and d[k].strip():
            prop[k] = d[k].strip()
    if d.get("tipo") in TIPOS:
        prop["tipo"] = d["tipo"]
    if d.get("severidad") in SEVERIDADES:
        prop["severidad"] = d["severidad"]
    if d.get("categoria") in cats:
        prop["categoria"] = d["categoria"]
    etiquetas = d.get("etiquetas")
    if isinstance(etiquetas, list):
        prop["etiquetas"] = ",".join(sorted(_etiquetas(base["etiquetas"]) | {str(e).strip().lower() for e in etiquetas if str(e).strip()}))
    prop["titulo"] = prop["titulo"][:300]
    salida.update(propuesta=prop, ia=True)
    return salida


# ── Alta, edición y estados ───────────────────────────────────────────────────

_CAMPOS = ("titulo", "tipo", "categoria", "severidad", "que_paso", "causa", "impacto", "recomendacion", "etiquetas",
           "proyecto_id", "cliente_id", "tipo_proyecto", "servicio_id", "ci_id")


def _validar_campos(db: Session, org, datos: dict) -> None:
    if "tipo" in datos and datos["tipo"] not in TIPOS:
        raise ErrorDeDominio(400, f"Tipo no válido: {datos['tipo']}")
    if "severidad" in datos and datos["severidad"] not in SEVERIDADES:
        raise ErrorDeDominio(400, f"Severidad no válida: {datos['severidad']}")
    if "categoria" in datos and datos["categoria"] not in categorias(db, org):
        raise ErrorDeDominio(400, f"Categoría no válida: {datos['categoria']} (las de LESSONS_CATEGORIES)")
    for k in ("titulo", "que_paso", "recomendacion"):
        if k in datos and not str(datos[k] or "").strip():
            raise ErrorDeDominio(400, f"«{k}» no puede quedar vacío")


def _cargar(db: Session, id_: str) -> Leccion:
    l = db.query(Leccion).filter(Leccion.id == id_).first()
    if l is None:
        raise ErrorDeDominio(404, "Lección no encontrada")
    return l


def _dict(db: Session, l: Leccion, usuario=None, detalle: bool = False) -> dict:
    d = {k: getattr(l, k) for k in ("id", "codigo", "titulo", "tipo", "categoria", "severidad", "que_paso", "causa",
                                     "impacto", "recomendacion", "estado", "origen_tipo", "origen_id", "origen_ref",
                                     "proyecto_id", "cliente_id", "tipo_proyecto", "etiquetas", "servicio_id", "ci_id",
                                     "autor_id", "validada_por")}
    d["validada_en"] = l.validada_en.isoformat() if l.validada_en else None
    d["created_at"] = l.created_at.isoformat() if l.created_at else None
    usos = dict(db.query(LeccionUso.valor, func.count(LeccionUso.id)).filter(LeccionUso.leccion_id == l.id)
                .group_by(LeccionUso.valor).all())
    d["usos"] = {v: int(usos.get(v, 0)) for v in VALORES_DE_USO}
    if detalle:
        d["hechos"] = json.loads(l.hechos) if l.hechos else []
        d["acciones"] = [_accion_dict(a) for a in db.query(LeccionAccion).filter(LeccionAccion.leccion_id == l.id)
                         .order_by(LeccionAccion.created_at).all()]
        d["historial_usos"] = [{"valor": u.valor, "contexto_tipo": u.contexto_tipo, "contexto_id": u.contexto_id,
                                "nota": u.nota, "user_id": u.user_id,
                                "created_at": u.created_at.isoformat() if u.created_at else None}
                               for u in db.query(LeccionUso).filter(LeccionUso.leccion_id == l.id)
                               .order_by(LeccionUso.created_at.desc()).limit(50).all()]
        if usuario is not None:
            d["puedo_editar"] = puede_editar(db, usuario, l)
            d["puedo_validar"] = puede_validar(db, usuario)
    return d


def puede_editar(db: Session, usuario, l: Leccion) -> bool:
    if puede_validar(db, usuario):
        return True
    return l.autor_id == usuario.id and l.estado in ("borrador", "en_revision")


def crear(db: Session, usuario, datos: dict) -> dict:
    from app.services.audit import audit_log
    from app.services.numbering import next_numbered_code
    origen_tipo = datos.get("origen_tipo") or "manual"
    if origen_tipo not in ORIGENES:
        raise ErrorDeDominio(400, f"Origen desconocido: {origen_tipo}")
    campos = {k: datos.get(k) for k in _CAMPOS if datos.get(k) not in (None, "")}
    campos.setdefault("tipo", "evitar")
    campos.setdefault("severidad", "media")
    _validar_campos(db, usuario.organization_id, {**campos, "titulo": campos.get("titulo"),
                                                  "que_paso": campos.get("que_paso"),
                                                  "recomendacion": campos.get("recomendacion"),
                                                  "categoria": campos.get("categoria")})
    l = Leccion(organization_id=usuario.organization_id, origen_tipo=origen_tipo, autor_id=usuario.id,
                estado="en_revision" if datos.get("enviar_a_revision") else "borrador", **campos)
    if origen_tipo != "manual":
        if not datos.get("origen_id"):
            raise ErrorDeDominio(400, "Falta el origen")
        h = hechos_de(db, usuario, origen_tipo, str(datos["origen_id"]))   # comprueba el acceso al origen
        l.origen_id, l.origen_ref, l.hechos = str(datos["origen_id"]), h["ref"], json.dumps(h["hechos"], ensure_ascii=False, default=str)
        for k, v in h["ambito"].items():
            if v and not getattr(l, k, None):
                setattr(l, k, v)
    vec = _vector(_texto_de(l))
    l.vector = json.dumps(vec) if vec else None
    l.codigo = next_numbered_code(db, "lesson", prefix="LEC", padding=4)
    db.add(l)
    db.flush()
    audit_log(db, usuario, "CREATE", "lecciones", l.id, l.codigo, new_values={"titulo": l.titulo, "origen": origen_tipo})
    db.commit()
    return _dict(db, l, usuario, detalle=True)


def editar(db: Session, usuario, id_: str, datos: dict) -> dict:
    from app.services.audit import audit_log
    l = _cargar(db, id_)
    if not puede_editar(db, usuario, l):
        raise ErrorDeDominio(403, "Sólo quien la escribió (antes de validarla) o quien valida puede editarla")
    cambios = {k: datos[k] for k in _CAMPOS if k in datos}
    _validar_campos(db, usuario.organization_id, cambios)
    antes = {k: getattr(l, k) for k in cambios}
    for k, v in cambios.items():
        setattr(l, k, v if v != "" else None)
    if datos.get("enviar_a_revision") and l.estado == "borrador":
        l.estado = "en_revision"
    vec = _vector(_texto_de(l))
    l.vector = json.dumps(vec) if vec else l.vector
    audit_log(db, usuario, "UPDATE", "lecciones", l.id, l.codigo, old_values=antes, new_values=cambios)
    db.commit()
    return _dict(db, l, usuario, detalle=True)


def cambiar_estado(db: Session, usuario, id_: str, estado: str) -> dict:
    from app.services.audit import audit_log
    if estado not in ESTADOS:
        raise ErrorDeDominio(400, f"Estado no válido: {estado}")
    l = _cargar(db, id_)
    if estado in ("validada", "archivada") or l.estado in ("validada", "archivada"):
        if not puede_validar(db, usuario):
            raise ErrorDeDominio(403, "Validar o archivar es de los roles de LESSONS_VALIDATOR_ROLES")
    elif not puede_editar(db, usuario, l):
        raise ErrorDeDominio(403, "No puedes cambiar esta lección")
    antes = l.estado
    l.estado = estado
    if estado == "validada":
        l.validada_por, l.validada_en = usuario.id, datetime.now(timezone.utc)
    audit_log(db, usuario, "UPDATE", "lecciones", l.id, l.codigo, old_values={"estado": antes}, new_values={"estado": estado})
    db.commit()
    return _dict(db, l, usuario, detalle=True)


def borrar(db: Session, usuario, id_: str) -> None:
    from app.services.audit import audit_log
    if _rol(usuario) != "admin":
        raise ErrorDeDominio(403, "Sólo un administrador borra lecciones (lo normal es archivarlas)")
    l = _cargar(db, id_)
    audit_log(db, usuario, "DELETE", "lecciones", l.id, l.codigo, old_values={"titulo": l.titulo})
    db.delete(l)
    db.commit()


def detalle(db: Session, usuario, id_: str) -> dict:
    return _dict(db, _cargar(db, id_), usuario, detalle=True)


def listar(db: Session, usuario, *, q: Optional[str] = None, estado: Optional[str] = None, tipo: Optional[str] = None,
           categoria: Optional[str] = None, origen_tipo: Optional[str] = None, proyecto_id: Optional[str] = None,
           cliente_id: Optional[str] = None, etiqueta: Optional[str] = None, page: int = 1, page_size: int = 50) -> dict:
    qry = db.query(Leccion)
    if estado:
        qry = qry.filter(Leccion.estado == estado)
    else:
        qry = qry.filter(Leccion.estado != "archivada")
    for col, val in ((Leccion.tipo, tipo), (Leccion.categoria, categoria), (Leccion.origen_tipo, origen_tipo),
                     (Leccion.proyecto_id, proyecto_id), (Leccion.cliente_id, cliente_id)):
        if val:
            qry = qry.filter(col == val)
    if etiqueta:
        qry = qry.filter(func.lower(Leccion.etiquetas).contains(etiqueta.strip().lower()))
    if q:
        patron = f"%{q.strip().lower()}%"
        qry = qry.filter(func.lower(Leccion.titulo).like(patron) | func.lower(Leccion.que_paso).like(patron)
                         | func.lower(Leccion.recomendacion).like(patron) | func.lower(Leccion.codigo).like(patron))
    total = qry.count()
    filas = qry.order_by(Leccion.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [_dict(db, l) for l in filas], "total": total, "page": page, "page_size": page_size}


def de_origen(db: Session, usuario, origen_tipo: str, origen_id: str) -> list[dict]:
    hechos_de(db, usuario, origen_tipo, origen_id)   # el acceso al origen manda
    return [_dict(db, l) for l in db.query(Leccion).filter(Leccion.origen_tipo == origen_tipo,
                                                          Leccion.origen_id == str(origen_id))
            .order_by(Leccion.created_at.desc()).all()]


# ── Pendientes de capturar ────────────────────────────────────────────────────

def pendientes(db: Session, usuario) -> list[dict]:
    """Lo cerrado en la ventana que todavía no tiene ninguna lección."""
    from app.models.project import Project
    from app.models.security_observability import SecurityIncident
    from app.models.service_desk.problems import MajorIncident, Problem
    from app.models.sprints import Sprint
    from app.services.service_desk.scoping import scope_problem_query
    dias = int(_aj(db, "LESSONS_PENDING_LOOKBACK_DAYS", usuario.organization_id, "int"))
    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    desde_fecha = desde.date()
    con_leccion = {(t, i) for t, i in db.query(Leccion.origen_tipo, Leccion.origen_id).filter(Leccion.origen_id.isnot(None)).all()}
    salida: list[dict] = []

    def poner(tipo, id_, ref, titulo, cuando):
        if (tipo, str(id_)) not in con_leccion:
            salida.append({"origen_tipo": tipo, "origen_id": str(id_), "ref": ref, "titulo": titulo,
                           "cerrado": cuando.isoformat() if cuando else None})

    for p in db.query(Project).filter(Project.status.in_(("completed", "closed"))).all():
        cuando = p.end_date_real or (p.updated_at.date() if getattr(p, "updated_at", None) else None)
        if cuando is None or cuando >= desde_fecha:
            poner("project", p.id, p.code, p.name, cuando)
    for pr in scope_problem_query(db.query(Problem), db, usuario).filter(Problem.status.in_(ESTADOS_DE_PROBLEMA_RESUELTOS)).all():
        cuando = getattr(pr, "resolved_at", None) or getattr(pr, "updated_at", None)
        if cuando is None or _aware(cuando) >= desde:
            poner("problem", pr.id, pr.number, pr.title, cuando)
    for m in db.query(MajorIncident).filter(MajorIncident.status.in_(ESTADOS_DE_INCIDENTE_MAYOR_RESUELTOS)).all():
        if m.resolved_at is None or _aware(m.resolved_at) >= desde:
            poner("major_incident", m.id, m.number, m.title, m.resolved_at)
    for s in db.query(Sprint).filter(Sprint.status == "completed").all():
        if (s.to_improve or s.went_well or s.action_items) and (s.end_date is None or s.end_date >= desde_fecha):
            poner("sprint", s.id, s.name, s.name, s.end_date)
    if _rol(usuario) == "admin":
        for i in db.query(SecurityIncident).filter(SecurityIncident.org_id == usuario.organization_id,
                                                   SecurityIncident.resolved_at.isnot(None)).all():
            if (i.lessons_learned or i.root_cause) and _aware(i.resolved_at) >= desde:
                poner("security_incident", i.id, f"SEC-{i.id[:8]}", i.title, i.resolved_at)
    salida.sort(key=lambda x: x["cerrado"] or "", reverse=True)
    return salida


def _aware(d):
    if isinstance(d, datetime) and d.tzinfo is None:
        return d.replace(tzinfo=timezone.utc)
    if isinstance(d, date) and not isinstance(d, datetime):
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return d


# ── Recomendaciones ───────────────────────────────────────────────────────────

def contexto_de(db: Session, usuario, contexto_tipo: str, contexto_id: Optional[str], campos: Optional[dict]) -> dict:
    if contexto_tipo == "nuevo_proyecto":
        c = campos or {}
        return {"ambito": {"cliente_id": c.get("cliente_id"), "tipo_proyecto": c.get("tipo_proyecto"),
                           "etiquetas": c.get("etiquetas")},
                "texto": f"{c.get('nombre') or ''} {c.get('descripcion') or ''}", "excluir": None}
    if contexto_tipo in ("project", "ticket"):
        h = hechos_de(db, usuario, contexto_tipo, str(contexto_id))
        return {"ambito": h["ambito"], "texto": h["texto"], "excluir": (contexto_tipo, str(contexto_id))}
    raise ErrorDeDominio(400, f"Contexto desconocido: {contexto_tipo}")


def _frase(l: Leccion) -> str:
    verbo = "Evita" if l.tipo == "evitar" else "Repite"
    pasado = (l.que_paso or "").strip().split("\n")[0][:220]
    donde = f"en {l.origen_ref}" if l.origen_ref else "en un caso anterior"
    return f"{verbo}: {l.recomendacion.strip()} — porque {donde} pasó: {pasado}"


def recomendar(db: Session, usuario, contexto_tipo: str, contexto_id: Optional[str] = None,
               campos: Optional[dict] = None) -> dict:
    org = usuario.organization_id
    ctx = contexto_de(db, usuario, contexto_tipo, contexto_id, campos)
    a = ctx["ambito"]
    pesos = {k: float(_aj(db, f"LESSONS_WEIGHT_{k}", org)) for k in ("CLIENT", "PROJECT_TYPE", "TAGS", "CATEGORY", "TEXT")}
    minimo = float(_aj(db, "LESSONS_RECOMMENDATIONS_MIN_SCORE", org))
    maximo = int(_aj(db, "LESSONS_RECOMMENDATIONS_MAX", org, "int"))
    qry = db.query(Leccion).filter(Leccion.estado != "archivada")
    if _aj(db, "LESSONS_ONLY_VALIDATED", org, "bool"):
        qry = qry.filter(Leccion.estado == "validada")
    etiquetas_ctx = _etiquetas(a.get("etiquetas"))
    vec = _vector(ctx["texto"]) if ctx["texto"].strip() else None
    palabras = _palabras(ctx["texto"])
    candidatas = qry.all()
    puntuadas = []
    for l in candidatas:
        if ctx["excluir"] and (l.origen_tipo, l.origen_id) == ctx["excluir"]:
            continue
        motivos, puntos = [], 0.0
        if a.get("cliente_id") and l.cliente_id == a["cliente_id"]:
            puntos += pesos["CLIENT"]
            motivos.append({"clave": "mismo_cliente", "peso": pesos["CLIENT"]})
        if a.get("tipo_proyecto") and l.tipo_proyecto == a["tipo_proyecto"]:
            puntos += pesos["PROJECT_TYPE"]
            motivos.append({"clave": "mismo_tipo_de_proyecto", "peso": pesos["PROJECT_TYPE"]})
        comunes = etiquetas_ctx & _etiquetas(l.etiquetas)
        if comunes:
            parte = pesos["TAGS"] * len(comunes) / len(etiquetas_ctx | _etiquetas(l.etiquetas))
            puntos += parte
            motivos.append({"clave": "etiquetas", "peso": round(parte, 3), "detalle": sorted(comunes)})
        if (a.get("servicio_id") and l.servicio_id == a["servicio_id"]) or (a.get("ci_id") and l.ci_id == a["ci_id"]):
            puntos += pesos["CATEGORY"]
            motivos.append({"clave": "mismo_servicio_o_ci", "peso": pesos["CATEGORY"]})
        texto = _parecido_texto(vec, palabras, l)
        if texto > 0:
            parte = pesos["TEXT"] * texto
            puntos += parte
            motivos.append({"clave": "texto_parecido", "peso": round(parte, 3),
                            "detalle": sorted(palabras & _palabras(_texto_de(l)))[:8]})
        if puntos >= minimo:
            puntuadas.append((puntos, l, motivos))
    puntuadas.sort(key=lambda x: -x[0])
    mis_usos = {}
    if contexto_id:
        mis_usos = {u.leccion_id: u.valor for u in db.query(LeccionUso).filter(
            LeccionUso.contexto_tipo == contexto_tipo, LeccionUso.contexto_id == str(contexto_id),
            LeccionUso.user_id == usuario.id).all()}
    return {"evaluadas": len(candidatas), "minimo": minimo, "items": [
        {**_dict(db, l), "puntuacion": round(p, 3), "motivos": m, "frase": _frase(l), "mi_valoracion": mis_usos.get(l.id)}
        for p, l, m in puntuadas[:maximo]]}


def valorar(db: Session, usuario, leccion_id: str, contexto_tipo: str, contexto_id: Optional[str], valor: str,
            nota: Optional[str] = None) -> dict:
    if valor not in VALORES_DE_USO:
        raise ErrorDeDominio(400, f"Valor no válido: {valor}")
    l = _cargar(db, leccion_id)
    if contexto_tipo in ("project", "ticket") and contexto_id:
        hechos_de(db, usuario, contexto_tipo, str(contexto_id))
    previo = db.query(LeccionUso).filter(LeccionUso.leccion_id == l.id, LeccionUso.contexto_tipo == contexto_tipo,
                                         LeccionUso.contexto_id == (str(contexto_id) if contexto_id else None),
                                         LeccionUso.user_id == usuario.id).first()
    if previo is not None:
        previo.valor, previo.nota = valor, (nota or None) and nota[:500]
    else:
        db.add(LeccionUso(organization_id=usuario.organization_id, leccion_id=l.id, contexto_tipo=contexto_tipo,
                          contexto_id=str(contexto_id) if contexto_id else None, valor=valor,
                          nota=(nota or None) and nota[:500], user_id=usuario.id))
    db.commit()
    return _dict(db, l)


# ── Acciones de mejora ────────────────────────────────────────────────────────

def _accion_dict(a: LeccionAccion) -> dict:
    hoy = timeutil.today()
    return {"id": a.id, "leccion_id": a.leccion_id, "descripcion": a.descripcion, "responsable_id": a.responsable_id,
            "fecha_limite": a.fecha_limite.isoformat() if a.fecha_limite else None, "estado": a.estado,
            "resultado": a.resultado, "cerrada_en": a.cerrada_en.isoformat() if a.cerrada_en else None,
            "vencida": bool(a.fecha_limite and a.fecha_limite < hoy and a.estado in ("abierta", "en_curso"))}


def crear_accion(db: Session, usuario, leccion_id: str, descripcion: str, responsable_id: Optional[str],
                 fecha_limite: Optional[date]) -> dict:
    l = _cargar(db, leccion_id)
    if not (puede_editar(db, usuario, l) or puede_validar(db, usuario)):
        raise ErrorDeDominio(403, "No puedes añadir acciones a esta lección")
    if responsable_id:
        from app.models.user import User
        if db.query(User.id).filter(User.id == responsable_id).first() is None:
            raise ErrorDeDominio(404, "Responsable no encontrado")
    a = LeccionAccion(organization_id=usuario.organization_id, leccion_id=l.id, descripcion=descripcion.strip(),
                      responsable_id=responsable_id, fecha_limite=fecha_limite, created_by=usuario.id)
    db.add(a)
    db.commit()
    return _accion_dict(a)


def editar_accion(db: Session, usuario, accion_id: str, datos: dict) -> dict:
    a = db.query(LeccionAccion).filter(LeccionAccion.id == accion_id).first()
    if a is None:
        raise ErrorDeDominio(404, "Acción no encontrada")
    l = _cargar(db, a.leccion_id)
    if not (a.responsable_id == usuario.id or puede_editar(db, usuario, l) or puede_validar(db, usuario)):
        raise ErrorDeDominio(403, "Sólo el responsable o quien edita la lección")
    if "estado" in datos:
        if datos["estado"] not in ESTADOS_DE_ACCION:
            raise ErrorDeDominio(400, f"Estado no válido: {datos['estado']}")
        a.estado = datos["estado"]
        a.cerrada_en = datetime.now(timezone.utc) if a.estado in ("hecha", "descartada") else None
    for k in ("descripcion", "resultado", "responsable_id", "fecha_limite"):
        if k in datos:
            setattr(a, k, datos[k])
    db.commit()
    return _accion_dict(a)


def acciones(db: Session, usuario, *, solo_mias: bool = False, solo_abiertas: bool = True) -> list[dict]:
    qry = db.query(LeccionAccion, Leccion.codigo, Leccion.titulo).join(Leccion, Leccion.id == LeccionAccion.leccion_id)
    if solo_mias:
        qry = qry.filter(LeccionAccion.responsable_id == usuario.id)
    if solo_abiertas:
        qry = qry.filter(LeccionAccion.estado.in_(("abierta", "en_curso")))
    return [{**_accion_dict(a), "leccion_codigo": c, "leccion_titulo": t}
            for a, c, t in qry.order_by(LeccionAccion.fecha_limite.is_(None), LeccionAccion.fecha_limite).all()]


# ── Indicadores ───────────────────────────────────────────────────────────────

def indicadores(db: Session, usuario) -> dict:
    por_estado = dict(db.query(Leccion.estado, func.count(Leccion.id)).group_by(Leccion.estado).all())
    activas = db.query(Leccion).filter(Leccion.estado != "archivada")
    por_categoria = dict(activas.with_entities(Leccion.categoria, func.count(Leccion.id)).group_by(Leccion.categoria).all())
    por_tipo = dict(activas.with_entities(Leccion.tipo, func.count(Leccion.id)).group_by(Leccion.tipo).all())
    por_origen = dict(activas.with_entities(Leccion.origen_tipo, func.count(Leccion.id)).group_by(Leccion.origen_tipo).all())
    usos = dict(db.query(LeccionUso.valor, func.count(LeccionUso.id)).group_by(LeccionUso.valor).all())
    total_usos = sum(usos.values())
    utiles = int(usos.get("util", 0)) + int(usos.get("aplicada", 0))
    top = (db.query(Leccion, func.count(LeccionUso.id).label("n"))
           .join(LeccionUso, LeccionUso.leccion_id == Leccion.id)
           .filter(LeccionUso.valor.in_(("util", "aplicada")))
           .group_by(Leccion.id).order_by(func.count(LeccionUso.id).desc()).limit(5).all())
    hoy = timeutil.today()
    abiertas = db.query(LeccionAccion).filter(LeccionAccion.estado.in_(("abierta", "en_curso")))
    # Por mes de calendario, los 12 últimos (el mes en curso, a medias, se marca).
    meses = []
    y, m = hoy.year, hoy.month
    for _ in range(12):
        meses.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    meses.reverse()
    creadas = {}
    for (c,) in db.query(Leccion.created_at).filter(Leccion.created_at.isnot(None)).all():
        creadas[(c.year, c.month)] = creadas.get((c.year, c.month), 0) + 1
    return {
        "por_estado": {e: int(por_estado.get(e, 0)) for e in ESTADOS},
        "por_categoria": {k: int(v) for k, v in sorted(por_categoria.items(), key=lambda x: -x[1])},
        "por_tipo": {t: int(por_tipo.get(t, 0)) for t in TIPOS},
        "por_origen": {k: int(v) for k, v in por_origen.items()},
        "valoraciones": {v: int(usos.get(v, 0)) for v in VALORES_DE_USO},
        "valoraciones_total": total_usos,
        "efectividad_pct": round(utiles / total_usos * 100, 1) if total_usos else None,
        "mas_utiles": [{"id": l.id, "codigo": l.codigo, "titulo": l.titulo, "valoraciones_utiles": int(n)} for l, n in top],
        "acciones_abiertas": abiertas.count(),
        "acciones_vencidas": abiertas.filter(LeccionAccion.fecha_limite < hoy).count(),
        "pendientes_de_capturar": len(pendientes(db, usuario)),
        "por_mes": [{"mes": f"{y}-{m:02d}", "lecciones": creadas.get((y, m), 0), "en_curso": (y, m) == (hoy.year, hoy.month)}
                    for y, m in meses],
    }
