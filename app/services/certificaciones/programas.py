"""Certificaciones: programas (§3.2), declaración de aplicabilidad y matriz (§3.3).

Programa: alcance (entidades, sedes, países, plantas OT, sistemas, procesos,
zonas con su SL objetivo), objetivos por marco y nivel, gobierno (responsable,
patrocinador de la dirección, calendario) y su proyecto.

Declaración de aplicabilidad: una fila por control común que exige alguno de
los objetivos (filtrando por los niveles del objetivo: TISAX AL2/AL3/prototipos,
partes de 62443…). La fila de sede vacía vale para toda la organización; una
sede que difiere tiene su propia fila (`dividir_por_sede`).

Segregación de funciones (§3.10):
- quien implanta un control (`implantado_por`) no lo da por eficaz;
- quien prueba no es quien implanta.

Matriz: control × marco × sede × estado (cumple, en curso, pendiente, no
cumple, caducado, no aplica). Cumplimiento continuo (`medir`): los controles
con `medible_por_plataforma` se marcan solos y aportan su evidencia firmada con
su huella; las tareas enlazadas que se cierran aportan la suya.
"""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

import logging

from app.core.codigos_de_error import error
from app.models.certificaciones import (
    CertAplicabilidad, CertControl, CertControlTarea, CertCorrespondencia, CertEvidencia, CertMarco, CertPrograma,
    CertPrueba,
)
from app.services.certificaciones import catalogo
from app.services.certificaciones import evidencias as ev_svc
from app.services.certificaciones.comun import (
    ahora, auditar, config, dump, elegir, exigir_segregacion, fecha, hoy, iso, json_de, nombre_de, org_de, propio,
    siguiente_codigo, usuario_de_la_empresa,
)

logger = logging.getLogger(__name__)

ESTADOS_PROGRAMA = ("borrador", "en_curso", "certificado", "suspendido", "cerrado")
ESTADOS_FILA = ("pendiente", "en_curso", "implantado")
EFICACIAS = ("sin_evaluar", "eficaz", "parcial", "no_eficaz")
TIPOS_PRUEBA = ("diseno", "eficacia_operativa")
RESULTADOS_PRUEBA = ("pendiente", "superada", "con_excepciones", "fallida")
ESTADOS_MATRIZ = ("cumple", "en_curso", "pendiente", "no_cumple", "caducado", "no_aplica")
CLAVES_DE_ALCANCE = ("entidades", "sedes", "paises", "plantas_ot", "sistemas", "procesos", "zonas")


# ── Programas ────────────────────────────────────────────────────────────────

def _alcance(datos) -> dict:
    datos = datos or {}
    salida = {}
    for k in CLAVES_DE_ALCANCE:
        v = datos.get(k) or []
        if not isinstance(v, list):
            raise error(422, "cert_campo_no_valido", campo=f"alcance.{k}")
        salida[k] = v
    return salida


def _objetivos(db: Session, org: str, objetivos) -> list[dict]:
    claves = {m.clave for m in db.query(CertMarco).filter(CertMarco.organization_id == org).all()}
    salida = []
    for o in objetivos or []:
        if not isinstance(o, dict) or o.get("marco") not in claves:
            raise error(422, "cert_campo_no_valido", campo="objetivos.marco")
        niveles = o.get("niveles")
        if niveles is not None and not isinstance(niveles, list):
            raise error(422, "cert_campo_no_valido", campo="objetivos.niveles")
        salida.append({"marco": o["marco"], "nivel": o.get("nivel"), "niveles": niveles,
                       "sl_objetivo": o.get("sl_objetivo")})
    return salida


