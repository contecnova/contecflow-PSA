"""Certificaciones: programa desde plantilla (§4 de la propuesta).

Al generar desde `app/data/certificaciones/plantillas/<clave>.yaml`:

1. Parámetros de alcance (número de sedes, OT, cotización, nivel TISAX, SL objetivo,
   entidad NIS2, prototipos, producto): se validan contra la plantilla y los que
   faltan toman `por_defecto`.
2. Objetivos del programa por marco con sus niveles: TISAX AL2/AL3 (+ prototipos),
   NIS2 si es entidad esencial o importante, SOX/J-SOX según dónde cotiza,
   IEC 62443 por partes (2-1 siempre; 3-2 y 3-3 con OT; 4-1 y 4-2 si desarrolla
   producto) y el SL objetivo como valor por defecto de cada zona.
3. Tareas: solo las que cumplen `aplica_si`; si una no aplica, sus sucesoras
   heredan sus dependencias (transitivamente).
4. Proyecto: se reutilizan las plantillas de proyecto (`plantillas_de_proyecto`):
   se crea una plantilla derivada (fases, tareas con su rol R, duración y RACI en
   la descripción, dependencias, riesgos y documentos), se instancia (el
   planificador pone las fechas con el calendario de la empresa) y se archiva
   (`is_active = False`: queda como traza de lo que se generó).
5. Programa + declaración de aplicabilidad + matriz, y cada tarea enlazada a sus
   controles: al cerrarse aporta su evidencia (`programas.medir`).
6. Documentos de la plantilla en **Documentos**, con aprobación obligatoria y
   enlazados como evidencia de sus controles (cuentan al aprobarse).
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.certificaciones import CertAplicabilidad, CertControl, CertControlTarea, CertEvidencia
from app.services.certificaciones import catalogo, expresiones
from app.services.certificaciones import programas as prog
from app.services.certificaciones.comun import auditar, config, fecha, hoy, org_de

_PROBABILIDAD = {"baja": "low", "media": "medium", "alta": "high"}
_IMPACTO = {"bajo": "minor", "medio": "moderate", "alto": "major", "critico": "critical"}


def parametros(plantilla: dict, dados: Optional[dict]) -> dict:
    """Valores de los parámetros: los dados, validados; los que faltan, `por_defecto`."""
    dados = dados or {}
    salida = {}
    for par in plantilla.get("parametros") or []:
        clave = par["clave"]
        valor = dados.get(clave, par.get("por_defecto"))
        try:
            salida[clave] = catalogo.normalizar_parametro(par, valor)
        except (ValueError, TypeError) as exc:
            raise error(422, "cert_parametro_no_valido", parametro=clave) from exc
    desconocidos = set(dados) - set(salida)
    if desconocidos:
        raise error(422, "cert_parametro_no_valido", parametro=sorted(desconocidos)[0])
    return salida


def objetivos(plantilla: dict, params: dict) -> list[dict]:
    """Objetivos por marco y niveles según los parámetros (docs/CERTIFICACIONES_CONTENIDO.md §2.1)."""
    salida = []
    cotiza = params.get("cotiza_en")
    for marco in plantilla.get("marcos") or []:
        o = {"marco": marco, "nivel": None, "niveles": None, "sl_objetivo": None}
        if marco == "tisax":
            nivel = params.get("nivel_tisax", "AL3")
            if nivel == "ninguno":
                continue
            niveles = ["AL2"] + (["AL3"] if nivel == "AL3" else [])
            if params.get("proteccion_prototipos", nivel == "AL3"):
                niveles.append("prototipos")
            o.update(nivel=nivel, niveles=niveles)
        elif marco == "nis2":
            entidad = params.get("entidad_nis2", "esencial")
            if entidad == "no":
                continue
            o["nivel"] = entidad
        elif marco == "sox":
            if cotiza is not None and cotiza not in ("eeuu", "ambos"):
                continue
        elif marco == "jsox":
            if cotiza is not None and cotiza not in ("japon", "ambos"):
                continue
        elif marco == "iec62443":
            niveles = ["2-1"]
            if params.get("tiene_ot", True):
                niveles += ["3-2", "3-3"]
            if params.get("desarrolla_producto", True):
                niveles += ["4-1", "4-2"]
            o.update(niveles=niveles, sl_objetivo=params.get("sl_objetivo"))
        salida.append(o)
    return salida


def tareas_que_aplican(plantilla: dict, params: dict) -> tuple[list[dict], dict[str, list[str]]]:
    """[(fase con sus tareas que aplican)], {tarea: dependencias heredadas}."""
    todas: dict[str, dict] = {}
    for f in plantilla.get("fases") or []:
        for t in f.get("tareas") or []:
            todas[t["clave"]] = t
    aplica = {k: expresiones.evaluar(t.get("aplica_si"), params) for k, t in todas.items()}
    memo: dict[str, list[str]] = {}

    def efectivas(clave: str, pila: tuple = ()) -> list[str]:
        """Las dependencias de `clave` sustituyendo las que no aplican por las suyas."""
        if clave in memo:
            return memo[clave]
        salida: list[str] = []
        for d in todas[clave].get("depende_de") or []:
            if d in pila or d not in todas:
                continue
            if aplica[d]:
                salida.append(d)
            else:
                salida.extend(efectivas(d, pila + (clave,)))
        memo[clave] = list(dict.fromkeys(salida))
        return memo[clave]

    fases = []
    for f in plantilla.get("fases") or []:
        ts = [t for t in f.get("tareas") or [] if aplica[t["clave"]]]
        if ts:
            fases.append({**f, "tareas": ts})
    deps = {k: efectivas(k) for k, v in aplica.items() if v}
    return fases, deps


def _descripcion(t: dict, controles: dict) -> str:
    raci = t.get("raci") or {}
    lineas = [f"R: {raci.get('R')} · A: {raci.get('A')}",
              f"C: {', '.join(raci.get('C') or []) or '—'} · I: {', '.join(raci.get('I') or []) or '—'}"]
    if t.get("controles"):
        lineas.append("Controles: " + ", ".join(t["controles"]))
    if t.get("entregables"):
        lineas.append("Entregables: " + "; ".join(t["entregables"]))
    return "\n".join(lineas)


def datos_de_proyecto(plantilla: dict, params: dict, nombre: str) -> dict:
    """El cuerpo de `plantillas_de_proyecto.crear` con solo lo que aplica."""
    fases, deps = tareas_que_aplican(plantilla, params)
    controles = catalogo.cargar()["controles"]
    phases = []
    for i, f in enumerate(fases):
        dias = max((t.get("dias") or 1) for t in f["tareas"])
        phases.append({"name": f["nombre"], "order": i, "estimated_weeks": max(1, math.ceil(dias / 5)),
                       "tasks": [{"key": t["clave"], "title": t["nombre"][:255],
                                  "description": _descripcion(t, controles),
                                  "role_name": (t.get("raci") or {}).get("R"),
                                  "duration_days": t.get("dias") or 1, "order": j}
                                 for j, t in enumerate(f["tareas"])]})
    dependencias = [{"predecessor": d, "successor": k, "dependency_type": "FS"} for k, ds in deps.items() for d in ds]
    riesgos = [{"title": r.get("titulo")[:255], "category": "cumplimiento",
                "probability": _PROBABILIDAD.get(r.get("probabilidad"), "medium"),
                "impact": _IMPACTO.get(r.get("impacto"), "moderate"), "mitigation_plan": r.get("mitigacion")}
               for r in plantilla.get("riesgos") or []]
    documentos = [{"name": d["nombre"][:255], "document_type": d.get("tipo"), "is_required": True,
                   "description": f"Plantilla {d['clave']}"} for d in plantilla.get("documentos") or []]
    return {"name": f"{nombre} · {plantilla['nombre']}"[:255], "description": plantilla["nombre"],
            "project_type": None, "phases": phases, "dependencies": dependencias, "risks": riesgos,
            "documents": documentos}


def _rellenar(texto: str, valores: dict) -> str:
    for k, v in valores.items():
        texto = texto.replace("{{" + k + "}}", str(v))
    return texto


def generar(db: Session, usuario, datos: dict) -> dict:
    """Programa, proyecto, declaración, enlaces tarea↔control y documentos desde una plantilla."""
    from app.models.advanced_config import ProjectTemplate
    from app.models.documents import ApprovalStatus, Document, DocumentCategory
    from app.models.project import ProjectPhase
    from app.models.task import Task
    from app.services import plantillas_de_proyecto

    org = org_de(usuario)
    catalogo.asegurar_sembrado(db, org)
    p = catalogo.plantilla(datos.get("plantilla") or "")
    params = parametros(p, datos.get("parametros"))
    nombre = (datos.get("nombre") or p["nombre"]).strip()[:300]
    inicio = fecha(datos.get("fecha_inicio"), "fecha_inicio") or hoy()

    # 1) Proyecto (reutiliza las plantillas de proyecto y el planificador; confirman ellas).
    cuerpo = datos_de_proyecto(p, params, nombre)
    derivada = plantillas_de_proyecto.crear(db, usuario, cuerpo)
    proyecto = plantillas_de_proyecto.instanciar(db, usuario, derivada.id, {
        "name": nombre, "start_date": inicio.isoformat(), "pm_id": datos.get("responsable_id") or usuario.id,
        "is_billable": False, "description": p["nombre"]})
    tpl = db.get(ProjectTemplate, derivada.id)
    if tpl is not None:
        tpl.is_active = False

    # 2) Programa y declaración de aplicabilidad.
    sedes = [f"Sede {i}" for i in range(1, min(int(params.get("num_sedes") or 1), 50) + 1)] \
        if int(params.get("num_sedes") or 1) > 1 else []
    zonas = [{"nombre": "OT", "sl_objetivo": params.get("sl_objetivo")}] if params.get("tiene_ot") else []
    programa = prog.crear(db, usuario, {
        "nombre": nombre, "descripcion": p["nombre"], "objetivos": objetivos(p, params),
        "alcance": {"sedes": sedes, "zonas": zonas, **(datos.get("alcance") or {})},
        "responsable_id": datos.get("responsable_id"), "patrocinador_id": datos.get("patrocinador_id"),
        "fecha_inicio": inicio, "fecha_objetivo": datos.get("fecha_objetivo"), "plantilla_clave": p["clave"],
        "parametros": params}, confirmar=False)
    programa.project_id = proyecto["project_id"]
    programa.estado = "en_curso"

    filas = {f.control_id: f for f in db.query(CertAplicabilidad).filter(
        CertAplicabilidad.programa_id == programa.id, CertAplicabilidad.sede == "").all()}
    por_clave = {c.clave_comun: c.id for c in db.query(CertControl).filter(CertControl.organization_id == org)}

    # 3) Tareas creadas ↔ controles (por fase y título, únicos en la plantilla validada).
    creadas = {}
    for t, fase in db.query(Task, ProjectPhase.name).join(ProjectPhase, ProjectPhase.id == Task.phase_id).filter(
            Task.project_id == proyecto["project_id"]).all():
        creadas[(fase, t.title)] = t.id
    fases, _deps = tareas_que_aplican(p, params)
    enlaces = 0
    for f in fases:
        for t in f["tareas"]:
            task_id = creadas.get((f["nombre"], t["nombre"][:255]))
            if not task_id:
                continue
            for c in t.get("controles") or []:
                fila = filas.get(por_clave.get(c))
                if fila is None:
                    continue
                db.add(CertControlTarea(organization_id=org, aplicabilidad_id=fila.id, task_id=task_id))
                enlaces += 1

    # 4) Documentos (políticas, procedimientos y registros) con aprobación obligatoria.
    textos = catalogo.cargar()["documentos"]
    cfg = config(db, org)
    valores = {"empresa": datos.get("empresa") or "", "alcance": nombre, "version": "0.1",
               "autoridad_nis2": cfg.autoridad_nis2 or "", "aprobador": "", "fecha_aprobacion": ""}
    categoria = {"politica": DocumentCategory.legal, "procedimiento": DocumentCategory.sop,
                 "registro": DocumentCategory.other}
    documentos = 0
    for d in p.get("documentos") or []:
        doc = Document(organization_id=org, title=d["nombre"][:255],
                       description=_rellenar(textos.get(d["clave"], ""), valores) or None,
                       category=categoria.get(d.get("tipo"), DocumentCategory.other),
                       project_id=proyecto["project_id"], requires_approval=True,
                       approval_status=ApprovalStatus.pending, created_by=usuario.id)
        db.add(doc)
        db.flush()
        documentos += 1
        for c in d.get("controles") or []:
            fila = filas.get(por_clave.get(c))
            if fila is None:
                continue
            db.add(CertEvidencia(organization_id=org, programa_id=programa.id, aplicabilidad_id=fila.id,
                                 control_id=fila.control_id, titulo=d["nombre"][:300], tipo="documento",
                                 origen="plantilla", document_id=doc.id, valida_desde=date.today(),
                                 creado_por=usuario.id))

    auditar(db, usuario, "GENERATE", "programa", programa.id, programa.codigo,
            despues={"plantilla": p["clave"], "parametros": params, "project_id": proyecto["project_id"],
                     "tareas": proyecto.get("tasks_created"), "enlaces": enlaces, "documentos": documentos,
                     "catalogo": catalogo.cargar().get("huella")})
    db.commit()
    return {"programa": prog.serializar(db, programa, detalle=True), "project_id": proyecto["project_id"],
            "project_code": proyecto.get("project_code"), "tareas": proyecto.get("tasks_created"),
            "dependencias": proyecto.get("dependencies_created"), "riesgos": proyecto.get("risks_created"),
            "enlaces_tarea_control": enlaces, "documentos": documentos, "parametros": params,
            "objetivos": objetivos(p, params)}
