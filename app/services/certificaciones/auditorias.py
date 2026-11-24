"""Certificaciones: auditorías, hallazgos y acciones correctivas (§3.5).

- Auditoría: interna, certificación fase 1 y fase 2, seguimiento, renovación, de
  cliente y regulatoria; plan, agenda y muestras pedidas; entidad y auditor.
- Hallazgo: no conformidad mayor o menor, observación u oportunidad de mejora.
  `abierto → en_correccion → corregido → cerrado`.
- CAPA: análisis de causa, plan, plazo, responsable; nace como TAREA en el
  proyecto del programa (o en el proyecto de CAPA de la configuración);
  `abierta → en_curso → hecha → verificada | no_eficaz`.

Segregación (§3.10): quien corrigió un hallazgo (o hizo alguna de sus acciones)
no lo cierra; quien hizo una acción no verifica su eficacia.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.certificaciones import (
    CertAccion, CertAuditor, CertAuditoria, CertControl, CertEntidad, CertHallazgo, CertMarco, CertPrograma,
)
from app.services.certificaciones.comun import (
    ahora, auditar, avisar, config, dump, elegir, exigir_segregacion, fecha, hoy, iso, json_de, nombre_de, org_de,
    propio, siguiente_codigo, usuario_de_la_empresa,
)

TIPOS = ("interna", "certificacion_f1", "certificacion_f2", "seguimiento", "renovacion", "cliente", "regulatoria")
ESTADOS = ("planificada", "en_curso", "informe", "cerrada")
CONCLUSIONES = ("favorable", "con_condiciones", "desfavorable")
TIPOS_HALLAZGO = ("nc_mayor", "nc_menor", "observacion", "oportunidad")
ESTADOS_HALLAZGO = ("abierto", "en_correccion", "corregido", "cerrado")
ESTADOS_ACCION = ("abierta", "en_curso", "hecha", "verificada", "no_eficaz")


# ── Auditorías ───────────────────────────────────────────────────────────────

def serializar(db: Session, a: CertAuditoria) -> dict:
    marco = db.get(CertMarco, a.marco_id) if a.marco_id else None
    entidad = db.get(CertEntidad, a.entidad_id) if a.entidad_id else None
    auditor = db.get(CertAuditor, a.auditor_id) if a.auditor_id else None
    n = db.query(CertHallazgo).filter(CertHallazgo.auditoria_id == a.id).count()
    abiertos = db.query(CertHallazgo).filter(CertHallazgo.auditoria_id == a.id,
                                             CertHallazgo.estado != "cerrado").count()
    return {"id": a.id, "codigo": a.codigo, "programa_id": a.programa_id, "tipo": a.tipo,
            "marco": marco.clave if marco else None, "marco_id": a.marco_id, "estado": a.estado,
            "fecha_inicio": iso(a.fecha_inicio), "fecha_fin": iso(a.fecha_fin), "entidad_id": a.entidad_id,
            "entidad": entidad.nombre if entidad else None, "auditor_id": a.auditor_id,
            "auditor": auditor.nombre if auditor else None, "responsable_id": a.responsable_id,
            "responsable": nombre_de(db, a.responsable_id), "plan": a.plan, "agenda": json_de(a.agenda, []),
            "muestras": json_de(a.muestras, []), "resultado": a.resultado, "conclusion": a.conclusion,
            "hallazgos": n, "hallazgos_abiertos": abiertos, "cerrada_en": iso(a.cerrada_en)}


def listar(db: Session, usuario, programa_id: Optional[str] = None) -> list[dict]:
    org = org_de(usuario)
    q = db.query(CertAuditoria).filter(CertAuditoria.organization_id == org)
    if programa_id:
        q = q.filter(CertAuditoria.programa_id == programa_id)
    return [serializar(db, a) for a in q.order_by(CertAuditoria.fecha_inicio.desc().nullslast(),
                                                  CertAuditoria.created_at.desc()).all()]


def _aplicar(db: Session, a: CertAuditoria, org: str, datos: dict, usuario) -> None:
    if "tipo" in datos and datos["tipo"]:
        a.tipo = elegir(datos["tipo"], TIPOS, "tipo")
    if "estado" in datos and datos["estado"]:
        a.estado = elegir(datos["estado"], ESTADOS, "estado")
        a.cerrada_en = ahora() if a.estado == "cerrada" else None
    if "conclusion" in datos:
        a.conclusion = elegir(datos["conclusion"], CONCLUSIONES, "conclusion") if datos["conclusion"] else None
    if "marco" in datos:
        m = db.query(CertMarco).filter(CertMarco.organization_id == org, CertMarco.clave == datos["marco"]).first() \
            if datos["marco"] else None
        if datos["marco"] and m is None:
            raise error(422, "cert_campo_no_valido", campo="marco")
        a.marco_id = m.id if m else None
    for k, modelo, que in (("entidad_id", CertEntidad, "entidad"), ("auditor_id", CertAuditor, "auditor")):
        if k in datos:
            setattr(a, k, propio(db, modelo, datos[k], usuario, que).id if datos[k] else None)
    if "responsable_id" in datos:
        a.responsable_id = usuario_de_la_empresa(db, org, datos["responsable_id"], "responsable_id")
    for k in ("fecha_inicio", "fecha_fin"):
        if k in datos:
            setattr(a, k, fecha(datos[k], k))
    for k in ("plan", "resultado"):
        if k in datos:
            setattr(a, k, datos[k])
    for k in ("agenda", "muestras"):
        if k in datos and datos[k] is not None:
            if not isinstance(datos[k], list):
                raise error(422, "cert_campo_no_valido", campo=k)
            setattr(a, k, dump(datos[k]))


def crear(db: Session, usuario, datos: dict) -> dict:
    org = org_de(usuario)
    p = propio(db, CertPrograma, datos.get("programa_id"), usuario, "programa_de_certificacion")
    a = CertAuditoria(organization_id=org, programa_id=p.id, codigo=siguiente_codigo(db, CertAuditoria, org, "AUD"),
                      tipo=elegir(datos.get("tipo"), TIPOS, "tipo"), estado="planificada", creado_por=usuario.id,
                      responsable_id=usuario.id)
    _aplicar(db, a, org, {k: v for k, v in datos.items() if k not in ("tipo", "programa_id")}, usuario)
    db.add(a)
    db.flush()
    auditar(db, usuario, "CREATE", "auditoria", a.id, a.codigo, despues={"tipo": a.tipo, "programa": p.codigo})
    db.commit()
    return serializar(db, a)


def editar(db: Session, usuario, auditoria_id: str, datos: dict) -> dict:
    a = propio(db, CertAuditoria, auditoria_id, usuario, "auditoria")
    antes = serializar(db, a)
    _aplicar(db, a, a.organization_id, datos, usuario)
    if a.estado == "cerrada" and db.query(CertHallazgo).filter(
            CertHallazgo.auditoria_id == a.id, CertHallazgo.tipo == "nc_mayor",
            CertHallazgo.estado != "cerrado").first() is not None and a.conclusion == "favorable":
        raise error(409, "cert_auditoria_con_nc_mayor_abierta")
    auditar(db, usuario, "UPDATE", "auditoria", a.id, a.codigo,
            antes={k: antes[k] for k in ("estado", "conclusion")}, despues={"estado": a.estado,
                                                                             "conclusion": a.conclusion})
    db.commit()
    return serializar(db, a)


def detalle(db: Session, usuario, auditoria_id: str) -> dict:
    a = propio(db, CertAuditoria, auditoria_id, usuario, "auditoria")
    return {**serializar(db, a), "lista_hallazgos": hallazgos(db, usuario, auditoria_id=a.id)}


# ── Hallazgos ────────────────────────────────────────────────────────────────

def serializar_hallazgo(db: Session, h: CertHallazgo, con_acciones: bool = False) -> dict:
    control = db.get(CertControl, h.control_id) if h.control_id else None
    vencido = h.estado != "cerrado" and h.fecha_limite is not None and h.fecha_limite < hoy()
    d = {"id": h.id, "codigo": h.codigo, "auditoria_id": h.auditoria_id, "programa_id": h.programa_id,
         "tipo": h.tipo, "control_id": h.control_id, "control": control.clave_comun if control else None,
         "titulo": h.titulo, "descripcion": h.descripcion, "estado": h.estado, "fecha_limite": iso(h.fecha_limite),
         "vencido": vencido, "corregido_por": h.corregido_por, "corregido": nombre_de(db, h.corregido_por),
         "corregido_en": iso(h.corregido_en), "cerrado_por": h.cerrado_por, "cerrado": nombre_de(db, h.cerrado_por),
         "cerrado_en": iso(h.cerrado_en), "created_at": iso(h.created_at)}
    if con_acciones:
        d["acciones"] = [serializar_accion(db, x) for x in db.query(CertAccion).filter(
            CertAccion.hallazgo_id == h.id).order_by(CertAccion.created_at).all()]
    return d


def hallazgos(db: Session, usuario, *, programa_id: Optional[str] = None, auditoria_id: Optional[str] = None,
              solo_abiertos: bool = False) -> list[dict]:
    org = org_de(usuario)
    q = db.query(CertHallazgo).filter(CertHallazgo.organization_id == org)
    if programa_id:
        q = q.filter(CertHallazgo.programa_id == programa_id)
    if auditoria_id:
        q = q.filter(CertHallazgo.auditoria_id == auditoria_id)
    if solo_abiertos:
        q = q.filter(CertHallazgo.estado != "cerrado")
    return [serializar_hallazgo(db, h, con_acciones=True) for h in q.order_by(CertHallazgo.created_at.desc()).all()]


def crear_hallazgo(db: Session, usuario, auditoria_id: str, datos: dict) -> dict:
    a = propio(db, CertAuditoria, auditoria_id, usuario, "auditoria")
    org = a.organization_id
    control_id = propio(db, CertControl, datos["control_id"], usuario, "control").id if datos.get("control_id") \
        else None
    titulo = (datos.get("titulo") or "").strip()
    if not titulo:
        raise error(422, "cert_campo_no_valido", campo="titulo")
    h = CertHallazgo(organization_id=org, auditoria_id=a.id, programa_id=a.programa_id,
                     codigo=siguiente_codigo(db, CertHallazgo, org, "HAL"),
                     tipo=elegir(datos.get("tipo"), TIPOS_HALLAZGO, "tipo"), control_id=control_id,
                     titulo=titulo[:300], descripcion=datos.get("descripcion"),
                     fecha_limite=fecha(datos.get("fecha_limite"), "fecha_limite"), creado_por=usuario.id)
    db.add(h)
    db.flush()
    auditar(db, usuario, "CREATE", "hallazgo", h.id, h.codigo, despues={"tipo": h.tipo, "auditoria": a.codigo})
    db.commit()
    return serializar_hallazgo(db, h, True)


def editar_hallazgo(db: Session, usuario, hallazgo_id: str, datos: dict) -> dict:
    h = propio(db, CertHallazgo, hallazgo_id, usuario, "hallazgo")
    if h.estado == "cerrado":
        raise error(409, "cert_hallazgo_cerrado")
    for k in ("titulo", "descripcion"):
        if k in datos and datos[k] is not None:
            setattr(h, k, datos[k])
    if "tipo" in datos and datos["tipo"]:
        h.tipo = elegir(datos["tipo"], TIPOS_HALLAZGO, "tipo")
    if "fecha_limite" in datos:
        h.fecha_limite = fecha(datos["fecha_limite"], "fecha_limite")
    if "estado" in datos and datos["estado"] in ("abierto", "en_correccion"):
        h.estado = datos["estado"]
    auditar(db, usuario, "UPDATE", "hallazgo", h.id, h.codigo, despues={"estado": h.estado, "tipo": h.tipo})
    db.commit()
    return serializar_hallazgo(db, h, True)


def marcar_corregido(db: Session, usuario, hallazgo_id: str) -> dict:
    h = propio(db, CertHallazgo, hallazgo_id, usuario, "hallazgo")
    if h.estado == "cerrado":
        raise error(409, "cert_hallazgo_cerrado")
    h.estado = "corregido"
    h.corregido_por = usuario.id
    h.corregido_en = ahora()
    auditar(db, usuario, "CORRECT", "hallazgo", h.id, h.codigo)
    db.commit()
    return serializar_hallazgo(db, h, True)


def cerrar_hallazgo(db: Session, usuario, hallazgo_id: str, comentario: Optional[str] = None) -> dict:
    """SoD: quien lo corrigió (o hizo alguna de sus acciones) no lo cierra. Las acciones deben estar verificadas."""
    h = propio(db, CertHallazgo, hallazgo_id, usuario, "hallazgo")
    if h.estado != "corregido":
        raise error(409, "cert_hallazgo_sin_corregir")
    exigir_segregacion(db, usuario, h.corregido_por, "cert_sod_corrector_no_cierra", "hallazgo", h.id)
    acciones = db.query(CertAccion).filter(CertAccion.hallazgo_id == h.id).all()
    for x in acciones:
        exigir_segregacion(db, usuario, x.hecho_por, "cert_sod_corrector_no_cierra", "hallazgo", h.id)
    if h.tipo in ("nc_mayor", "nc_menor") and any(x.estado not in ("verificada",) for x in acciones):
        raise error(409, "cert_hallazgo_con_acciones_sin_verificar")
    h.estado = "cerrado"
    h.cerrado_por = usuario.id
    h.cerrado_en = ahora()
    auditar(db, usuario, "CLOSE", "hallazgo", h.id, h.codigo, despues={"comentario": comentario})
    db.commit()
    return serializar_hallazgo(db, h, True)


# ── Acciones correctivas (CAPA) ──────────────────────────────────────────────

def serializar_accion(db: Session, x: CertAccion) -> dict:
    task = None
    if x.task_id:
        from app.models.task import Task
        t = db.get(Task, x.task_id)
        if t is not None:
            task = {"id": t.id, "code": t.code, "status": getattr(t.status, "value", t.status),
                    "project_id": t.project_id}
    vencida = x.estado in ("abierta", "en_curso") and x.fecha_limite is not None and x.fecha_limite < hoy()
    return {"id": x.id, "hallazgo_id": x.hallazgo_id, "analisis_causa": x.analisis_causa, "plan": x.plan,
            "responsable_id": x.responsable_id, "responsable": nombre_de(db, x.responsable_id),
            "fecha_limite": iso(x.fecha_limite), "estado": x.estado, "vencida": vencida, "tarea": task,
            "hecho_por": x.hecho_por, "hecho": nombre_de(db, x.hecho_por), "hecho_en": iso(x.hecho_en),
            "verificacion": x.verificacion, "verificado_por": x.verificado_por,
            "verificado": nombre_de(db, x.verificado_por), "verificado_en": iso(x.verificado_en)}


def acciones(db: Session, usuario, *, programa_id: Optional[str] = None, solo_vencidas: bool = False) -> list[dict]:
    org = org_de(usuario)
    q = db.query(CertAccion).join(CertHallazgo, CertHallazgo.id == CertAccion.hallazgo_id).filter(
        CertAccion.organization_id == org)
    if programa_id:
        q = q.filter(CertHallazgo.programa_id == programa_id)
    filas = [serializar_accion(db, x) for x in q.order_by(CertAccion.fecha_limite.asc().nullslast()).all()]
    return [f for f in filas if f["vencida"]] if solo_vencidas else filas


def _crear_tarea(db: Session, usuario, h: CertHallazgo, x: CertAccion) -> Optional[str]:
    from app.models.task import Task, TaskPriority, TaskStatus
    from app.services.numbering import next_numbered_code
    programa = db.get(CertPrograma, h.programa_id)
    project_id = (programa.project_id if programa else None) or config(db, h.organization_id).proyecto_capa_id
    if not project_id:
        return None
    t = Task(organization_id=h.organization_id, project_id=project_id,
             code=next_numbered_code(db, "task", prefix="TSK", padding=5),
             title=f"CAPA {h.codigo}: {h.titulo}"[:255],
             description=f"{x.plan}\n\nCausa: {x.analisis_causa or '—'}",
             assignee_id=x.responsable_id, due_date=x.fecha_limite, status=TaskStatus.todo,
             priority=TaskPriority.high if h.tipo == "nc_mayor" else TaskPriority.medium,
             created_by=usuario.id)
    db.add(t)
    db.flush()
    return t.id


def crear_accion(db: Session, usuario, hallazgo_id: str, datos: dict) -> dict:
    h = propio(db, CertHallazgo, hallazgo_id, usuario, "hallazgo")
    if h.estado == "cerrado":
        raise error(409, "cert_hallazgo_cerrado")
    plan = (datos.get("plan") or "").strip()
    if not plan:
        raise error(422, "cert_campo_no_valido", campo="plan")
    x = CertAccion(organization_id=h.organization_id, hallazgo_id=h.id, analisis_causa=datos.get("analisis_causa"),
                   plan=plan, responsable_id=usuario_de_la_empresa(db, h.organization_id, datos.get("responsable_id"),
                                                                   "responsable_id"),
                   fecha_limite=fecha(datos.get("fecha_limite"), "fecha_limite") or h.fecha_limite,
                   estado="abierta", creado_por=usuario.id)
    db.add(x)
    db.flush()
    x.task_id = _crear_tarea(db, usuario, h, x)
    x.project_id = None
    if h.estado == "abierto":
        h.estado = "en_correccion"
    auditar(db, usuario, "CREATE", "accion", x.id, h.codigo, despues={"task_id": x.task_id,
                                                                       "fecha_limite": iso(x.fecha_limite)})
    avisar(db, x.responsable_id, "capa_asignada", h.codigo, x.id, "/certificaciones?tab=auditorias",
           titulo=h.titulo, fecha=iso(x.fecha_limite) or "—")
    db.commit()
    return serializar_accion(db, x)


def editar_accion(db: Session, usuario, accion_id: str, datos: dict) -> dict:
    x = propio(db, CertAccion, accion_id, usuario, "accion_correctiva")
    if x.estado in ("verificada",):
        raise error(409, "cert_accion_verificada")
    for k in ("analisis_causa", "plan"):
        if k in datos and datos[k] is not None:
            setattr(x, k, datos[k])
    if "fecha_limite" in datos:
        x.fecha_limite = fecha(datos["fecha_limite"], "fecha_limite")
    if "responsable_id" in datos:
        x.responsable_id = usuario_de_la_empresa(db, x.organization_id, datos["responsable_id"], "responsable_id")
    if "estado" in datos and datos["estado"] in ("abierta", "en_curso"):
        x.estado = datos["estado"]
    auditar(db, usuario, "UPDATE", "accion", x.id, x.hallazgo_id, despues={"estado": x.estado})
    db.commit()
    return serializar_accion(db, x)


def marcar_hecha(db: Session, usuario, accion_id: str) -> dict:
    x = propio(db, CertAccion, accion_id, usuario, "accion_correctiva")
    if x.estado not in ("abierta", "en_curso", "no_eficaz"):
        raise error(409, "cert_transicion_no_permitida", desde=x.estado, hasta="hecha")
    x.estado = "hecha"
    x.hecho_por = usuario.id
    x.hecho_en = ahora()
    auditar(db, usuario, "DONE", "accion", x.id, x.hallazgo_id)
    db.commit()
    return serializar_accion(db, x)


def verificar(db: Session, usuario, accion_id: str, eficaz: bool, verificacion: Optional[str]) -> dict:
    """Verificación de eficacia. SoD: quien hizo la acción no la verifica."""
    x = propio(db, CertAccion, accion_id, usuario, "accion_correctiva")
    if x.estado != "hecha":
        raise error(409, "cert_transicion_no_permitida", desde=x.estado, hasta="verificada")
    exigir_segregacion(db, usuario, x.hecho_por, "cert_sod_ejecutor_no_verifica", "accion", x.id)
    x.estado = "verificada" if eficaz else "no_eficaz"
    x.verificacion = verificacion
    x.verificado_por = usuario.id
    x.verificado_en = ahora()
    auditar(db, usuario, "VERIFY", "accion", x.id, x.hallazgo_id, despues={"eficaz": eficaz})
    db.commit()
    return serializar_accion(db, x)