def serializar(db: Session, p: CertPrograma, detalle: bool = False) -> dict:
    d = {"id": p.id, "codigo": p.codigo, "nombre": p.nombre, "descripcion": p.descripcion, "estado": p.estado,
         "alcance": json_de(p.alcance, {}), "objetivos": json_de(p.objetivos, []),
         "responsable_id": p.responsable_id, "responsable": nombre_de(db, p.responsable_id),
         "patrocinador_id": p.patrocinador_id, "patrocinador": nombre_de(db, p.patrocinador_id),
         "fecha_inicio": iso(p.fecha_inicio), "fecha_objetivo": iso(p.fecha_objetivo), "project_id": p.project_id,
         "plantilla_clave": p.plantilla_clave, "parametros": json_de(p.parametros, {}),
         "created_at": iso(p.created_at)}
    if detalle:
        from sqlalchemy import func
        d["filas"] = db.query(func.count(CertAplicabilidad.id)).filter(
            CertAplicabilidad.programa_id == p.id).scalar() or 0
    return d


def listar(db: Session, usuario) -> list[dict]:
    org = org_de(usuario)
    catalogo.asegurar_sembrado(db, org)
    return [serializar(db, p) for p in db.query(CertPrograma).filter(CertPrograma.organization_id == org)
            .order_by(CertPrograma.created_at.desc()).all()]


def crear(db: Session, usuario, datos: dict, *, confirmar: bool = True) -> CertPrograma:
    org = org_de(usuario)
    catalogo.asegurar_sembrado(db, org)
    nombre = (datos.get("nombre") or "").strip()
    if not nombre:
        raise error(422, "cert_campo_no_valido", campo="nombre")
    p = CertPrograma(
        organization_id=org, codigo=siguiente_codigo(db, CertPrograma, org, "CERT"), nombre=nombre[:300],
        descripcion=datos.get("descripcion"), estado="borrador", alcance=dump(_alcance(datos.get("alcance"))),
        objetivos=dump(_objetivos(db, org, datos.get("objetivos"))),
        responsable_id=usuario_de_la_empresa(db, org, datos.get("responsable_id"), "responsable_id") or usuario.id,
        patrocinador_id=usuario_de_la_empresa(db, org, datos.get("patrocinador_id"), "patrocinador_id"),
        fecha_inicio=fecha(datos.get("fecha_inicio"), "fecha_inicio") or hoy(),
        fecha_objetivo=fecha(datos.get("fecha_objetivo"), "fecha_objetivo"),
        plantilla_clave=datos.get("plantilla_clave"), parametros=dump(datos.get("parametros")),
        creado_por=usuario.id)
    db.add(p)
    db.flush()
    n = poblar_aplicabilidad(db, p)
    auditar(db, usuario, "CREATE", "programa", p.id, p.codigo,
            despues={"nombre": p.nombre, "objetivos": json_de(p.objetivos, []), "filas": n})
    if confirmar:
        db.commit()
    return p


def editar(db: Session, usuario, programa_id: str, datos: dict) -> dict:
    p = propio(db, CertPrograma, programa_id, usuario, "programa_de_certificacion")
    org = p.organization_id
    antes = serializar(db, p)
    if "nombre" in datos and datos["nombre"]:
        p.nombre = datos["nombre"].strip()[:300]
    if "descripcion" in datos:
        p.descripcion = datos["descripcion"]
    if "estado" in datos and datos["estado"]:
        p.estado = elegir(datos["estado"], ESTADOS_PROGRAMA, "estado")
    if "alcance" in datos and datos["alcance"] is not None:
        p.alcance = dump(_alcance(datos["alcance"]))
    for k in ("responsable_id", "patrocinador_id"):
        if k in datos:
            setattr(p, k, usuario_de_la_empresa(db, org, datos[k], k))
    for k in ("fecha_inicio", "fecha_objetivo"):
        if k in datos:
            setattr(p, k, fecha(datos[k], k))
    nuevas = 0
    if "objetivos" in datos and datos["objetivos"] is not None:
        p.objetivos = dump(_objetivos(db, org, datos["objetivos"]))
        db.flush()
        nuevas = poblar_aplicabilidad(db, p)
    auditar(db, usuario, "UPDATE", "programa", p.id, p.codigo, antes=antes, despues=serializar(db, p),
            meta={"filas_nuevas": nuevas})
    db.commit()
    return serializar(db, p, detalle=True)


