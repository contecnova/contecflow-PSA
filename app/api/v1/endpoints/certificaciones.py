"""Certificaciones y cumplimiento continuo (migración 212, docs/CERTIFICACIONES.md).

La lógica está en `app/services/certificaciones/`. Capacidades:
`certificaciones.ver` (leer), `certificaciones.gestionar` (programas,
declaración, evidencias, CAPA, certificados, proveedores críticos, NIS2),
`certificaciones.auditar` (pruebas, eficacia, auditorías, hallazgos, accesos de
auditores, paquete; con segregación de funciones en el servicio) y
`certificaciones.administrar` (configuración, biblioteca, texto oficial,
borrados y RGPD de auditores).

Rutas anónimas: `GET /certificaciones/auditor/{token}` y `.../paquete` (acceso
temporal de solo lectura del auditor; credencial = token, guardado solo como
huella; la sesión declara su contexto y publica la empresa al resolverlo; cada
consulta queda registrada). Ver docs/seguridad/rutas_anonimas.md.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_db, requiere_capacidad
from app.core.responses import APIResponse
from app.db.session import sesion_de_sistema
from app.models.user import User
from app.services.certificaciones import (
    auditorias, catalogo, certificados, comun, evidencias, externos, generacion, nis2, panel, programas,
    proveedores, rgpd,
)
from app.services.certificaciones.traduccion import RutaTraducida, idioma_de_peticion

# 24-11-2026 (barrido de traducciones): las respuestas salen con el contenido de la
# biblioteca en el idioma de la interfaz (`X-Idioma`); ver services/certificaciones/traduccion.py.
router = APIRouter(route_class=RutaTraducida)

VER = "certificaciones.ver"
GESTIONAR = "certificaciones.gestionar"
AUDITAR = "certificaciones.auditar"
ADMINISTRAR = "certificaciones.administrar"


def _ok(data):
    return APIResponse.ok(data=data)


# ── Esquemas ─────────────────────────────────────────────────────────────────

class ObjetivoIn(BaseModel):
    marco: str = Field(max_length=60)
    nivel: Optional[str] = Field(None, max_length=30)
    niveles: Optional[list[str]] = None
    sl_objetivo: Optional[str] = Field(None, max_length=10)


class ProgramaIn(BaseModel):
    nombre: Optional[str] = Field(None, max_length=300)
    descripcion: Optional[str] = Field(None, max_length=20000)
    estado: Optional[str] = Field(None, max_length=15)
    alcance: Optional[dict[str, Any]] = None
    objetivos: Optional[list[ObjetivoIn]] = None
    responsable_id: Optional[str] = Field(None, max_length=36)
    patrocinador_id: Optional[str] = Field(None, max_length=36)
    fecha_inicio: Optional[date] = None
    fecha_objetivo: Optional[date] = None


class DesdePlantillaIn(BaseModel):
    plantilla: str = Field(min_length=1, max_length=80)
    nombre: Optional[str] = Field(None, max_length=300)
    parametros: Optional[dict[str, Any]] = None
    alcance: Optional[dict[str, Any]] = None
    empresa: Optional[str] = Field(None, max_length=200)
    responsable_id: Optional[str] = Field(None, max_length=36)
    patrocinador_id: Optional[str] = Field(None, max_length=36)
    fecha_inicio: Optional[date] = None
    fecha_objetivo: Optional[date] = None


class FilaIn(BaseModel):
    aplica: Optional[bool] = None
    justificacion: Optional[str] = Field(None, max_length=8000)
    estado: Optional[str] = Field(None, max_length=15)
    responsable_id: Optional[str] = Field(None, max_length=36)


class EficaciaIn(BaseModel):
    eficacia: str = Field(max_length=15)
    comentario: Optional[str] = Field(None, max_length=4000)


class SedeIn(BaseModel):
    sede: str = Field(min_length=1, max_length=120)


class TareaIn(BaseModel):
    task_id: str = Field(min_length=1, max_length=36)


class PruebaIn(BaseModel):
    tipo: str = Field(max_length=20)
    periodo_desde: Optional[date] = None
    periodo_hasta: Optional[date] = None
    poblacion: Optional[int] = Field(None, ge=0)
    muestra: Optional[int] = Field(None, ge=0)
    metodo: Optional[str] = Field(None, max_length=8000)
    resultado: Optional[str] = Field(None, max_length=20)
    excepciones: Optional[str] = Field(None, max_length=8000)
    notas: Optional[str] = Field(None, max_length=8000)


class EvidenciaIn(BaseModel):
    aplicabilidad_id: Optional[str] = Field(None, max_length=36)
    control_id: Optional[str] = Field(None, max_length=36)
    programa_id: Optional[str] = Field(None, max_length=36)
    titulo: str = Field(min_length=1, max_length=300)
    tipo: Optional[str] = Field(None, max_length=20)
    document_id: Optional[str] = Field(None, max_length=36)
    task_id: Optional[str] = Field(None, max_length=36)
    uri: Optional[str] = Field(None, max_length=1000)
    sha256: Optional[str] = Field(None, max_length=64)
    valida_desde: Optional[date] = None
    caduca_el: Optional[date] = None


class ControlIn(BaseModel):
    titulo: Optional[str] = Field(None, max_length=300)
    descripcion: Optional[str] = Field(None, max_length=20000)
    dominio: Optional[str] = Field(None, max_length=80)
    evidencia_sugerida: Optional[list[str]] = None
    activo: Optional[bool] = None


class TextoOficialIn(BaseModel):
    filas: list[dict[str, Any]] = Field(default_factory=list, max_length=5000)
    licencia: Optional[dict[str, Any]] = None


class AuditoriaIn(BaseModel):
    programa_id: Optional[str] = Field(None, max_length=36)
    tipo: Optional[str] = Field(None, max_length=25)
    marco: Optional[str] = Field(None, max_length=60)
    estado: Optional[str] = Field(None, max_length=15)
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    entidad_id: Optional[str] = Field(None, max_length=36)
    auditor_id: Optional[str] = Field(None, max_length=36)
    responsable_id: Optional[str] = Field(None, max_length=36)
    plan: Optional[str] = Field(None, max_length=20000)
    agenda: Optional[list[dict[str, Any]]] = None
    muestras: Optional[list[dict[str, Any]]] = None
    resultado: Optional[str] = Field(None, max_length=20000)
    conclusion: Optional[str] = Field(None, max_length=20)


class HallazgoIn(BaseModel):
    tipo: Optional[str] = Field(None, max_length=15)
    control_id: Optional[str] = Field(None, max_length=36)
    titulo: Optional[str] = Field(None, max_length=300)
    descripcion: Optional[str] = Field(None, max_length=20000)
    fecha_limite: Optional[date] = None
    estado: Optional[str] = Field(None, max_length=15)


class AccionIn(BaseModel):
    analisis_causa: Optional[str] = Field(None, max_length=20000)
    plan: Optional[str] = Field(None, max_length=20000)
    responsable_id: Optional[str] = Field(None, max_length=36)
    fecha_limite: Optional[date] = None
    estado: Optional[str] = Field(None, max_length=15)


class VerificarIn(BaseModel):
    eficaz: bool
    verificacion: Optional[str] = Field(None, max_length=8000)


class ComentarioIn(BaseModel):
    comentario: Optional[str] = Field(None, max_length=4000)


class EntidadIn(BaseModel):
    nombre: Optional[str] = Field(None, max_length=200)
    tipo: Optional[str] = Field(None, max_length=30)
    acreditaciones: Optional[list[str]] = None
    subcontractor_id: Optional[str] = Field(None, max_length=36)
    contacto_email: Optional[str] = Field(None, max_length=255)
    web: Optional[str] = Field(None, max_length=300)
    notas: Optional[str] = Field(None, max_length=8000)
    activo: Optional[bool] = None


class AuditorIn(BaseModel):
    nombre: Optional[str] = Field(None, max_length=200)
    entidad_id: Optional[str] = Field(None, max_length=36)
    email: Optional[str] = Field(None, max_length=255)
    cualificaciones: Optional[list[str]] = None
    independencia_declarada: Optional[bool] = None
    conflictos_interes: Optional[str] = Field(None, max_length=8000)
    nda_firmado_el: Optional[date] = None
    nda_document_id: Optional[str] = Field(None, max_length=36)
    desde: Optional[date] = None
    hasta: Optional[date] = None
    activo: Optional[bool] = None


class AccesoIn(BaseModel):
    auditor_id: str = Field(min_length=1, max_length=36)
    programa_id: str = Field(min_length=1, max_length=36)
    dias: Optional[int] = Field(None, ge=1, le=365)


class CertificadoIn(BaseModel):
    numero: Optional[str] = Field(None, max_length=120)
    marco: Optional[str] = Field(None, max_length=60)
    programa_id: Optional[str] = Field(None, max_length=36)
    entidad_id: Optional[str] = Field(None, max_length=36)
    alcance: Optional[str] = Field(None, max_length=8000)
    nivel: Optional[str] = Field(None, max_length=30)
    emitido_el: Optional[date] = None
    valido_hasta: Optional[date] = None
    estado: Optional[str] = Field(None, max_length=15)
    enx_id: Optional[str] = Field(None, max_length=60)
    enx_ambito: Optional[str] = Field(None, max_length=200)
    proxima_auditoria: Optional[date] = None
    tipo_proxima: Optional[str] = Field(None, max_length=20)
    document_id: Optional[str] = Field(None, max_length=36)


class IncidenteIn(BaseModel):
    ticket: Optional[str] = Field(None, max_length=60)
    programa_id: Optional[str] = Field(None, max_length=36)
    titulo: Optional[str] = Field(None, max_length=300)
    descripcion: Optional[str] = Field(None, max_length=20000)
    detectado_en: Optional[str] = Field(None, max_length=40)
    significativo: Optional[bool] = None
    transfronterizo: Optional[bool] = None
    impacto: Optional[str] = Field(None, max_length=8000)
    autoridad: Optional[str] = Field(None, max_length=200)
    responsable_id: Optional[str] = Field(None, max_length=36)
    estado: Optional[str] = Field(None, max_length=20)


class ComunicacionIn(BaseModel):
    tipo: str = Field(max_length=25)
    destinatario: Optional[str] = Field(None, max_length=200)
    asunto: Optional[str] = Field(None, max_length=300)
    contenido: Optional[str] = Field(None, max_length=50000)
    referencia: Optional[str] = Field(None, max_length=120)
    enviado_en: Optional[str] = Field(None, max_length=40)


class ProveedorIn(BaseModel):
    nombre: Optional[str] = Field(None, max_length=200)
    subcontractor_id: Optional[str] = Field(None, max_length=36)
    programa_id: Optional[str] = Field(None, max_length=36)
    criticidad: Optional[str] = Field(None, max_length=10)
    servicios: Optional[str] = Field(None, max_length=8000)
    resultado: Optional[str] = Field(None, max_length=20)
    riesgo: Optional[str] = Field(None, max_length=8000)
    proxima_evaluacion: Optional[date] = None
    notas: Optional[str] = Field(None, max_length=8000)


class ConfigIn(BaseModel):
    aviso_certificado_dias: Optional[int] = Field(None, ge=1, le=3650)
    aviso_auditoria_dias: Optional[int] = Field(None, ge=1, le=3650)
    caducidad_evidencia_dias: Optional[int] = Field(None, ge=1, le=3650)
    aviso_evidencia_dias: Optional[int] = Field(None, ge=1, le=3650)
    exigir_evidencia_aprobada: Optional[bool] = None
    acceso_auditor_max_dias: Optional[int] = Field(None, ge=1, le=365)
    autoridad_nis2: Optional[str] = Field(None, max_length=200)
    nis2_alerta_horas: Optional[int] = Field(None, ge=1, le=720)
    nis2_notificacion_horas: Optional[int] = Field(None, ge=1, le=720)
    nis2_informe_final_dias: Optional[int] = Field(None, ge=1, le=365)
    proyecto_capa_id: Optional[str] = Field(None, max_length=36)


def _d(m: BaseModel) -> dict:
    return m.model_dump(exclude_unset=True)


# ── Panel, configuración y biblioteca ────────────────────────────────────────

@router.get("/panel", summary="Panel: avance por norma, carencias, hallazgos, CAPA vencidas, certificados y NIS2")
def ver_panel(programa_id: Optional[str] = Query(None, max_length=36), db: Session = Depends(get_db),
              current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(panel.panel(db, current_user, programa_id))


@router.get("/config", summary="Configuración de Certificaciones de la empresa")
def ver_config(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.administrar"))):
    return _ok(comun.config_dict(comun.config(db, comun.org_de(current_user))))


@router.put("/config", summary="Guardar la configuración de Certificaciones")
def guardar_config(payload: ConfigIn, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("certificaciones.administrar"))):
    return _ok(comun.guardar_config(db, current_user, _d(payload)))


@router.get("/catalogo/marcos", summary="Marcos de la biblioteca (siembra la primera vez)")
def ver_marcos(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(catalogo.marcos(db, current_user))


@router.get("/catalogo/controles", summary="Biblioteca única de controles con sus correspondencias")
def ver_controles(marco: Optional[str] = Query(None, max_length=60), dominio: Optional[str] = Query(None, max_length=80),
                  q: Optional[str] = Query(None, max_length=200), afectados: bool = False,
                  db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(catalogo.controles(db, current_user, marco=marco, dominio=dominio, q=q, afectados=afectados))


@router.patch("/catalogo/controles/{control_id}", summary="Editar un control (deja de ponerse al día con la semilla)")
def editar_control(control_id: str, payload: ControlIn, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("certificaciones.administrar"))):
    return _ok(catalogo.editar_control(db, current_user, control_id, _d(payload)))


@router.post("/catalogo/correspondencias/{correspondencia_id}/revisada",
             summary="Marcar revisada una correspondencia afectada por un cambio de versión")
def revisar_correspondencia(correspondencia_id: str, db: Session = Depends(get_db),
                            current_user: User = Depends(requiere_capacidad("certificaciones.administrar"))):
    return _ok(catalogo.revisar_version(db, current_user, correspondencia_id))


@router.post("/catalogo/sembrar", summary="Sembrar o poner al día la biblioteca de la empresa")
def sembrar(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.administrar"))):
    informe = catalogo.sembrar(db, comun.org_de(current_user), usuario=current_user)
    db.commit()
    return _ok(informe)


@router.get("/catalogo/validacion", summary="Validación del contenido (errores y avisos)")
def validacion(current_user: User = Depends(requiere_capacidad("certificaciones.administrar"))):
    return _ok(catalogo.resumen_de_validacion())


@router.post("/catalogo/texto-oficial", summary="Importar el texto oficial con licencia (y corregir ids)")
def importar_texto(payload: TextoOficialIn, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("certificaciones.administrar"))):
    return _ok(catalogo.importar_texto_oficial(db, current_user, payload.filas, payload.licencia))


@router.get("/plantillas", summary="Plantillas de programa con sus parámetros de alcance")
def ver_plantillas(current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(catalogo.plantillas())


# ── Programas, aplicabilidad y matriz ────────────────────────────────────────

@router.get("/programas", summary="Programas de certificación de la empresa")
def listar_programas(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(programas.listar(db, current_user))


@router.post("/programas", summary="Crear un programa (con su declaración de aplicabilidad)", status_code=201)
def crear_programa(payload: ProgramaIn, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    datos = _d(payload)
    if payload.objetivos is not None:
        datos["objetivos"] = [o.model_dump() for o in payload.objetivos]
    p = programas.crear(db, current_user, datos)
    return _ok(programas.serializar(db, p, detalle=True))


@router.post("/programas/desde-plantilla", summary="Generar programa, proyecto, declaración y documentos (§4)",
             status_code=201)
def desde_plantilla(payload: DesdePlantillaIn, request: Request, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(generacion.generar(db, current_user, _d(payload), idioma=idioma_de_peticion(request)))


@router.get("/programas/{programa_id}", summary="Un programa")
def ver_programa(programa_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    from app.models.certificaciones import CertPrograma
    return _ok(programas.serializar(db, comun.propio(db, CertPrograma, programa_id, current_user,
                                                     "programa_de_certificacion"), detalle=True))


@router.patch("/programas/{programa_id}", summary="Editar alcance, objetivos, gobierno y estado")
def editar_programa(programa_id: str, payload: ProgramaIn, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    datos = _d(payload)
    if payload.objetivos is not None:
        datos["objetivos"] = [o.model_dump() for o in payload.objetivos]
    return _ok(programas.editar(db, current_user, programa_id, datos))


@router.delete("/programas/{programa_id}", summary="Borrar un programa (bloqueo legal y auditoría)")
def borrar_programa(programa_id: str, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("certificaciones.administrar"))):
    programas.borrar(db, current_user, programa_id)
    return _ok({"ok": True})


@router.get("/programas/{programa_id}/aplicabilidad", summary="Declaración de aplicabilidad")
def ver_aplicabilidad(programa_id: str, marco: Optional[str] = Query(None, max_length=60),
                      sede: Optional[str] = Query(None, max_length=120), estado: Optional[str] = Query(None, max_length=15),
                      q: Optional[str] = Query(None, max_length=200), db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(programas.aplicabilidad(db, current_user, programa_id, marco=marco, sede=sede, estado=estado, q=q))


@router.get("/programas/{programa_id}/matriz", summary="Matriz control × marco × sede × estado")
def ver_matriz(programa_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(programas.matriz(db, current_user, programa_id))


@router.post("/programas/{programa_id}/medir", summary="Cumplimiento continuo: medir y aportar evidencia automática")
def medir(programa_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(programas.medir(db, current_user, programa_id))


@router.patch("/aplicabilidad/{fila_id}", summary="Aplica/justificación, estado de implantación y responsable")
def editar_fila(fila_id: str, payload: FilaIn, db: Session = Depends(get_db),
                current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(programas.editar_fila(db, current_user, fila_id, _d(payload)))


@router.post("/aplicabilidad/{fila_id}/eficacia", summary="Evaluar la eficacia (quien implantó no evalúa)")
def eficacia(fila_id: str, payload: EficaciaIn, db: Session = Depends(get_db),
             current_user: User = Depends(requiere_capacidad("certificaciones.auditar"))):
    return _ok(programas.evaluar_eficacia(db, current_user, fila_id, payload.eficacia, payload.comentario))


@router.post("/aplicabilidad/{fila_id}/sedes", summary="Fila propia de una sede", status_code=201)
def dividir(fila_id: str, payload: SedeIn, db: Session = Depends(get_db),
            current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(programas.dividir_por_sede(db, current_user, fila_id, payload.sede))


@router.get("/aplicabilidad/{fila_id}/tareas", summary="Tareas que implantan el control")
def tareas(fila_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(programas.tareas_de_fila(db, current_user, fila_id))


@router.post("/aplicabilidad/{fila_id}/tareas", summary="Enlazar una tarea al control")
def enlazar(fila_id: str, payload: TareaIn, db: Session = Depends(get_db),
            current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(programas.enlazar_tarea(db, current_user, fila_id, payload.task_id))


@router.get("/aplicabilidad/{fila_id}/pruebas", summary="Pruebas de diseño y de eficacia operativa")
def ver_pruebas(fila_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(programas.pruebas(db, current_user, fila_id))


@router.post("/aplicabilidad/{fila_id}/pruebas", summary="Registrar una prueba (quien prueba no implanta)",
             status_code=201)
def registrar_prueba(fila_id: str, payload: PruebaIn, db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("certificaciones.auditar"))):
    return _ok(programas.registrar_prueba(db, current_user, fila_id, _d(payload)))


@router.get("/aplicabilidad/{fila_id}/evidencias", summary="Evidencias que cuentan para la fila")
def evidencias_de_fila(fila_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    from app.models.certificaciones import CertAplicabilidad
    f = comun.propio(db, CertAplicabilidad, fila_id, current_user, "fila_de_aplicabilidad")
    cfg = comun.config(db, f.organization_id)
    return _ok([evidencias.serializar(db, e, cfg) for e in evidencias.de_la_fila(db, f)])


# ── Evidencias ───────────────────────────────────────────────────────────────

@router.get("/evidencias", summary="Evidencias (filtro por programa, control y estado)")
def listar_evidencias(programa_id: Optional[str] = Query(None, max_length=36),
                      control_id: Optional[str] = Query(None, max_length=36),
                      estado: Optional[str] = Query(None, max_length=25), db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(evidencias.listar(db, current_user, programa_id=programa_id, control_id=control_id,
                                 estado_filtro=estado))


@router.post("/evidencias", summary="Registrar una evidencia (apoyada en Documentos)", status_code=201)
def crear_evidencia(payload: EvidenciaIn, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    ev = evidencias.crear(db, current_user, _d(payload))
    return _ok(evidencias.serializar(db, ev, comun.config(db, ev.organization_id)))


@router.delete("/evidencias/{evidencia_id}", summary="Borrar una evidencia (bloqueo legal y auditoría)")
def borrar_evidencia(evidencia_id: str, db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("certificaciones.administrar"))):
    evidencias.borrar(db, current_user, evidencia_id)
    return _ok({"ok": True})


# ── Auditorías, hallazgos y CAPA ─────────────────────────────────────────────

@router.get("/auditorias", summary="Auditorías")
def listar_auditorias(programa_id: Optional[str] = Query(None, max_length=36), db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(auditorias.listar(db, current_user, programa_id))


@router.post("/auditorias", summary="Planificar una auditoría", status_code=201)
def crear_auditoria(payload: AuditoriaIn, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("certificaciones.auditar"))):
    return _ok(auditorias.crear(db, current_user, _d(payload)))


@router.get("/auditorias/{auditoria_id}", summary="Una auditoría con sus hallazgos")
def ver_auditoria(auditoria_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(auditorias.detalle(db, current_user, auditoria_id))


@router.patch("/auditorias/{auditoria_id}", summary="Plan, agenda, muestras, resultado y estado")
def editar_auditoria(auditoria_id: str, payload: AuditoriaIn, db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("certificaciones.auditar"))):
    return _ok(auditorias.editar(db, current_user, auditoria_id, _d(payload)))


@router.post("/auditorias/{auditoria_id}/hallazgos", summary="Registrar un hallazgo", status_code=201)
def crear_hallazgo(auditoria_id: str, payload: HallazgoIn, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("certificaciones.auditar"))):
    return _ok(auditorias.crear_hallazgo(db, current_user, auditoria_id, _d(payload)))


@router.get("/hallazgos", summary="Hallazgos con sus acciones")
def listar_hallazgos(programa_id: Optional[str] = Query(None, max_length=36), solo_abiertos: bool = False,
                     db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(auditorias.hallazgos(db, current_user, programa_id=programa_id, solo_abiertos=solo_abiertos))


@router.patch("/hallazgos/{hallazgo_id}", summary="Editar un hallazgo")
def editar_hallazgo(hallazgo_id: str, payload: HallazgoIn, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("certificaciones.auditar"))):
    return _ok(auditorias.editar_hallazgo(db, current_user, hallazgo_id, _d(payload)))


@router.post("/hallazgos/{hallazgo_id}/corregido", summary="Marcar el hallazgo como corregido")
def corregido(hallazgo_id: str, db: Session = Depends(get_db),
              current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(auditorias.marcar_corregido(db, current_user, hallazgo_id))


@router.post("/hallazgos/{hallazgo_id}/cerrar", summary="Cerrar el hallazgo (quien lo corrigió no lo cierra)")
def cerrar_hallazgo(hallazgo_id: str, payload: ComentarioIn = ComentarioIn(), db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("certificaciones.auditar"))):
    return _ok(auditorias.cerrar_hallazgo(db, current_user, hallazgo_id, payload.comentario))


@router.post("/hallazgos/{hallazgo_id}/acciones", summary="Acción correctiva (nace como tarea)", status_code=201)
def crear_accion(hallazgo_id: str, payload: AccionIn, db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(auditorias.crear_accion(db, current_user, hallazgo_id, _d(payload)))


@router.get("/acciones", summary="Acciones correctivas (CAPA)")
def listar_acciones(programa_id: Optional[str] = Query(None, max_length=36), solo_vencidas: bool = False,
                    db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(auditorias.acciones(db, current_user, programa_id=programa_id, solo_vencidas=solo_vencidas))


@router.patch("/acciones/{accion_id}", summary="Editar una acción correctiva")
def editar_accion(accion_id: str, payload: AccionIn, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(auditorias.editar_accion(db, current_user, accion_id, _d(payload)))


@router.post("/acciones/{accion_id}/hecha", summary="Marcar la acción como hecha")
def accion_hecha(accion_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(auditorias.marcar_hecha(db, current_user, accion_id))


@router.post("/acciones/{accion_id}/verificar", summary="Verificar la eficacia (quien la hizo no verifica)")
def verificar(accion_id: str, payload: VerificarIn, db: Session = Depends(get_db),
              current_user: User = Depends(requiere_capacidad("certificaciones.auditar"))):
    return _ok(auditorias.verificar(db, current_user, accion_id, payload.eficaz, payload.verificacion))


# ── Empresas colaboradoras, auditores y accesos ──────────────────────────────

@router.get("/entidades", summary="Empresas colaboradoras")
def listar_entidades(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(externos.entidades(db, current_user))


@router.post("/entidades", summary="Alta de empresa colaboradora", status_code=201)
def crear_entidad(payload: EntidadIn, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(externos.guardar_entidad(db, current_user, _d(payload)))


@router.patch("/entidades/{entidad_id}", summary="Editar empresa colaboradora")
def editar_entidad(entidad_id: str, payload: EntidadIn, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(externos.guardar_entidad(db, current_user, _d(payload), entidad_id))


@router.get("/auditores", summary="Auditores y consultores externos")
def listar_auditores(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(externos.auditores(db, current_user))


@router.post("/auditores", summary="Alta de auditor", status_code=201)
def crear_auditor(payload: AuditorIn, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(externos.guardar_auditor(db, current_user, _d(payload)))


@router.patch("/auditores/{auditor_id}", summary="Editar auditor")
def editar_auditor(auditor_id: str, payload: AuditorIn, db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(externos.guardar_auditor(db, current_user, _d(payload), auditor_id))


@router.get("/auditores/{auditor_id}/rgpd", summary="Copia RGPD de un auditor externo (art. 15/20)")
def rgpd_copia(auditor_id: str, db: Session = Depends(get_db),
               current_user: User = Depends(requiere_capacidad("certificaciones.administrar"))):
    return _ok(rgpd.copia_auditor(db, current_user, auditor_id))


@router.post("/auditores/{auditor_id}/suprimir", summary="Supresión RGPD de un auditor externo (art. 17)")
def rgpd_suprimir(auditor_id: str, db: Session = Depends(get_db),
                  current_user: User = Depends(requiere_capacidad("certificaciones.administrar"))):
    return _ok(rgpd.suprimir_auditor(db, current_user, auditor_id))


@router.get("/accesos", summary="Accesos temporales de auditores")
def listar_accesos(programa_id: Optional[str] = Query(None, max_length=36), db: Session = Depends(get_db),
                   current_user: User = Depends(requiere_capacidad("certificaciones.auditar"))):
    return _ok(externos.accesos(db, current_user, programa_id))


@router.post("/accesos", summary="Conceder acceso temporal de solo lectura (devuelve el enlace una vez)",
             status_code=201)
def conceder(payload: AccesoIn, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.auditar"))):
    return _ok(externos.conceder(db, current_user, _d(payload)))


@router.post("/accesos/{acceso_id}/revocar", summary="Revocar un acceso")
def revocar(acceso_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.auditar"))):
    return _ok(externos.revocar(db, current_user, acceso_id))


@router.get("/accesos/{acceso_id}/registro", summary="Todo lo que consultó el auditor con ese acceso")
def registro_de_acceso(acceso_id: str, db: Session = Depends(get_db),
                       current_user: User = Depends(requiere_capacidad("certificaciones.auditar"))):
    return _ok(externos.registro(db, current_user, acceso_id))


# ── Certificados, NIS2 y proveedores críticos ────────────────────────────────

@router.get("/certificados", summary="Certificados y etiquetas con sus vencimientos")
def listar_certificados(programa_id: Optional[str] = Query(None, max_length=36), db: Session = Depends(get_db),
                        current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(certificados.listar(db, current_user, programa_id))


@router.post("/certificados", summary="Alta de certificado o etiqueta", status_code=201)
def crear_certificado(payload: CertificadoIn, db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(certificados.guardar(db, current_user, _d(payload)))


@router.patch("/certificados/{certificado_id}", summary="Editar certificado")
def editar_certificado(certificado_id: str, payload: CertificadoIn, db: Session = Depends(get_db),
                       current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(certificados.guardar(db, current_user, _d(payload), certificado_id))


@router.get("/incidentes", summary="Incidentes NIS2 con sus relojes")
def listar_incidentes(solo_abiertos: bool = False, db: Session = Depends(get_db),
                      current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(nis2.listar(db, current_user, solo_abiertos))


@router.post("/incidentes", summary="Incidente notificable NIS2 (desde un ticket)", status_code=201)
def crear_incidente(payload: IncidenteIn, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(nis2.crear(db, current_user, _d(payload)))


@router.get("/incidentes/{incidente_id}", summary="Incidente NIS2 con comunicaciones y relojes")
def ver_incidente(incidente_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    from app.models.certificaciones import CertIncidente
    return _ok(nis2.serializar(db, comun.propio(db, CertIncidente, incidente_id, current_user, "incidente_nis2"), True))


@router.patch("/incidentes/{incidente_id}", summary="Editar incidente NIS2")
def editar_incidente(incidente_id: str, payload: IncidenteIn, db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(nis2.editar(db, current_user, incidente_id, _d(payload)))


@router.post("/incidentes/{incidente_id}/comunicaciones", summary="Registrar una comunicación a la autoridad",
             status_code=201)
def comunicar(incidente_id: str, payload: ComunicacionIn, db: Session = Depends(get_db),
              current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(nis2.comunicar(db, current_user, incidente_id, _d(payload)))


@router.get("/incidentes/{incidente_id}/plantilla/{tipo}", summary="Plantilla de notificación a la autoridad")
def plantilla_nis2(incidente_id: str, tipo: str, idioma: Optional[str] = Query(None, max_length=10),
                   db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(nis2.plantilla(db, current_user, incidente_id, tipo, idioma or getattr(current_user, "language", None)))


@router.get("/proveedores", summary="Proveedores críticos de la cadena de suministro")
def listar_proveedores(programa_id: Optional[str] = Query(None, max_length=36), db: Session = Depends(get_db),
                       current_user: User = Depends(requiere_capacidad("certificaciones.ver"))):
    return _ok(proveedores.listar(db, current_user, programa_id))


@router.post("/proveedores", summary="Evaluar un proveedor crítico", status_code=201)
def crear_proveedor(payload: ProveedorIn, db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(proveedores.guardar(db, current_user, _d(payload)))


@router.patch("/proveedores/{proveedor_id}", summary="Editar la evaluación de un proveedor crítico")
def editar_proveedor(proveedor_id: str, payload: ProveedorIn, db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("certificaciones.gestionar"))):
    return _ok(proveedores.guardar(db, current_user, _d(payload), proveedor_id))


# ── Paquete del auditor ──────────────────────────────────────────────────────

@router.post("/programas/{programa_id}/paquete", summary="Paquete del auditor firmado (Ed25519)")
def paquete(programa_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.auditar"))):
    return _ok(panel.generar_paquete(db, current_user, programa_id))


@router.get("/programas/{programa_id}/paquetes", summary="Paquetes generados (traza)")
def paquetes(programa_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("certificaciones.auditar"))):
    return _ok(panel.paquetes(db, current_user, programa_id))


# ── Acceso del auditor externo (anónimo con token) ───────────────────────────

def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/auditor/{token}", summary="Vista de solo lectura del auditor externo (acceso temporal)")
def vista_auditor(token: str, request: Request,
                  db: Session = Depends(sesion_de_sistema("certificaciones: acceso temporal del auditor"))):
    x = externos.resolver_token(db, token)
    datos = panel.vista_del_auditor(db, x)
    externos.apuntar(db, x, "vista", None, _ip(request))
    return _ok(datos)


@router.get("/auditor/{token}/paquete", summary="Paquete firmado para el auditor externo (acceso temporal)")
def paquete_auditor(token: str, request: Request,
                    db: Session = Depends(sesion_de_sistema("certificaciones: paquete del auditor"))):
    x = externos.resolver_token(db, token)
    doc = panel.generar_paquete(db, None, x.programa_id, acceso=x)
    externos.apuntar(db, x, "paquete", doc.get("package_sha256"), _ip(request))
    return _ok(doc)
