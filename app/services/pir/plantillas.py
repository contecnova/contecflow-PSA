"""PIR: configuración por empresa y plantillas (preguntas y criterios por tipo).

Docs: docs/PIR.md §«Configuración».

- `config(db, org)`: la fila de `pir_configuracion` de la empresa o, si no hay,
  una sin guardar con los valores de fábrica (7 días en cambios, 30 en
  proyectos, aviso 2 días antes, segregación activada, obligatoria en cambios
  normales y de emergencia, opcional en estándar y en proyectos).
- `resolver(db, org, ambito, tipo, idioma)`: qué cuestionario, plazo y
  obligatoriedad lleva una PIR nueva. Gana la plantilla activa de ese ámbito y
  tipo; si no, la del ámbito sin tipo; si no, la de fábrica (ITIL 4 en cambios,
  PMBOK en proyectos) en el idioma de la empresa. Lo que la plantilla deja vacío
  (`obligatorio`, `dias`) sale de la configuración.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.pir import PirConfiguracion, PirPlantilla
from app.services.formato_regional import IDIOMA_DE_RESPALDO

AMBITOS = ("change", "project")
TIPOS_DE_CAMBIO = ("standard", "normal", "emergency")
MOMENTOS_CAMBIO = ("implantacion", "cierre")
MOMENTOS_PROYECTO = ("go_live", "cierre", "ambos")

_CAMPOS_CONFIG = {
    "dias_cambio": int, "dias_proyecto": int, "aviso_dias_antes": int, "segregacion": bool,
    "momento_cambio": str, "momento_proyecto": str, "obligatorio_normal": bool, "obligatorio_emergencia": bool,
    "obligatorio_estandar": bool, "obligatorio_proyecto": bool, "proyecto_acciones_id": str,
}

# ── Cuestionarios de fábrica ─────────────────────────────────────────────────
# ITIL 4 (Change enablement, «post-implementation review»): objetivos, efectos
# no deseados, plazo/ventana, recursos, marcha atrás, satisfacción.
_CRITERIOS_CAMBIO = (
    ("objetivos", "Se consiguieron los objetivos del cambio", "The change achieved its objectives", "变更达到了预期目标"),
    ("sin_incidencias", "No provocó incidencias imprevistas", "It caused no unexpected incidents", "未引发意外事件"),
    ("ventana", "Se implantó en la ventana y el plazo previstos", "It was implemented within the planned window and schedule",
     "在计划的窗口和时间内实施"),
    ("recursos", "Recursos y coste según lo previsto", "Resources and cost as planned", "资源和成本符合计划"),
    ("marcha_atras", "El plan de marcha atrás no hizo falta o funcionó", "The rollback plan was not needed or worked",
     "无需回退或回退计划有效"),
    ("usuarios", "Usuarios y partes interesadas satisfechos", "Users and stakeholders are satisfied", "用户和相关方满意"),
)
# PMBOK (cierre del proyecto y transición): alcance, plazo, coste, calidad,
# beneficios y traspaso a operaciones.
_CRITERIOS_PROYECTO = (
    ("alcance", "Se entregó el alcance acordado", "The agreed scope was delivered", "交付了约定的范围"),
    ("plazo", "Se cumplió el plazo", "The schedule was met", "按期完成"),
    ("coste", "Se cumplió el presupuesto", "The budget was met", "预算得到遵守"),
    ("calidad", "El cliente aceptó los entregables (calidad)", "The customer accepted the deliverables (quality)",
     "客户验收了交付物（质量）"),
    ("beneficios", "Los beneficios previstos se están consiguiendo", "The expected benefits are being realised",
     "预期收益正在实现"),
    ("transicion", "La transición a operaciones o al cliente está completa",
     "The handover to operations or the customer is complete", "向运维或客户的移交已完成"),
)
_PREGUNTAS = (
    ("bien", "¿Qué fue bien?", "What went well?", "哪些方面做得好？"),
    ("mejorar", "¿Qué se puede mejorar?", "What could be improved?", "哪些方面可以改进？"),
    ("distinto", "¿Qué haríamos distinto la próxima vez?", "What would we do differently next time?",
     "下次我们会有什么不同的做法？"),
)
_PREGUNTA_RIESGOS = ("riesgos", "¿Qué riesgos se materializaron y cómo se trataron?",
                     "Which risks materialised and how were they handled?", "哪些风险发生了，如何处理的？")


def org_de(usuario) -> Optional[str]:
    """La empresa activa de la petición (no la de la ficha: hay usuarios en varias empresas)."""
    from app.services.service_desk.scoping import empresa_activa
    # Siempre texto: la empresa de `db.info` puede venir como entero y se compara
    # con `organization_id` (String) de cambios y proyectos; 1 != "1" daba 404.
    org = empresa_activa(usuario)
    return None if org is None else str(org)


def _en(fila: tuple, idioma: str) -> dict:
    i = {"es": 1, "en": 2, "zh": 3}.get((idioma or IDIOMA_DE_RESPALDO)[:2], 1)
    return {"clave": fila[0], "texto": fila[i]}


def de_fabrica(ambito: str, idioma: str = "es") -> dict:
    """Criterios y preguntas de fábrica del ámbito, en el idioma pedido."""
    criterios = _CRITERIOS_CAMBIO if ambito == "change" else _CRITERIOS_PROYECTO
    preguntas = _PREGUNTAS + ((_PREGUNTA_RIESGOS,) if ambito == "project" else ())
    return {"criterios": [_en(c, idioma) for c in criterios], "preguntas": [_en(p, idioma) for p in preguntas]}


# ── Configuración ────────────────────────────────────────────────────────────

def config(db: Session, org: Optional[str]) -> PirConfiguracion:
    fila = db.query(PirConfiguracion).filter(PirConfiguracion.organization_id == org).first()
    if fila is not None:
        return fila
    return PirConfiguracion(organization_id=org, dias_cambio=7, dias_proyecto=30, aviso_dias_antes=2,
                            segregacion=True, momento_cambio="implantacion", momento_proyecto="ambos",
                            obligatorio_normal=True, obligatorio_emergencia=True, obligatorio_estandar=False,
                            obligatorio_proyecto=False, proyecto_acciones_id=None)


def config_dict(c: PirConfiguracion) -> dict:
    return {k: getattr(c, k) for k in _CAMPOS_CONFIG}


def guardar_config(db: Session, usuario, datos: dict) -> dict:
    from app.services.audit import audit_log
    org = org_de(usuario)
    fila = db.query(PirConfiguracion).filter(PirConfiguracion.organization_id == org).first()
    antes = config_dict(fila or config(db, org))
    if fila is None:
        fila = config(db, org)
        db.add(fila)
    for campo, tipo in _CAMPOS_CONFIG.items():
        if campo not in datos:
            continue
        valor = datos[campo]
        if campo == "proyecto_acciones_id":
            valor = valor or None
            if valor:
                from app.models.project import Project
                if db.query(Project.id).filter(Project.id == valor, Project.organization_id == org).first() is None:
                    raise error(404, "no_encontrado", que="proyecto")
        elif tipo is int:
            valor = int(valor)
            if valor < 0 or valor > 365:
                raise error(422, "pir_config_no_valida", campo=campo)
        elif tipo is bool:
            valor = bool(valor)
        setattr(fila, campo, valor)
    if fila.momento_cambio not in MOMENTOS_CAMBIO:
        raise error(422, "pir_config_no_valida", campo="momento_cambio")
    if fila.momento_proyecto not in MOMENTOS_PROYECTO:
        raise error(422, "pir_config_no_valida", campo="momento_proyecto")
    fila.updated_por = usuario.id
    db.flush()
    audit_log(db, usuario, "UPDATE", "pir_configuracion", fila.id, "PIR", old_values=antes, new_values=config_dict(fila))
    db.commit()
    return config_dict(fila)


def obligatorio_por_defecto(c: PirConfiguracion, ambito: str, tipo: Optional[str]) -> bool:
    if ambito == "change":
        return bool({"normal": c.obligatorio_normal, "emergency": c.obligatorio_emergencia,
                     "standard": c.obligatorio_estandar}.get(tipo or "normal", c.obligatorio_normal))
    return bool(c.obligatorio_proyecto)


# ── Plantillas ───────────────────────────────────────────────────────────────

def _lista(raw) -> list:
    try:
        v = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return v if isinstance(v, list) else []


def _limpiar_items(items, campo: str) -> str:
    """`[{clave, texto}]` sin vacíos ni claves repetidas; la clave sale del texto si falta."""
    import re
    vistos, salida = set(), []
    for i, it in enumerate(items or []):
        if not isinstance(it, dict):
            raise error(422, "pir_plantilla_no_valida", campo=campo)
        texto = str(it.get("texto") or "").strip()
        if not texto:
            continue
        clave = str(it.get("clave") or "").strip() or re.sub(r"[^a-z0-9]+", "_", texto.lower())[:40].strip("_") or f"c{i}"
        if clave in vistos:
            raise error(422, "pir_plantilla_no_valida", campo=campo)
        vistos.add(clave)
        salida.append({"clave": clave, "texto": texto[:500]})
    return json.dumps(salida, ensure_ascii=False)


def plantilla_dict(p: PirPlantilla) -> dict:
    return {"id": p.id, "nombre": p.nombre, "ambito": p.ambito, "tipo": p.tipo, "obligatorio": p.obligatorio,
            "dias": p.dias, "criterios": _lista(p.criterios), "preguntas": _lista(p.preguntas),
            "activo": bool(p.activo), "updated_at": (p.updated_at or p.created_at).isoformat()
            if (p.updated_at or p.created_at) else None}


def listar_plantillas(db: Session, usuario, ambito: Optional[str] = None) -> list[dict]:
    q = db.query(PirPlantilla).filter(PirPlantilla.organization_id == org_de(usuario))
    if ambito:
        q = q.filter(PirPlantilla.ambito == ambito)
    return [plantilla_dict(p) for p in q.order_by(PirPlantilla.ambito, PirPlantilla.tipo, PirPlantilla.nombre).all()]


def _cargar_plantilla(db: Session, usuario, pid: str) -> PirPlantilla:
    p = db.query(PirPlantilla).filter(PirPlantilla.id == pid,
                                      PirPlantilla.organization_id == org_de(usuario)).first()
    if p is None:
        raise error(404, "no_encontrado", que="plantilla")
    return p


def guardar_plantilla(db: Session, usuario, datos: dict, pid: Optional[str] = None) -> dict:
    from app.services.audit import audit_log
    p = _cargar_plantilla(db, usuario, pid) if pid else PirPlantilla(organization_id=org_de(usuario),
                                                                     creado_por=usuario.id)
    antes = plantilla_dict(p) if pid else None
    if "nombre" in datos:
        p.nombre = str(datos["nombre"] or "").strip()[:200]
    if "ambito" in datos:
        if datos["ambito"] not in AMBITOS:
            raise error(422, "pir_plantilla_no_valida", campo="ambito")
        p.ambito = datos["ambito"]
    if "tipo" in datos:
        p.tipo = (str(datos["tipo"]).strip() or None) if datos["tipo"] else None
    if "obligatorio" in datos:
        p.obligatorio = None if datos["obligatorio"] is None else bool(datos["obligatorio"])
    if "dias" in datos:
        p.dias = None if datos["dias"] in (None, "") else int(datos["dias"])
        if p.dias is not None and not 0 <= p.dias <= 365:
            raise error(422, "pir_plantilla_no_valida", campo="dias")
    if "criterios" in datos:
        p.criterios = _limpiar_items(datos["criterios"], "criterios")
    if "preguntas" in datos:
        p.preguntas = _limpiar_items(datos["preguntas"], "preguntas")
    if "activo" in datos:
        p.activo = bool(datos["activo"])
    if not p.nombre or p.ambito not in AMBITOS:
        raise error(422, "campos_obligatorios", campos="nombre, ambito")
    if p.ambito == "change" and p.tipo and p.tipo not in TIPOS_DE_CAMBIO:
        raise error(422, "pir_plantilla_no_valida", campo="tipo")
    db.add(p)
    db.flush()
    audit_log(db, usuario, "UPDATE" if pid else "CREATE", "pir_plantilla", p.id, p.nombre, old_values=antes,
              new_values=plantilla_dict(p))
    db.commit()
    return plantilla_dict(p)


def borrar_plantilla(db: Session, usuario, pid: str) -> None:
    from app.services.audit import audit_log
    p = _cargar_plantilla(db, usuario, pid)
    audit_log(db, usuario, "DELETE", "pir_plantilla", p.id, p.nombre, old_values=plantilla_dict(p))
    db.delete(p)
    db.commit()


def resolver(db: Session, org: Optional[str], ambito: str, tipo: Optional[str], idioma: str = "es") -> dict:
    """`{plantilla_id, criterios, preguntas, obligatorio, dias}` para una PIR nueva."""
    c = config(db, org)
    base = db.query(PirPlantilla).filter(PirPlantilla.organization_id == org, PirPlantilla.ambito == ambito,
                                         PirPlantilla.activo.is_(True))
    p = (base.filter(PirPlantilla.tipo == tipo).order_by(PirPlantilla.created_at).first() if tipo else None) \
        or base.filter(PirPlantilla.tipo.is_(None)).order_by(PirPlantilla.created_at).first()
    fabrica = de_fabrica(ambito, idioma)
    criterios = _lista(p.criterios) if p is not None and _lista(p.criterios) else fabrica["criterios"]
    preguntas = _lista(p.preguntas) if p is not None and _lista(p.preguntas) else fabrica["preguntas"]
    obligatorio = p.obligatorio if p is not None and p.obligatorio is not None else obligatorio_por_defecto(c, ambito, tipo)
    dias = p.dias if p is not None and p.dias is not None else (c.dias_cambio if ambito == "change" else c.dias_proyecto)
    return {"plantilla_id": p.id if p is not None else None, "criterios": criterios, "preguntas": preguntas,
            "obligatorio": bool(obligatorio), "dias": int(dias)}