def borrar(db: Session, usuario, programa_id: str) -> None:
    """Borra el programa con sus filas, pruebas, evidencias y auditorías (bloqueo legal al confirmar)."""
    p = propio(db, CertPrograma, programa_id, usuario, "programa_de_certificacion")
    auditar(db, usuario, "DELETE", "programa", p.id, p.codigo, antes=serializar(db, p))
    db.delete(p)
    db.commit()


# ── Declaración de aplicabilidad ─────────────────────────────────────────────

def controles_del_programa(db: Session, p: CertPrograma) -> dict[str, list[tuple[str, str, Optional[str]]]]:
    """control_id → [(marco, id_control, nivel)] que exigen los objetivos del programa."""
    org = p.organization_id
    marcos = {m.clave: m for m in db.query(CertMarco).filter(CertMarco.organization_id == org).all()}
    salida: dict[str, list] = {}
    for o in json_de(p.objetivos, []):
        m = marcos.get(o.get("marco"))
        if m is None:
            continue
        niveles = o.get("niveles")
        for r in db.query(CertCorrespondencia).filter(CertCorrespondencia.organization_id == org,
                                                       CertCorrespondencia.marco_id == m.id).all():
            if niveles and r.nivel is not None and r.nivel not in niveles:
                continue
            salida.setdefault(r.control_id, []).append((m.clave, r.id_control, r.nivel))
    return salida


def poblar_aplicabilidad(db: Session, p: CertPrograma) -> int:
    """Crea las filas (sede general) que faltan para los controles exigidos. Idempotente; no borra."""
    exigidos = controles_del_programa(db, p)
    hay = {r[0] for r in db.query(CertAplicabilidad.control_id).filter(
        CertAplicabilidad.programa_id == p.id, CertAplicabilidad.sede == "").all()}
    n = 0
    for control_id in exigidos:
        if control_id in hay:
            continue
        db.add(CertAplicabilidad(organization_id=p.organization_id, programa_id=p.id, control_id=control_id,
                                 sede="", aplica=True, estado="pendiente", eficacia="sin_evaluar",
                                 responsable_id=p.responsable_id))
        n += 1
    db.flush()
    return n


def serializar_fila(db: Session, f: CertAplicabilidad, control: Optional[CertControl] = None,
                    marcos: Optional[list] = None, evidencias: Optional[list] = None, cfg=None,
                    cache: Optional[dict] = None) -> dict:
    control = control or db.get(CertControl, f.control_id)
    cfg = cfg or config(db, f.organization_id)
    evs = evidencias if evidencias is not None else ev_svc.de_la_fila(db, f)
    estados = [ev_svc.estado(db, e, cfg, cache) for e in evs]
    return {"id": f.id, "programa_id": f.programa_id, "control_id": f.control_id,
            "control": control.clave_comun if control else None, "titulo": control.titulo if control else None,
            "dominio": control.dominio if control else None,
            "medible": control.medible_por_plataforma if control else None, "marcos": marcos or [],
            "sede": f.sede, "aplica": f.aplica, "justificacion": f.justificacion, "estado": f.estado,
            "eficacia": f.eficacia, "responsable_id": f.responsable_id, "implantado_por": f.implantado_por,
            "implantado_en": iso(f.implantado_en), "eficacia_por": f.eficacia_por, "eficacia_en": iso(f.eficacia_en),
            "ultima_revision": iso(f.ultima_revision), "medicion": f.medicion, "medicion_en": iso(f.medicion_en),
            "evidencias": len(evs), "evidencias_validas": estados.count("valida"),
            "evidencias_caducadas": estados.count("caducada"),
            "estado_matriz": estado_matriz(f, estados)}


def estado_matriz(f: CertAplicabilidad, estados_evidencia: list[str]) -> str:
    if not f.aplica:
        return "no_aplica"
    if f.medicion == "attention" or f.eficacia == "no_eficaz":
        return "no_cumple"
    validas = estados_evidencia.count("valida") > 0
    if f.estado == "implantado":
        if not validas and "caducada" in estados_evidencia:
            return "caducado"
        if validas and f.eficacia == "eficaz":
            return "cumple"
        return "en_curso"
    return "en_curso" if f.estado == "en_curso" else "pendiente"


def aplicabilidad(db: Session, usuario, programa_id: str, *, marco: Optional[str] = None,
                  sede: Optional[str] = None, estado: Optional[str] = None, q: Optional[str] = None) -> list[dict]:
    p = propio(db, CertPrograma, programa_id, usuario, "programa_de_certificacion")
    exigidos = controles_del_programa(db, p)
    cfg = config(db, p.organization_id)
    evs = ev_svc.por_control(db, p.organization_id, p.id)
    controles = {c.id: c for c in db.query(CertControl).filter(CertControl.organization_id == p.organization_id)}
    cache: dict = {}
    q_ = db.query(CertAplicabilidad).filter(CertAplicabilidad.programa_id == p.id)
    if sede is not None:
        q_ = q_.filter(CertAplicabilidad.sede == sede)
    salida = []
    for f in q_.all():
        ms = [{"marco": m, "id_control": i, "nivel": n} for m, i, n in exigidos.get(f.control_id, [])]
        if marco and not any(x["marco"] == marco for x in ms):
            continue
        c = controles.get(f.control_id)
        if q and c and q.lower() not in (c.titulo + c.clave_comun).lower():
            continue
        propias = [e for e in evs.get(f.control_id, []) if e.aplicabilidad_id in (None, f.id)]
        fila = serializar_fila(db, f, c, ms, propias, cfg, cache)
        if estado and fila["estado_matriz"] != estado:
            continue
        salida.append(fila)
    salida.sort(key=lambda x: (x["dominio"] or "", x["control"] or "", x["sede"]))
    return salida


def editar_fila(db: Session, usuario, fila_id: str, datos: dict) -> dict:
    """Aplica/justificación, estado de implantación, responsable y revisión. La eficacia va aparte (SoD)."""
    f = propio(db, CertAplicabilidad, fila_id, usuario, "fila_de_aplicabilidad")
    antes = {k: getattr(f, k) for k in ("aplica", "justificacion", "estado", "responsable_id")}
    if "aplica" in datos and datos["aplica"] is not None:
        f.aplica = bool(datos["aplica"])
        if not f.aplica and not (datos.get("justificacion") or f.justificacion):
            raise error(422, "cert_exclusion_sin_justificacion")
    if "justificacion" in datos:
        f.justificacion = datos["justificacion"]
    if "responsable_id" in datos:
        f.responsable_id = usuario_de_la_empresa(db, f.organization_id, datos["responsable_id"], "responsable_id")
    if "estado" in datos and datos["estado"]:
        nuevo = elegir(datos["estado"], ESTADOS_FILA, "estado")
        if nuevo == "implantado" and f.estado != "implantado":
            f.implantado_por = usuario.id
            f.implantado_en = ahora()
        if nuevo != "implantado":
            f.implantado_por = f.implantado_en = None
            f.eficacia = "sin_evaluar"
            f.eficacia_por = f.eficacia_en = None
        f.estado = nuevo
    f.ultima_revision = hoy()
    auditar(db, usuario, "UPDATE", "aplicabilidad", f.id, f.control_id, antes=antes,
            despues={k: getattr(f, k) for k in antes})
    db.commit()
    return serializar_fila(db, f)


def evaluar_eficacia(db: Session, usuario, fila_id: str, eficacia: str, comentario: Optional[str] = None) -> dict:
    """SoD: quien implantó el control no lo da por eficaz."""
    f = propio(db, CertAplicabilidad, fila_id, usuario, "fila_de_aplicabilidad")
    elegir(eficacia, EFICACIAS, "eficacia")
    if f.estado != "implantado" and eficacia != "sin_evaluar":
        raise error(409, "cert_eficacia_sin_implantar")
    exigir_segregacion(db, usuario, f.implantado_por, "cert_sod_implantador_no_evalua", "aplicabilidad", f.id)
    antes = f.eficacia
    f.eficacia = eficacia
    f.eficacia_por = usuario.id
    f.eficacia_en = ahora()
    f.ultima_revision = hoy()
    auditar(db, usuario, "EVALUATE", "aplicabilidad", f.id, f.control_id, antes={"eficacia": antes},
            despues={"eficacia": eficacia, "comentario": comentario})
    db.commit()
    return serializar_fila(db, f)


def dividir_por_sede(db: Session, usuario, fila_id: str, sede: str) -> dict:
    """Fila propia de una sede (copia la general) para un control que difiere en esa sede."""
    f = propio(db, CertAplicabilidad, fila_id, usuario, "fila_de_aplicabilidad")
    sede = (sede or "").strip()[:120]
    if not sede:
        raise error(422, "cert_campo_no_valido", campo="sede")
    hay = db.query(CertAplicabilidad).filter(CertAplicabilidad.programa_id == f.programa_id,
                                             CertAplicabilidad.control_id == f.control_id,
                                             CertAplicabilidad.sede == sede).first()
    if hay is not None:
        return serializar_fila(db, hay)
    nueva = CertAplicabilidad(organization_id=f.organization_id, programa_id=f.programa_id, control_id=f.control_id,
                              sede=sede, aplica=f.aplica, justificacion=f.justificacion, estado="pendiente",
                              eficacia="sin_evaluar", responsable_id=f.responsable_id)
    db.add(nueva)
    db.flush()
    auditar(db, usuario, "CREATE", "aplicabilidad", nueva.id, f"{f.control_id}@{sede}")
    db.commit()
    return serializar_fila(db, nueva)


def enlazar_tarea(db: Session, usuario, fila_id: str, task_id: str) -> dict:
    f = propio(db, CertAplicabilidad, fila_id, usuario, "fila_de_aplicabilidad")
    from app.models.task import Task
    t = db.get(Task, task_id)
    if t is None or t.organization_id != f.organization_id:
        raise error(422, "cert_campo_no_valido", campo="task_id")
    hay = db.query(CertControlTarea).filter(CertControlTarea.aplicabilidad_id == f.id,
                                            CertControlTarea.task_id == t.id).first()
    if hay is None:
        db.add(CertControlTarea(organization_id=f.organization_id, aplicabilidad_id=f.id, task_id=t.id))
        auditar(db, usuario, "LINK", "aplicabilidad", f.id, t.id)
        db.commit()
    return {"ok": True}


def tareas_de_fila(db: Session, usuario, fila_id: str) -> list[dict]:
    f = propio(db, CertAplicabilidad, fila_id, usuario, "fila_de_aplicabilidad")
    from app.models.task import Task
    salida = []
    for enlace in db.query(CertControlTarea).filter(CertControlTarea.aplicabilidad_id == f.id).all():
        t = db.get(Task, enlace.task_id)
        if t is not None:
            salida.append({"id": t.id, "code": t.code, "title": t.title,
                           "status": getattr(t.status, "value", t.status), "project_id": t.project_id})
    return salida


# ── Pruebas de control (SOX / J-SOX) ─────────────────────────────────────────

def serializar_prueba(db: Session, pr: CertPrueba) -> dict:
    return {"id": pr.id, "aplicabilidad_id": pr.aplicabilidad_id, "tipo": pr.tipo,
            "periodo_desde": iso(pr.periodo_desde), "periodo_hasta": iso(pr.periodo_hasta),
            "poblacion": pr.poblacion, "muestra": pr.muestra, "metodo": pr.metodo, "resultado": pr.resultado,
            "excepciones": pr.excepciones, "probado_por": pr.probado_por, "probado": nombre_de(db, pr.probado_por),
            "probado_en": iso(pr.probado_en), "notas": pr.notas}


def pruebas(db: Session, usuario, fila_id: str) -> list[dict]:
    f = propio(db, CertAplicabilidad, fila_id, usuario, "fila_de_aplicabilidad")
    return [serializar_prueba(db, x) for x in db.query(CertPrueba).filter(CertPrueba.aplicabilidad_id == f.id)
            .order_by(CertPrueba.created_at.desc()).all()]


def registrar_prueba(db: Session, usuario, fila_id: str, datos: dict) -> dict:
    """SoD: quien prueba no es quien implantó. Muestra ≤ población."""
    f = propio(db, CertAplicabilidad, fila_id, usuario, "fila_de_aplicabilidad")
    exigir_segregacion(db, usuario, f.implantado_por, "cert_sod_implantador_no_prueba", "aplicabilidad", f.id)
    tipo = elegir(datos.get("tipo"), TIPOS_PRUEBA, "tipo")
    resultado = elegir(datos.get("resultado") or "pendiente", RESULTADOS_PRUEBA, "resultado")
    poblacion, muestra = datos.get("poblacion"), datos.get("muestra")
    if poblacion is not None and muestra is not None and int(muestra) > int(poblacion):
        raise error(422, "cert_muestra_mayor_que_poblacion")
    pr = CertPrueba(organization_id=f.organization_id, aplicabilidad_id=f.id, tipo=tipo,
                    periodo_desde=fecha(datos.get("periodo_desde"), "periodo_desde"),
                    periodo_hasta=fecha(datos.get("periodo_hasta"), "periodo_hasta"),
                    poblacion=poblacion, muestra=muestra, metodo=datos.get("metodo"), resultado=resultado,
                    excepciones=datos.get("excepciones"), probado_por=usuario.id, probado_en=ahora(),
                    notas=datos.get("notas"))
    db.add(pr)
    db.flush()
    auditar(db, usuario, "TEST", "prueba", pr.id, f.control_id,
            despues={"tipo": tipo, "resultado": resultado, "poblacion": poblacion, "muestra": muestra})
    db.commit()
    return serializar_prueba(db, pr)


# ── Matriz cruzada ───────────────────────────────────────────────────────────

def matriz(db: Session, usuario, programa_id: str) -> dict:
    """Control × marco × sede × estado, con totales por marco y por sede."""
    p = propio(db, CertPrograma, programa_id, usuario, "programa_de_certificacion")
    filas = aplicabilidad(db, usuario, programa_id)
    alcance = json_de(p.alcance, {})
    sedes = [""] + [s if isinstance(s, str) else (s or {}).get("nombre", "") for s in alcance.get("sedes") or []]
    generales = {f["control_id"]: f for f in filas if f["sede"] == ""}
    por_sede = {(f["control_id"], f["sede"]): f for f in filas if f["sede"]}
    marcos = sorted({m["marco"] for f in filas for m in f["marcos"]})
    totales = {m: {e: 0 for e in ESTADOS_MATRIZ} for m in marcos}
    totales_sede = {s: {e: 0 for e in ESTADOS_MATRIZ} for s in sedes}
    controles = []
    for control_id, g in sorted(generales.items(), key=lambda x: (x[1]["dominio"] or "", x[1]["control"] or "")):
        celdas = {}
        for s in sedes:
            f = por_sede.get((control_id, s), g) if s else g
            celdas[s] = f["estado_matriz"]
            totales_sede[s][f["estado_matriz"]] += 1
        for m in {x["marco"] for x in g["marcos"]}:
            totales[m][g["estado_matriz"]] += 1
        controles.append({"control_id": control_id, "control": g["control"], "titulo": g["titulo"],
                          "dominio": g["dominio"], "marcos": g["marcos"], "fila_id": g["id"], "sedes": celdas})
    return {"programa_id": p.id, "marcos": marcos, "sedes": sedes, "estados": list(ESTADOS_MATRIZ),
            "controles": controles, "totales_por_marco": totales, "totales_por_sede": totales_sede}


# ── Cumplimiento continuo ────────────────────────────────────────────────────

def _medida(db: Session, org: str, medida: str, informe: dict) -> tuple[str, dict]:
    """(estado, lo medido) de una medida de `catalogo.MEDIDAS` (quien llama la aísla en un punto de guardado)."""
    por_id = {c["id"]: c for c in informe.get("controls", [])}

    def del_informe(*ids):
        cs = [por_id[i] for i in ids if i in por_id]
        if not cs:
            return "not_measurable", {}
        if any(c["status"] == "attention" for c in cs):
            return "attention", {c["id"]: c["measured"] for c in cs}
        if all(c["status"] == "not_measurable" for c in cs):
            return "not_measurable", {c["id"]: c["measured"] for c in cs}
        return "pass", {c["id"]: c["measured"] for c in cs}

    if medida == "mfa_cobertura":
        return del_informe("mfa_required", "mfa_coverage")
    if medida == "politica_contrasenas":
        return del_informe("password_policy")
    if medida == "registro_auditoria_inmutable":
        return del_informe("audit_chain")
    if medida == "sod_conflictos":
        return del_informe("sod_open")
    if medida == "copias_seguridad":
        return del_informe("backups")
    if medida == "retencion_datos":
        c = por_id.get("retention")
        if not c:
            return "not_measurable", {}
            activas = (c.get("measured") or {}).get("active_policies") or 0
            return ("pass" if activas else "attention"), c.get("measured") or {}
        desde = ahora() - timedelta(days=365)
        if medida == "recertificacion_accesos":
            from app.models.seguridad_de_cuentas import AccessReviewCampaign as C
            cerradas = db.query(C).filter(C.organization_id == org, C.status == "closed", C.closed_at >= desde).count()
            vencidas = db.query(C).filter(C.organization_id == org, C.status == "open", C.due_at < ahora()).count()
            return ("pass" if cerradas and not vencidas else "attention"), {"cerradas_12_meses": cerradas,
                                                                             "abiertas_vencidas": vencidas}
        if medida == "revision_proveedores":
            from app.models.proveedores import SupplierRiskAssessment as R
            n = db.query(R).filter(R.organization_id == org, R.assessed_at >= desde.date()).count()
            vencidas = db.query(R).filter(R.organization_id == org, R.next_review_date < hoy()).count()
            return ("pass" if n and not vencidas else "attention"), {"evaluaciones_12_meses": n,
                                                                      "revisiones_vencidas": vencidas}
        if medida == "inventario_activos_cmdb":
            from app.models.service_desk.cmdb import ConfigurationItem as CI
            n = db.query(CI).filter(CI.organization_id == org).count()
            return ("pass" if n else "attention"), {"elementos": n}
        if medida == "gestion_vulnerabilidades":
            from app.models.cmdb_software import VulnerabilityFinding as V
            criticas = db.query(V).filter(V.organization_id == org, V.status == "open",
                                          V.severity.in_(("critical", "high"))).count()
            return ("pass" if criticas == 0 else "attention"), {"criticas_o_altas_abiertas": criticas}
        if medida == "gestion_cambios_cab":
            from app.models.service_desk.changes import ITSMChangeRequest as Ch
            n = db.query(Ch).filter(Ch.organization_id == org, Ch.created_at >= desde).count()
            sin_aprobar = db.query(Ch).filter(Ch.organization_id == org, Ch.created_at >= desde,
                                              Ch.status.in_(("implemented", "closed_success")),
                                              Ch.approved_at.is_(None)).count()
            return ("pass" if n and not sin_aprobar else ("attention" if sin_aprobar else "info")), {
                "cambios_12_meses": n, "implantados_sin_aprobacion": sin_aprobar}
        if medida == "gestion_incidentes":
            from app.models.service_desk.tickets import Ticket
            n = db.query(Ticket).filter(Ticket.organization_id == org, Ticket.created_at >= desde).count()
            resueltos = db.query(Ticket).filter(Ticket.organization_id == org, Ticket.resolved_at >= desde).count()
            return ("pass" if n and resueltos else "info"), {"tickets_12_meses": n, "resueltos": resueltos}
    return "not_measurable", {}


def medir(db: Session, usuario, programa_id: str) -> dict:
    """Mide los controles medibles, aporta su evidencia del sistema (una por control y día) y la de las tareas hechas."""
    from app.services.informe_de_cumplimiento import generar
    from app.models.task import Task
    p = propio(db, CertPrograma, programa_id, usuario, "programa_de_certificacion")
    org = p.organization_id
    catalogo.importar_evidencias_grc(db, org)
    informe = generar(db, org)
    filas = db.query(CertAplicabilidad).filter(CertAplicabilidad.programa_id == p.id).all()
    controles = {c.id: c for c in db.query(CertControl).filter(CertControl.organization_id == org)}
    medidas: dict[str, tuple] = {}
    medidas_hechas = evidencias_sistema = evidencias_tarea = 0
    momento = ahora()
    for f in filas:
        c = controles.get(f.control_id)
        if c is None or not c.medible_por_plataforma:
            continue
        if c.medible_por_plataforma not in medidas:
            try:
                with db.begin_nested():
                    medidas[c.medible_por_plataforma] = _medida(db, org, c.medible_por_plataforma, informe)
            except Exception:
                logger.warning("certificaciones: no se pudo medir %s", c.medible_por_plataforma, exc_info=True)
                medidas[c.medible_por_plataforma] = ("not_measurable", {"error": "no_medible"})
        estado, medido = medidas[c.medible_por_plataforma]
        f.medicion, f.medicion_en, f.medicion_detalle = estado, momento, dump(medido)
        medidas_hechas += 1
        hoy_ = hoy()
        ya = db.query(CertEvidencia.id).filter(CertEvidencia.organization_id == org,
                                              CertEvidencia.control_id == c.id, CertEvidencia.origen == "sistema",
                                              CertEvidencia.valida_desde == hoy_).first()
        if ya is None and estado in ("pass", "attention", "info"):
            contenido = {"medida": c.medible_por_plataforma, "estado": estado, "medido": medido,
                         "informe_generado": str(informe.get("generated_at")), "cadena": informe.get("audit_chain_head")}
            texto = json.dumps(contenido, sort_keys=True, ensure_ascii=False, default=str)
            db.add(CertEvidencia(organization_id=org, control_id=c.id, titulo=f"Medida automática: {c.medible_por_plataforma}",
                                 tipo="informe_sistema", origen="sistema", contenido=texto,
                                 sha256=hashlib.sha256(texto.encode()).hexdigest(), valida_desde=hoy_,
                                 caduca_el=hoy_ + timedelta(days=31) if estado == "pass" else hoy_,
                                 creado_por=None))
            evidencias_sistema += 1
    for enlace in db.query(CertControlTarea).filter(CertControlTarea.organization_id == org).all():
        f = db.get(CertAplicabilidad, enlace.aplicabilidad_id)
        if f is None or f.programa_id != p.id:
            continue
        t = db.get(Task, enlace.task_id)
        if t is None or getattr(t.status, "value", t.status) != "done":
            continue
        ya = db.query(CertEvidencia.id).filter(CertEvidencia.aplicabilidad_id == f.id,
                                              CertEvidencia.task_id == t.id).first()
        if ya is None:
            db.add(CertEvidencia(organization_id=org, programa_id=p.id, aplicabilidad_id=f.id, control_id=f.control_id,
                                 titulo=f"Tarea cerrada: {t.code or ''} {t.title}"[:300], tipo="tarea", origen="tarea",
                                 task_id=t.id, valida_desde=hoy(), creado_por=None))
            evidencias_tarea += 1
    auditar(db, usuario, "MEASURE", "programa", p.id, p.codigo,
            meta={"medidas": medidas_hechas, "evidencias_sistema": evidencias_sistema,
                  "evidencias_tarea": evidencias_tarea})
    db.commit()
    return {"medidas": medidas_hechas, "evidencias_sistema": evidencias_sistema,
            "evidencias_tarea": evidencias_tarea,
            "resultado": {k: v[0] for k, v in medidas.items()}}
