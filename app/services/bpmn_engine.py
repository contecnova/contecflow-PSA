"""Motor de ejecucion de los procesos BPMN 2.0 guardados en /bpm.

Guia funcional y de administracion: `docs/BPM.md`. Historia: auditoria 2026-11
(el editor no ejecutaba nada), revision 16-11-2026 (decisiones manuales,
codigos traducibles), auditoria 22-11-2026 (las tareas de servicio ya no se
dan por hechas solas) y revision 23-11-2026 (migracion 204: todo lo de abajo
que no estaba).

El motor recorre el XML de la version **publicada** con fichas y guarda cada
elemento que atraviesa como un paso de la instancia (`bpmn_instance_steps`):
eso es tambien su historial. Una instancia se queda siempre en la version con
que arranco (salvo migracion explicita, `migrar`).

Elementos que ejecuta:

- **startEvent** (el de inicio sin definicion; los de mensaje o temporizador se
  aceptan como inicio manual con un aviso de validacion).
- **userTask, task, manualTask**: tarea humana en la bandeja. Asignacion por
  persona (`assignee`), candidatos (`candidateUsers`, `candidateGroups`: rol
  base, grupo de aprobacion o cola de agentes) o la calle (lane) del diagrama.
  Plazo de la tarea (`dueIn` ISO 8601 o `dueDate`): al vencer se escala
  (aviso y marca). Formulario (`formFields`): campos tipados que se validan al
  completar. `approval="true"`: la tarea es una aprobacion (segregacion).
- **serviceTask, sendTask, businessRuleTask, scriptTask**: con `action` (lista
  cerrada de `bpmn_acciones.ACCIONES`: ticket, cambio, demanda, aprobacion,
  politica, aviso, variables) se ejecutan solas en una cola con reintentos
  (`retries`) e incidente si se agotan; sin `action` esperan confirmacion
  humana (auditoria 22-11-2026). **Nunca se ejecuta codigo del diagrama**: un
  `scriptTask` sin accion es una tarea que confirma una persona.
- **receiveTask** e **intermediateCatchEvent** de mensaje: esperan el mensaje
  (`correlacionar`, por instancia o por clave de negocio).
- **intermediateCatchEvent** de temporizador (`timeDuration` o `timeDate`).
- **exclusiveGateway**: la primera condicion que se cumple, o la de por
  defecto; sin ninguna condicion, decision manual en la bandeja.
- **inclusiveGateway**: reparte por todas las salidas cuya condicion se cumple
  (o la de por defecto); sin condiciones, decision manual de una o varias
  salidas. Como union espera mientras quede alguna ficha que aun pueda llegar.
- **parallelGateway**: reparte por todas; como union espera una ficha por
  cada flujo de entrada.
- **subProcess** (incrustado): su inicio interno; termina cuando no le queda
  nada pendiente dentro.
- **callActivity** (`calledElement` = clave de otro proceso de la empresa):
  arranca una instancia hija con la version publicada y sigue cuando termina,
  con sus variables.
- **boundaryEvent**: temporizador (interrumpe o no), mensaje y error, sobre
  tareas, subprocesos y llamadas.
- **endEvent**: normal; de terminacion (corta su ambito); de error (lo captura
  el borde de error mas cercano; si nadie, la instancia falla).
- **intermediateThrowEvent** sin definicion: pasa.

Lo demas (compensacion, senales, escalados BPMN, condicionales, enlaces,
compuertas complejas o por eventos, subprocesos de evento, transacciones,
temporizadores ciclicos) hace que el diagrama no se pueda publicar: mejor no
arrancar que quedarse a medias. `validar()` devuelve los problemas (bloquean) y
los avisos (no bloquean) con un codigo por problema (`bpm.problema_<code>`).

Seguridad: el XML se parsea con `defusedxml` sin DTD (sin XXE ni expansion de
entidades); las condiciones son comparaciones simples (`var op valor`), no
codigo; las acciones automaticas son una lista cerrada.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional
from xml.etree.ElementTree import ParseError

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring as _fromstring
from sqlalchemy.orm import Session, contains_eager, selectinload

from app.core.codigos_de_error import ErrorConCodigo, error
from app.models.bpmn_process import (BPMNInstance, BPMNInstanceStep, BPMNProcess, BPMNProcessStatus,
                                     BPMNProcessVersion)

logger = logging.getLogger(__name__)

_NS = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
#: Espacio de nombres de las extensiones propias (`contecflow:assignee`…). Al
#: leer se aceptan esos nombres en cualquier espacio de nombres (tambien los de
#: Camunda al importar: `camunda:assignee`, `camunda:candidateGroups`…).
CONTECFLOW_NS = "http://contecflow.io/schema/bpmn/1.0"
_EXTENSIONES = {"assignee", "candidateGroups", "candidateUsers", "dueIn", "dueDate", "formFields", "action",
                "actionConfig", "retries", "approval", "resultVariable"}

HUMANOS = {"task", "userTask", "manualTask"}
AUTOMATICOS = {"serviceTask", "scriptTask", "sendTask", "businessRuleTask"}
ACTIVIDADES = HUMANOS | AUTOMATICOS | {"receiveTask", "subProcess", "callActivity"}
_SOPORTADOS = ACTIVIDADES | {"startEvent", "endEvent", "exclusiveGateway", "parallelGateway", "inclusiveGateway",
                             "intermediateCatchEvent", "intermediateThrowEvent", "boundaryEvent"}
_IGNORADOS = {"laneSet", "documentation", "extensionElements", "textAnnotation", "association", "dataObject",
              "dataObjectReference", "dataStoreReference", "group", "ioSpecification", "property",
              "dataInputAssociation", "dataOutputAssociation", "multiInstanceLoopCharacteristics_"}

#: Por que espera un paso (`BPMNInstanceStep.wait_kind`).
ESPERA_TAREA, ESPERA_DECISION, ESPERA_TEMPORIZADOR, ESPERA_UNION = "task", "decision", "timer", "join"
ESPERA_MENSAJE, ESPERA_SUBPROCESO, ESPERA_LLAMADA = "message", "subprocess", "call"
ESPERA_TRABAJO, ESPERA_REINTENTO, ESPERA_INCIDENTE, ESPERA_APROBACION = "job", "retry", "incident", "approval"
#: Los que completa una persona desde la bandeja.
ESPERAS_HUMANAS = {ESPERA_TAREA, ESPERA_DECISION}

#: Estados de una instancia (la API valida el filtro contra esta lista).
ESTADOS_DE_INSTANCIA = ("running", "suspended", "completed", "cancelled", "failed")
_TERMINADOS = ("completed", "cancelled", "failed")

#: Tipos de variable (`variables_schema` y `formFields`).
TIPOS_DE_VARIABLE = ("string", "text", "number", "integer", "boolean", "date", "enum", "user")

#: Profundidad maxima de llamadas entre procesos (callActivity dentro de callActivity…).
_MAX_PROFUNDIDAD = 10

# Nombre de calle (lane) → rol. Ademas del propio valor del rol (`UserRole`),
# los nombres con que se muestra en la interfaz en los tres idiomas. Solo los
# roles internos: son los que tienen bandeja.
_ALIAS_DE_ROL = {
    "admin": ("dirección", "direccion", "dirección / admin", "administrador", "administrator", "管理员"),
    "pm": ("project manager", "jefe de proyecto", "项目经理"),
    "team_lead": ("team lead", "responsable de equipo", "团队负责人"),
    "hr": ("rrhh", "recursos humanos", "human resources", "人力资源"),
    "employee": ("empleado", "员工"),
}

_NOMBRE_DE_VARIABLE = re.compile(r"^[A-Za-z_][\w.]{0,99}$")
_EXPRESION = re.compile(r"^\$\{\s*([A-Za-z_][\w.]*)\s*\}$")


def rol_de_calle(nombre: Optional[str]) -> Optional[str]:
    """El rol que exige una calle (o un candidato) por su nombre, o None si no es un rol."""
    from app.models.user import UserRole

    clave = (nombre or "").strip().lower()
    if clave.startswith("role:"):
        clave = clave[5:]
    if not clave:
        return None
    for rol in UserRole:
        if rol.value not in _ALIAS_DE_ROL:
            continue   # subcontractor: no entra en la bandeja (`require_internal_user`)
        if clave == rol.value or clave in _ALIAS_DE_ROL[rol.value]:
            return rol.value
    return None


# ── Grafo ────────────────────────────────────────────────────────────────────

@dataclass
class Nodo:
    id: str
    tipo: str
    nombre: Optional[str]
    entradas: list = field(default_factory=list)
    salidas: list = field(default_factory=list)
    defecto: Optional[str] = None
    rol: Optional[str] = None
    calle: Optional[str] = None              # nombre de la calle (rol o grupo)
    terminar: bool = False
    temporizador: Optional[tuple] = None     # ("duration"|"date", texto)
    definiciones: list = field(default_factory=list)
    decision: bool = False                   # compuerta sin condiciones: elige una persona
    padre: Optional[str] = None              # subproceso que lo contiene (None: el proceso)
    inicio_interno: Optional[str] = None     # subProcess: su startEvent
    adjunto: Optional[str] = None            # boundaryEvent: actividad a la que va pegado
    interrumpe: bool = True                  # boundaryEvent: cancelActivity
    bordes: list = field(default_factory=list)   # actividad: sus boundaryEvent
    mensaje: Optional[str] = None            # nombre del mensaje que espera
    error_code: Optional[str] = None         # endEvent/boundaryEvent de error (None en el borde: todos)
    llamado: Optional[str] = None            # callActivity: clave del proceso
    ext: dict = field(default_factory=dict)  # extensiones (assignee, formFields, action…)
    formulario: Optional[list] = None        # formFields ya leidos

    @property
    def accion(self) -> Optional[str]:
        return (self.ext.get("action") or "").strip() or None if self.tipo in AUTOMATICOS else None

    @property
    def es_aprobacion(self) -> bool:
        return str(self.ext.get("approval", "")).strip().lower() in ("true", "1", "yes", "si", "sí") \
            or self.accion == "approval"


@dataclass
class Flujo:
    id: str
    origen: str
    destino: str
    condicion: Optional[str]
    nombre: Optional[str] = None


@dataclass
class Problema:
    """Lo que impide ejecutar un diagrama (o, como aviso, lo que conviene revisar).

    `code` lo traduce la interfaz (`bpm.problema_<code>`, con `element` y
    `extra` como parametros); `texto` es la version legible en castellano que
    va en el 422 del arranque y en los logs.
    """
    code: str
    texto: str
    element: Optional[str] = None
    extra: Optional[str] = None

    def como_dict(self) -> dict:
        return {"code": self.code, "element": self.element, "extra": self.extra, "detail": self.texto}

    def __str__(self) -> str:
        return self.texto


@dataclass
class Grafo:
    nodos: dict
    flujos: dict
    inicio: Optional[str]
    problemas: list
    avisos: list = field(default_factory=list)
    _alcance: dict = field(default_factory=dict)

    def opciones(self, nodo_id: str) -> list[dict]:
        """Las salidas de una decision manual, con su etiqueta."""
        n = self.nodos.get(nodo_id)
        if n is None:
            return []
        out = []
        for fid in n.salidas:
            f = self.flujos[fid]
            destino = self.nodos.get(f.destino)
            out.append({"flow_id": fid, "name": f.nombre or (destino.nombre if destino else None) or f.destino,
                        "default": fid == n.defecto})
        return out

    def dentro(self, nodo_id: str, ambito: Optional[str]) -> bool:
        """¿Esta `nodo_id` dentro del subproceso `ambito` (a cualquier profundidad)? None: el proceso."""
        if ambito is None:
            return nodo_id in self.nodos
        n = self.nodos.get(nodo_id)
        while n is not None and n.padre is not None:
            if n.padre == ambito:
                return True
            n = self.nodos.get(n.padre)
        return False

    def sucesores(self, nodo_id: str) -> list[str]:
        n = self.nodos[nodo_id]
        out = [self.flujos[f].destino for f in n.salidas]
        out += n.bordes
        if n.tipo == "subProcess" and n.inicio_interno:
            out.append(n.inicio_interno)
        if n.tipo == "endEvent" and n.padre:
            out.append(n.padre)   # al cerrar el ambito, la ficha sale por el subproceso
        return out

    def alcanza(self, origen: str, destino: str) -> bool:
        """¿Puede una ficha en `origen` llegar a `destino`? (sin atravesar `destino`)."""
        clave = (origen, destino)
        if clave not in self._alcance:
            vistos, pila, hay = {origen}, [origen], False
            while pila and not hay:
                for s in self.sucesores(pila.pop()):
                    if s == destino:
                        hay = True
                        break
                    if s not in vistos and s in self.nodos:
                        vistos.add(s)
                        pila.append(s)
            self._alcance[clave] = hay
        return self._alcance[clave]

    def bordes_de(self, nodo_id: str, definicion: str) -> list:
        n = self.nodos.get(nodo_id)
        return [self.nodos[b] for b in (n.bordes if n else []) if definicion in self.nodos[b].definiciones]


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _etiqueta(n: Nodo) -> str:
    return n.nombre or n.id


def _xml_seguro(xml: str):
    """XML del usuario: sin DTD, sin entidades, sin referencias externas (XXE)."""
    return _fromstring(xml, forbid_dtd=True, forbid_entities=True, forbid_external=True)


def _extensiones(el) -> dict:
    """Atributos de extension (con espacio de nombres) que entiende el motor."""
    out = {}
    for k, v in el.attrib.items():
        if k.startswith("{") and _local(k) in _EXTENSIONES:
            out[_local(k)] = v
    return out


def leer_formulario(texto: Optional[str]) -> Optional[list]:
    """`formFields` (JSON) → lista de campos validos; None si no hay; ValueError si esta mal."""
    if not texto or not str(texto).strip():
        return None
    datos = json.loads(texto)
    if not isinstance(datos, list):
        raise ErrorConCodigo("bpm_formulario_no_lista", detail="formFields no es una lista")
    campos = []
    for c in datos:
        if not isinstance(c, dict) or not _NOMBRE_DE_VARIABLE.match(str(c.get("name", ""))):
            raise ErrorConCodigo("bpm_formulario_campo_sin_nombre", detail="campo sin nombre valido")
        tipo = c.get("type") or "string"
        if tipo not in TIPOS_DE_VARIABLE:
            raise ErrorConCodigo("bpm_formulario_tipo_no_valido", tipo=tipo, detail=f"tipo {tipo}")
        campos.append({"name": c["name"], "label": str(c.get("label") or c["name"])[:200], "type": tipo,
                       "required": bool(c.get("required")), "personal": bool(c.get("personal")),
                       "options": [str(o)[:200] for o in (c.get("options") or [])][:100]})
    return campos


def leer(xml: str) -> Grafo:
    """El grafo ejecutable del diagrama, lo que impide ejecutarlo y los avisos."""
    try:
        raiz = _xml_seguro(xml)
    except (ParseError, DefusedXmlException, ValueError, TypeError) as exc:
        # XML mal formado, los rechazos de defusedxml (DTD, entidades) y lo que no
        # es texto XML: el problema vuelve a la pantalla con su codigo.
        return Grafo({}, {}, None, [Problema("invalid_xml", f"XML no valido: {exc}", extra=str(exc)[:200])])
    procesos = [p for p in raiz.iter(f"{_NS}process")]
    con_inicio = [p for p in procesos if p.find(f"{_NS}startEvent") is not None]
    if not con_inicio:
        return Grafo({}, {}, None, [Problema("no_start", "El diagrama no tiene evento de inicio")])
    if len(con_inicio) > 1:
        return Grafo({}, {}, None, [Problema("multiple_pools",
                                             "Hay varios procesos (piscinas) con inicio: no se soporta")])
    proceso = con_inicio[0]
    mensajes = {m.get("id"): (m.get("name") or m.get("id")) for m in raiz.iter(f"{_NS}message")}
    errores = {e.get("id"): (e.get("errorCode") or e.get("name") or e.get("id")) for e in raiz.iter(f"{_NS}error")}

    calles = {}
    for calle in proceso.iter(f"{_NS}lane"):
        for ref in calle.findall(f"{_NS}flowNodeRef"):
            if ref.text and calle.get("name"):
                calles[ref.text.strip()] = calle.get("name").strip()

    nodos, flujos, problemas, avisos = {}, {}, [], []

    def ambito(contenedor, padre: Optional[str]) -> None:
        for hijo in contenedor:
            tipo = _local(hijo.tag)
            if tipo in _IGNORADOS:
                continue
            if tipo == "sequenceFlow":
                cond = hijo.find(f"{_NS}conditionExpression")
                flujos[hijo.get("id")] = Flujo(hijo.get("id"), hijo.get("sourceRef"), hijo.get("targetRef"),
                                              (cond.text or "").strip() if cond is not None and cond.text else None,
                                              hijo.get("name"))
                continue
            defs = [_local(d.tag) for d in hijo if _local(d.tag).endswith("EventDefinition")]
            calle = calles.get(hijo.get("id")) or (nodos[padre].calle if padre and padre in nodos else None)
            n = Nodo(hijo.get("id"), tipo, hijo.get("name"), defecto=hijo.get("default"), calle=calle,
                     rol=rol_de_calle(calle), definiciones=defs, padre=padre, ext=_extensiones(hijo))
            nodos[n.id] = n
            _comprobar(hijo, n, defs, mensajes, errores, problemas, avisos)
            if tipo == "subProcess" and n.tipo in _SOPORTADOS:
                ambito(hijo, n.id)
                internos = [c for c in hijo if _local(c.tag) == "startEvent"]
                simples = [c for c in internos if not [d for d in c if _local(d.tag).endswith("EventDefinition")]]
                if len(simples) != 1 or len(internos) != 1:
                    problemas.append(Problema("subprocess_without_start",
                                              f"el subproceso «{_etiqueta(n)}» necesita un único inicio simple",
                                              _etiqueta(n)))
                else:
                    n.inicio_interno = simples[0].get("id")

    ambito(proceso, None)

    for f in flujos.values():
        if f.origen not in nodos or f.destino not in nodos:
            # Antes: KeyError (500) al llegar la ficha a un destino inexistente.
            problemas.append(Problema("dangling_flow", f"el flujo «{f.id}» une elementos que no existen", f.id))
            continue
        nodos[f.origen].salidas.append(f.id)
        nodos[f.destino].entradas.append(f.id)
        if f.condicion and _condicion(f.condicion) is None:
            problemas.append(Problema("bad_condition",
                                      f"condición que no se puede evaluar en el flujo «{f.id}»: {f.condicion}",
                                      f.nombre or f.id, f.condicion[:200]))
    for n in nodos.values():
        if n.tipo == "boundaryEvent":
            host = nodos.get(n.adjunto or "")
            if host is None or host.tipo not in ACTIVIDADES:
                problemas.append(Problema("boundary_without_host",
                                          f"el evento de borde «{_etiqueta(n)}» no va pegado a una actividad",
                                          _etiqueta(n)))
            else:
                host.bordes.append(n.id)
                n.padre = host.padre
        if n.tipo in ("exclusiveGateway", "inclusiveGateway") and len(n.salidas) > 1:
            n.decision = not any(flujos[f].condicion for f in n.salidas)
            if not n.decision:
                sin = [flujos[f] for f in n.salidas if not flujos[f].condicion and f != n.defecto]
                for f in sin:
                    avisos.append(Problema("flow_never_taken",
                                           f"la salida «{f.nombre or f.id}» de «{_etiqueta(n)}» no tiene condición "
                                           "ni es la de por defecto: nunca se toma", f.nombre or f.id))
        if n.defecto and n.defecto not in n.salidas:
            problemas.append(Problema("bad_default", f"la salida por defecto de «{_etiqueta(n)}» no sale de él",
                                      _etiqueta(n)))

    inicios = [n for n in nodos.values() if n.tipo == "startEvent" and n.padre is None]
    simples = [n for n in inicios if not n.definiciones]
    inicio = (simples or inicios)[0].id if inicios else None
    if inicio and nodos[inicio].definiciones:
        avisos.append(Problema("start_with_definition",
                               "el inicio tiene definición (mensaje o temporizador): se arranca a mano o por la API",
                               _etiqueta(nodos[inicio]), ", ".join(nodos[inicio].definiciones)))
    for n in nodos.values():
        if n.tipo != "endEvent" and not n.salidas and n.tipo in _SOPORTADOS:
            problemas.append(Problema("no_outgoing", f"«{_etiqueta(n)}» no tiene salida", _etiqueta(n)))
    g = Grafo(nodos, flujos, inicio, problemas, avisos)
    if inicio and not problemas:
        alcanzables, pila = {inicio}, [inicio]
        while pila:
            for s in g.sucesores(pila.pop()):
                if s in nodos and s not in alcanzables:
                    alcanzables.add(s)
                    pila.append(s)
        for n in nodos.values():
            if n.id not in alcanzables and n.tipo != "startEvent":
                avisos.append(Problema("unreachable", f"«{_etiqueta(n)}» no se alcanza desde el inicio",
                                       _etiqueta(n)))
    return g


def _comprobar(el, n: Nodo, defs: list, mensajes: dict, errores: dict, problemas: list, avisos: list) -> None:
    """Lo que el motor sabe hacer con este elemento, o el problema que lo impide."""
    tipo, etq = n.tipo, _etiqueta(n)

    def mal(code, texto, extra=None):
        problemas.append(Problema(code, texto, etq, extra))

    if tipo not in _SOPORTADOS:
        mal("unsupported_element", f"{tipo} «{etq}»", tipo)
        return
    if tipo == "subProcess" and el.get("triggeredByEvent") == "true":
        mal("unsupported_element", f"subproceso de evento «{etq}»", "eventSubProcess")
        return
    if any(_local(c.tag) in ("multiInstanceLoopCharacteristics", "standardLoopCharacteristics") for c in el):
        mal("unsupported_element", f"actividad múltiple o en bucle «{etq}»", "loop")
    if "compensateEventDefinition" in defs or el.get("isForCompensation") == "true":
        mal("unsupported_element", f"compensación «{etq}»", "compensation")
        return

    def temporizador() -> Optional[tuple]:
        timer = el.find(f"{_NS}timerEventDefinition")
        dur, fecha = timer.find(f"{_NS}timeDuration"), timer.find(f"{_NS}timeDate")
        if timer.find(f"{_NS}timeCycle") is not None:
            mal("invalid_timer", f"temporizador cíclico «{etq}»: no se soporta")
            return None
        if dur is not None and dur.text and _duracion(dur.text.strip()) is not None:
            return ("duration", dur.text.strip())
        if fecha is not None and fecha.text and _fecha(fecha.text.strip()) is not None:
            return ("date", fecha.text.strip())
        mal("invalid_timer", f"temporizador sin duración ni fecha válidas «{etq}»")
        return None

    def mensaje() -> Optional[str]:
        d = el.find(f"{_NS}messageEventDefinition")
        ref = d.get("messageRef") if d is not None else el.get("messageRef")
        nombre = mensajes.get(ref) if ref else None
        if not nombre:
            mal("message_without_name", f"«{etq}» espera un mensaje sin nombre (messageRef)")
        return nombre

    if tipo == "endEvent":
        n.terminar = "terminateEventDefinition" in defs
        if "errorEventDefinition" in defs:
            d = el.find(f"{_NS}errorEventDefinition")
            n.error_code = errores.get(d.get("errorRef")) if d.get("errorRef") else "error"
        otras = [d for d in defs if d not in ("terminateEventDefinition", "errorEventDefinition")]
        if otras or len(defs) > 1:
            mal("end_with_definition", f"endEvent con {', '.join(defs)} «{etq}»", ", ".join(otras or defs))
    elif tipo == "intermediateCatchEvent":
        if defs == ["timerEventDefinition"]:
            n.temporizador = temporizador()
        elif defs == ["messageEventDefinition"]:
            n.mensaje = mensaje()
        else:
            mal("catch_without_timer", f"intermediateCatchEvent sin temporizador ni mensaje «{etq}»")
    elif tipo == "intermediateThrowEvent" and defs:
        mal("throw_with_definition", f"intermediateThrowEvent con {', '.join(defs)} «{etq}»", ", ".join(defs))
    elif tipo == "receiveTask":
        n.mensaje = mensaje()
    elif tipo == "boundaryEvent":
        n.adjunto = el.get("attachedToRef")
        n.interrumpe = el.get("cancelActivity", "true") != "false"
        if defs == ["timerEventDefinition"]:
            n.temporizador = temporizador()
        elif defs == ["messageEventDefinition"]:
            n.mensaje = mensaje()
        elif defs == ["errorEventDefinition"]:
            d = el.find(f"{_NS}errorEventDefinition")
            n.error_code = errores.get(d.get("errorRef")) if d.get("errorRef") else None
            n.interrumpe = True
        else:
            mal("boundary_unsupported", f"evento de borde «{etq}» con {', '.join(defs) or 'ninguna definición'}",
                ", ".join(defs))
    elif tipo == "callActivity":
        n.llamado = (el.get("calledElement") or "").strip() or None
        if not n.llamado:
            mal("call_without_target", f"la llamada «{etq}» no dice a qué proceso (calledElement)")
    if tipo in AUTOMATICOS and n.ext.get("action"):
        from app.services.bpmn_acciones import ACCIONES
        if n.ext["action"].strip() not in ACCIONES:
            mal("unknown_action", f"acción desconocida «{n.ext['action']}» en «{etq}»", n.ext["action"][:60])
        if n.ext.get("actionConfig"):
            try:
                if not isinstance(json.loads(n.ext["actionConfig"]), dict):
                    raise ValueError
            except ValueError:
                mal("bad_action_config", f"actionConfig de «{etq}» no es un objeto JSON")
    if n.ext.get("formFields"):
        try:
            n.formulario = leer_formulario(n.ext["formFields"])
        except (ValueError, TypeError):
            mal("bad_form", f"formulario no válido en «{etq}»")
    if n.ext.get("dueIn") and _duracion(n.ext["dueIn"].strip()) is None:
        mal("invalid_due", f"plazo (dueIn) no válido en «{etq}»: {n.ext['dueIn']}", n.ext["dueIn"][:40])
    if n.ext.get("retries"):
        try:
            if not 0 <= int(n.ext["retries"]) <= 20:
                raise ValueError
        except ValueError:
            mal("bad_retries", f"reintentos no válidos en «{etq}» (0-20)")


def validar(xml: str) -> dict:
    """¿Se puede ejecutar este diagrama? Con los problemas (bloquean) y los avisos, cada uno con su codigo."""
    g = leer(xml)
    return {"executable": not g.problemas, "problems": [p.como_dict() for p in g.problemas],
            "warnings": [p.como_dict() for p in g.avisos]}


# ── Condiciones, duraciones y fechas ────────────────────────────────────────

_COMPARACION = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*(==|!=|>=|<=|>|<)\s*(.+?)\s*$")


def _valor(texto: str):
    t = texto.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
        return t[1:-1]
    if t.lower() in ("true", "false"):
        return t.lower() == "true"
    try:
        return float(t)
    except ValueError:
        return None


def _condicion(texto: str):
    """[[(var, op, valor)]] (or de ands) o None si no se puede leer. Nunca se evalua codigo."""
    t = texto.strip()
    if t.startswith("${") and t.endswith("}"):
        t = t[2:-1]
    t = t.replace("&&", " and ").replace("||", " or ")
    grupos = []
    for parte_or in re.split(r"\s+or\s+", t):
        ands = []
        for parte in re.split(r"\s+and\s+", parte_or):
            m = _COMPARACION.match(parte)
            if not m or _valor(m.group(3)) is None:
                return None
            ands.append((m.group(1), m.group(2), _valor(m.group(3))))
        grupos.append(ands)
    return grupos


def cumple(texto: Optional[str], variables: dict) -> bool:
    grupos = _condicion(texto or "")
    if grupos is None:
        return False

    def una(var, op, esperado) -> bool:
        if var not in variables:
            return False
        actual = variables[var]
        if isinstance(esperado, bool):
            actual = str(actual).lower() in ("true", "1", "yes", "si", "sí") if not isinstance(actual, bool) else actual
        elif isinstance(esperado, float):
            try:
                actual = float(actual)
            except (TypeError, ValueError):
                return False
        else:
            actual = str(actual)
        try:
            return {"==": actual == esperado, "!=": actual != esperado, ">": actual > esperado,
                    "<": actual < esperado, ">=": actual >= esperado, "<=": actual <= esperado}[op]
        except TypeError:
            return False

    return any(all(una(*c) for c in ands) for ands in grupos)


_DURACION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def _duracion(texto: str) -> Optional[timedelta]:
    m = _DURACION.match(texto or "")
    if not m or not any(m.groups()):
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return timedelta(days=d, hours=h, minutes=mi, seconds=s)


def _fecha(texto: str) -> Optional[datetime]:
    try:
        f = datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    except ValueError:
        return None
    return f if f.tzinfo else f.replace(tzinfo=timezone.utc)


def _interpolar(texto: str, variables: dict) -> str:
    """`${var}` dentro de un texto → su valor (solo sustitucion, nunca evaluacion)."""
    return re.sub(r"\$\{\s*([A-Za-z_][\w.]*)\s*\}", lambda m: str(variables.get(m.group(1), "")), texto or "")


# ── Variables ───────────────────────────────────────────────────────────────

def validar_variables(db: Session, org, variables: Optional[dict]) -> dict:
    """Las variables que llegan de la API, comprobadas (nombre y tamaño)."""
    from app.services.settings_service import get_runtime_int

    variables = variables or {}
    if not isinstance(variables, dict):
        raise error(422, "bpm_variables_nombre_no_valido", nombres="?")
    malos = [k for k in variables if not isinstance(k, str) or not _NOMBRE_DE_VARIABLE.match(k)]
    if malos:
        raise error(422, "bpm_variables_nombre_no_valido", nombres=", ".join(map(str, malos[:10])))
    tope = get_runtime_int(db, "BPMN_MAX_VARIABLES_BYTES", org)
    tamano = len(json.dumps(variables, default=str).encode("utf8"))
    if tope and tamano > tope:
        raise error(413, "bpm_variables_demasiado_grandes", bytes=tamano, max=tope)
    return variables


def esquema(proc_o_texto) -> list:
    """Las variables declaradas de un proceso (`variables_schema`)."""
    texto = getattr(proc_o_texto, "variables_schema", proc_o_texto)
    if not texto:
        return []
    try:
        datos = json.loads(texto) if isinstance(texto, str) else texto
        return leer_formulario(json.dumps(datos)) or []
    except (ValueError, TypeError):
        return []


def _tipar(nombre: str, valor, tipo: str, opciones: Optional[list] = None):
    """`valor` convertido a `tipo`, o 422 `bpm_variable_tipo_no_valido`."""
    def mal():
        return error(422, "bpm_variable_tipo_no_valido", nombre=nombre, tipo=tipo)

    if valor is None:
        return None
    try:
        if tipo in ("string", "text", "user"):
            if isinstance(valor, (dict, list)):
                raise mal()
            return str(valor)[:5000]
        if tipo == "number":
            if isinstance(valor, bool):
                raise mal()
            return float(valor)
        if tipo == "integer":
            if isinstance(valor, bool) or float(valor) != int(float(valor)):
                raise mal()
            return int(float(valor))
        if tipo == "boolean":
            if isinstance(valor, bool):
                return valor
            t = str(valor).strip().lower()
            if t in ("true", "1", "yes", "si", "sí"):
                return True
            if t in ("false", "0", "no"):
                return False
            raise mal()
        if tipo == "date":
            return date.fromisoformat(str(valor)[:10]).isoformat()
        if tipo == "enum":
            if opciones and str(valor) not in opciones:
                raise mal()
            return str(valor)
    except (TypeError, ValueError):
        raise mal()
    return valor


def tipar_variables(campos: list, variables: dict, *, exigir: bool = False, solo_declaradas: bool = False) -> dict:
    """Variables convertidas a su tipo declarado.

    `exigir`: los campos `required` tienen que venir (formulario de una tarea).
    `solo_declaradas`: una variable que no es del formulario es un 422.
    """
    por_nombre = {c["name"]: c for c in campos}
    if solo_declaradas:
        sobran = [k for k in variables if k not in por_nombre]
        if sobran:
            raise error(422, "bpm_variable_no_declarada", nombres=", ".join(sobran[:10]))
    out = dict(variables)
    for c in campos:
        if c["name"] in variables:
            out[c["name"]] = _tipar(c["name"], variables[c["name"]], c["type"], c.get("options"))
        if exigir and c.get("required") and out.get(c["name"]) in (None, ""):
            raise error(422, "bpm_campo_obligatorio", nombre=c.get("label") or c["name"])
    return out


# ── Asignacion ──────────────────────────────────────────────────────────────

@dataclass
class Perfil:
    """Quien mira la bandeja o completa un paso: su rol y sus grupos (una consulta por peticion)."""
    id: str
    rol: Optional[str]
    admin: bool
    grupos: set = field(default_factory=set)     # "approval:<id>", "team:<id>"


def perfil(db: Optional[Session], user) -> Perfil:
    rol = getattr(user.role, "value", user.role)
    p = Perfil(user.id, rol, bool(getattr(user, "is_superadmin", False)) or rol == "admin")
    if db is None:
        return p
    from app.models.billing_reports import ApprovalGroup
    from app.models.service_desk.agents import AgentGroupMember
    for gid, miembros in db.query(ApprovalGroup.id, ApprovalGroup.member_ids).all():
        try:
            if user.id in json.loads(miembros or "[]"):
                p.grupos.add(f"approval:{gid}")
        except (TypeError, ValueError):
            continue
    for (gid,) in db.query(AgentGroupMember.group_id).filter(AgentGroupMember.user_id == user.id).all():
        p.grupos.add(f"team:{gid}")
    return p


def candidatos(paso: BPMNInstanceStep) -> list[str]:
    out = [t for t in (paso.candidate_groups or "").split(",") if t]
    if paso.candidate_role:
        out.append(f"role:{paso.candidate_role}")
    return out


def puede_completar(paso: BPMNInstanceStep, quien, db: Optional[Session] = None) -> bool:
    """¿Puede `quien` (usuario o `Perfil`) completar el paso? Admin siempre (salvo segregacion, aparte)."""
    p = quien if isinstance(quien, Perfil) else perfil(db, quien)
    if p.admin:
        return True
    if paso.assignee_user_id:
        return paso.assignee_user_id == p.id
    tokens = candidatos(paso)
    if not tokens:
        return True
    return any(t == f"role:{p.rol}" or t == f"user:{p.id}" or t in p.grupos for t in tokens)


class _Resolutor:
    """Resuelve personas y grupos por id, correo o nombre, con cache por ejecucion."""

    def __init__(self, db: Session, org: Optional[str]):
        self.db, self.org, self._cache = db, org, {}

    def usuario(self, valor) -> Optional[str]:
        from app.models.user import User
        v = str(valor or "").strip()
        if not v:
            return None
        if ("u", v) not in self._cache:
            q = self.db.query(User.id).filter(User.is_active.is_(True))
            if self.org:
                q = q.filter(User.organization_id == self.org)
            fila = q.filter(User.email == v.lower()).first() if "@" in v else q.filter(User.id == v).first()
            self._cache[("u", v)] = fila[0] if fila else None
        return self._cache[("u", v)]

    def grupo(self, valor: str) -> Optional[str]:
        from app.models.billing_reports import ApprovalGroup
        from app.models.service_desk.agents import AgentGroup
        v = (valor or "").strip()
        if not v:
            return None
        if ("g", v) not in self._cache:
            rol = rol_de_calle(v)
            token = f"role:{rol}" if rol else None
            clase, _, resto = v.partition(":")
            if token is None and clase in ("approval", "team") and resto:
                modelo = ApprovalGroup if clase == "approval" else AgentGroup
                fila = self.db.query(modelo.id).filter(modelo.id == resto).first()
                token = f"{clase}:{fila[0]}" if fila else None
            if token is None and clase == "user" and resto:
                uid = self.usuario(resto)
                token = f"user:{uid}" if uid else None
            if token is None:
                fila = self.db.query(ApprovalGroup.id).filter(ApprovalGroup.name == v).first()
                token = f"approval:{fila[0]}" if fila else None
            if token is None:
                fila = self.db.query(AgentGroup.id).filter(AgentGroup.name == v).first()
                token = f"team:{fila[0]}" if fila else None
            self._cache[("g", v)] = token
        return self._cache[("g", v)]


def _valor_de(expr: Optional[str], inst: BPMNInstance, variables: dict):
    """`${initiator}`, `${variable}` o el literal."""
    t = (expr or "").strip()
    m = _EXPRESION.match(t)
    if not m:
        return t or None
    nombre = m.group(1)
    if nombre in ("initiator", "starter"):
        return inst.started_by_user_id
    return variables.get(nombre)


def _asignar(r: _Resolutor, inst: BPMNInstance, n: Nodo, variables: dict) -> dict:
    """Columnas de asignacion y plazo de un paso humano."""
    out: dict = {"candidate_role": n.rol}
    tokens: list[str] = []
    if n.ext.get("assignee"):
        out["assignee_user_id"] = r.usuario(_valor_de(n.ext["assignee"], inst, variables))
    for t in (n.ext.get("candidateUsers") or "").split(","):
        uid = r.usuario(_valor_de(t, inst, variables)) if t.strip() else None
        if uid:
            tokens.append(f"user:{uid}")
    for t in (n.ext.get("candidateGroups") or "").split(","):
        tok = r.grupo(str(_valor_de(t, inst, variables) or "")) if t.strip() else None
        if tok:
            tokens.append(tok)
    if n.calle and not n.rol:
        tok = r.grupo(n.calle)   # calle con el nombre de un grupo de aprobacion o una cola
        if tok:
            tokens.append(tok)
    if tokens:
        out["candidate_groups"] = ",".join(dict.fromkeys(tokens))[:1000]
    if n.ext.get("dueIn") and _duracion(n.ext["dueIn"].strip()):
        out["sla_due_at"] = _ahora() + _duracion(n.ext["dueIn"].strip())
    elif n.ext.get("dueDate"):
        f = _fecha(str(_valor_de(n.ext["dueDate"], inst, variables) or ""))
        if f:
            out["sla_due_at"] = f
    return out


# ── Ejecucion ───────────────────────────────────────────────────────────────

def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def version_ejecutable(db: Session, proc: BPMNProcess) -> BPMNProcessVersion:
    """La version que arrancan las instancias nuevas.

    La publicada. Si el proceso nunca ha publicado ni retirado ninguna, la
    ultima guardada (modo borrador, para probar mientras se diseña). Si todas
    estan retiradas, 409: retirar es «no se arranca mas».
    """
    q = db.query(BPMNProcessVersion).filter(BPMNProcessVersion.process_id == proc.id)
    v = q.filter(BPMNProcessVersion.is_published.is_(True)).order_by(BPMNProcessVersion.version.desc()).first()
    if v is not None:
        return v
    if q.filter(BPMNProcessVersion.retired_at.isnot(None)).first() is not None:
        raise error(409, "bpm_sin_version_publicada")
    v = q.order_by(BPMNProcessVersion.version.desc()).first()
    if v is None:
        raise error(422, "bpm_sin_diagrama")
    return v


class _Grafos:
    """Grafos por (proceso, version), leidos una sola vez por peticion."""

    def __init__(self, db: Session):
        self.db = db
        self._cache: dict[tuple[str, int], Grafo] = {}

    def de(self, inst: BPMNInstance) -> Grafo:
        return self.version(inst.process_id, inst.version)

    def version(self, process_id: str, version: int) -> Grafo:
        clave = (process_id, version)
        if clave not in self._cache:
            v = self.db.query(BPMNProcessVersion).filter(BPMNProcessVersion.process_id == process_id,
                                                         BPMNProcessVersion.version == version).first()
            if v is None:
                raise error(409, "bpm_version_diagrama_no_existe")
            self._cache[clave] = leer(v.bpmn_xml)
        return self._cache[clave]


def _grafo(db: Session, inst: BPMNInstance) -> Grafo:
    return _Grafos(db).de(inst)


def _variables(inst: BPMNInstance) -> dict:
    try:
        return json.loads(inst.variables or "{}")
    except (TypeError, ValueError):
        return {}


def _json(texto) -> dict:
    try:
        v = json.loads(texto) if texto else {}
        return v if isinstance(v, dict) else {"value": v}
    except (TypeError, ValueError):
        return {}


def _limite(db: Session, org) -> int:
    from app.core.config import settings
    from app.services.settings_service import get_runtime_int
    # Un 0 o un valor vacio en Ajustes no quita la proteccion contra bucles.
    return get_runtime_int(db, "BPMN_MAX_AUTOMATIC_STEPS", org) or settings.BPMN_MAX_AUTOMATIC_STEPS


def _paso(db, inst, nodo: Nodo, estado: str, **kw) -> BPMNInstanceStep:
    p = BPMNInstanceStep(instance_id=inst.id, organization_id=inst.organization_id, element_id=nodo.id,
                         element_type=nodo.tipo, name=nodo.nombre, status=estado,
                         completed_at=_ahora() if estado == "completed" else None, **kw)
    db.add(p)
    return p


def _activos(db: Session, inst: BPMNInstance) -> list[BPMNInstanceStep]:
    db.flush()
    return db.query(BPMNInstanceStep).filter(BPMNInstanceStep.instance_id == inst.id,
                                             BPMNInstanceStep.status == "active").all()


def _cerrar_paso(p: BPMNInstanceStep, estado: str = "cancelled") -> None:
    p.status = estado
    p.completed_at = _ahora()


def _fallar(inst: BPMNInstance, codigo: str, motivo: str, **params) -> None:
    inst.status = "failed"
    inst.error = motivo[:500]
    inst.error_code = codigo
    inst.error_params = json.dumps(params, default=str) if params else None
    inst.ended_at = _ahora()


class _Corrida:
    """Una pasada del motor sobre una instancia: la cola de fichas y lo que hace falta para moverlas."""

    def __init__(self, db: Session, inst: BPMNInstance, g: Grafo, profundidad: int = 0, avisar_padre: bool = True):
        self.db, self.inst, self.g = db, inst, g
        self.avisar_padre = avisar_padre   # False: la llamada que la arranco mira el resultado ella misma
        self.pendientes: list[tuple[str, Optional[str]]] = []
        self.resolutor = _Resolutor(db, inst.organization_id)
        self.profundidad = profundidad
        self.avisos: list[tuple[str, BPMNInstanceStep]] = []   # (user_id, paso) a avisar al terminar

    # -- fichas --
    def salir(self, n: Nodo, flujos: Optional[Iterable[str]] = None) -> None:
        for f in (n.salidas if flujos is None else flujos):
            self.pendientes.append((self.g.flujos[f].destino, f))

    def quitar_fichas(self, ambito: Optional[str]) -> None:
        self.pendientes = [(nid, f) for nid, f in self.pendientes if not self.g.dentro(nid, ambito)]

    # -- bucle --
    def avanzar(self, entradas: list[tuple[str, Optional[str]]]) -> None:
        self.pendientes += entradas
        limite = _limite(self.db, self.inst.organization_id)
        vueltas = 0
        while self.inst.status == "running":
            if not self.pendientes:
                if self.revisar():
                    continue
                break
            vueltas += 1
            if vueltas > limite:
                _fallar(self.inst, "loop_limit", f"Más de {limite} pasos automáticos seguidos: ¿un bucle sin espera?",
                        limit=limite)
                break
            nodo_id, flujo = self.pendientes.pop(0)
            if nodo_id in self.g.nodos:
                self.entrar(self.g.nodos[nodo_id], flujo)
        self.db.flush()
        if self.inst.status == "running" and not _activos(self.db, self.inst):
            self.inst.status = "completed"
            self.inst.ended_at = _ahora()
        if self.inst.status in _TERMINADOS and self.avisar_padre:
            _al_terminar(self.db, self.inst, self.profundidad)
        self.avisar()

    def revisar(self) -> bool:
        """Sin fichas en la cola: uniones inclusivas que ya pueden pasar y subprocesos vacios."""
        activos = _activos(self.db, self.inst)
        hubo = False
        for p in activos:
            n = self.g.nodos.get(p.element_id)
            if n is None or p.status != "active":
                continue
            if p.wait_kind == ESPERA_UNION and n.tipo == "inclusiveGateway":
                otros = [q for q in activos if q.id != p.id and q.status == "active"]
                if not any(self.g.alcanza(q.element_id, n.id) for q in otros if q.element_id in self.g.nodos):
                    _cerrar_paso(p, "completed")
                    self.repartir(n)
                    hubo = True
            elif p.wait_kind == ESPERA_SUBPROCESO:
                dentro = [q for q in activos if q.status == "active" and self.g.dentro(q.element_id, n.id)]
                if not dentro:
                    _cerrar_paso(p, "completed")
                    self.cancelar_bordes(n.id)
                    self.salir(n)
                    hubo = True
        return hubo

    # -- elementos --
    def entrar(self, n: Nodo, flujo: Optional[str]) -> None:
        db, inst, g = self.db, self.inst, self.g
        variables = _variables(inst)
        if n.tipo in HUMANOS or (n.tipo in AUTOMATICOS and not n.accion):
            extra = {"result": json.dumps({"automatic": False, "tipo": n.tipo})} if n.tipo in AUTOMATICOS else {}
            if n.es_aprobacion:
                extra = {"result": json.dumps({**_json(extra.get("result")), "approval": True})}
            asignacion = _asignar(self.resolutor, inst, n, variables)
            p = _paso(db, inst, n, "active", wait_kind=ESPERA_TAREA, **asignacion, **extra)
            if asignacion.get("assignee_user_id"):
                self.avisos.append((asignacion["assignee_user_id"], p))
            self.crear_bordes(n)
        elif n.tipo in AUTOMATICOS:
            _paso(db, inst, n, "active", wait_kind=ESPERA_TRABAJO, due_at=_ahora(), candidate_role=n.rol,
                  result=json.dumps({"automatic": True, "action": n.accion}))
            self.crear_bordes(n)
        elif n.tipo == "receiveTask" or (n.tipo == "intermediateCatchEvent" and n.mensaje):
            _paso(db, inst, n, "active", wait_kind=ESPERA_MENSAJE, result=json.dumps({"message": n.mensaje}))
            self.crear_bordes(n)
        elif n.tipo == "intermediateCatchEvent":
            clase, texto = n.temporizador
            vence = _ahora() + _duracion(texto) if clase == "duration" else _fecha(texto)
            _paso(db, inst, n, "active", due_at=vence, wait_kind=ESPERA_TEMPORIZADOR)
        elif n.tipo == "endEvent":
            _paso(db, inst, n, "completed", **({"result": json.dumps({"error": n.error_code})} if n.error_code else {}))
            if n.error_code:
                self.lanzar_error(n.padre, n.error_code, desde=n.id)
            elif n.terminar:
                if n.padre is None:
                    self.cancelar_ambito(None)
                    inst.status = "completed"
                    inst.ended_at = _ahora()
                else:
                    self.cancelar_ambito(n.padre)
        elif n.tipo in ("exclusiveGateway", "inclusiveGateway"):
            if n.tipo == "inclusiveGateway" and len(n.entradas) > 1:
                self.llegar_a_union(n, flujo)
                return
            self.repartir(n)
        elif n.tipo == "parallelGateway" and len(n.entradas) > 1:
            self.llegar_a_union(n, flujo)
        elif n.tipo == "subProcess":
            _paso(db, inst, n, "active", wait_kind=ESPERA_SUBPROCESO)
            self.crear_bordes(n)
            self.pendientes.append((n.inicio_interno, None))
        elif n.tipo == "callActivity":
            p = _paso(db, inst, n, "active", wait_kind=ESPERA_LLAMADA)
            self.crear_bordes(n)
            db.flush()
            self.llamar(n, p, variables)
        else:
            # startEvent, parallelGateway de reparto, throw sin definicion
            _paso(db, inst, n, "completed")
            self.salir(n)

    def repartir(self, n: Nodo) -> None:
        """Salida de una compuerta exclusiva o inclusiva (o union inclusiva ya completa)."""
        if len(n.salidas) <= 1:
            _paso(self.db, self.inst, n, "completed")
            self.salir(n)
            return
        if n.decision:
            res = {"multiple": True} if n.tipo == "inclusiveGateway" else {}
            _paso(self.db, self.inst, n, "active", candidate_role=n.rol, wait_kind=ESPERA_DECISION,
                  **({"result": json.dumps(res)} if res else {}),
                  **{k: v for k, v in _asignar(self.resolutor, self.inst, n, _variables(self.inst)).items()
                     if k != "candidate_role"})
            return
        _paso(self.db, self.inst, n, "completed")
        variables = _variables(self.inst)
        con = [f for f in n.salidas if f != n.defecto and self.g.flujos[f].condicion
               and cumple(self.g.flujos[f].condicion, variables)]
        if n.tipo == "exclusiveGateway":
            con = con[:1]
        elegidos = con or ([n.defecto] if n.defecto else [])
        if not elegidos:
            _fallar(self.inst, "no_route",
                    f"Ninguna condición de «{_etiqueta(n)}» se cumple y no hay salida por defecto",
                    element=_etiqueta(n))
            return
        self.salir(n, elegidos)

    def llegar_a_union(self, n: Nodo, flujo: Optional[str]) -> None:
        """Una ficha llega a una union. Paralela: una por flujo de entrada. Inclusiva: la decide `revisar`."""
        self.db.flush()
        union = self.db.query(BPMNInstanceStep).filter(
            BPMNInstanceStep.instance_id == self.inst.id, BPMNInstanceStep.element_id == n.id,
            BPMNInstanceStep.status == "active").first()
        if union is None:
            union = _paso(self.db, self.inst, n, "active", arrived=0, wait_kind=ESPERA_UNION,
                          result=json.dumps({"flows": []}))
        llegados = _json(union.result).get("flows") or []
        if flujo and flujo not in llegados:
            llegados.append(flujo)
        union.result = json.dumps({"flows": llegados})
        union.arrived = (union.arrived or 0) + 1
        if n.tipo == "parallelGateway" and set(n.entradas) <= set(llegados):
            _cerrar_paso(union, "completed")
            self.salir(n)

    def crear_bordes(self, host: Nodo) -> None:
        for bid in host.bordes:
            b = self.g.nodos[bid]
            if b.temporizador:
                clase, texto = b.temporizador
                vence = _ahora() + _duracion(texto) if clase == "duration" else _fecha(texto)
                _paso(self.db, self.inst, b, "active", due_at=vence, wait_kind=ESPERA_TEMPORIZADOR,
                      result=json.dumps({"boundary": host.id}))
            elif b.mensaje:
                _paso(self.db, self.inst, b, "active", wait_kind=ESPERA_MENSAJE,
                      result=json.dumps({"message": b.mensaje, "boundary": host.id}))

    def cancelar_bordes(self, host_id: str) -> None:
        bordes = set(self.g.nodos[host_id].bordes) if host_id in self.g.nodos else set()
        if not bordes:
            return
        for p in _activos(self.db, self.inst):
            if p.element_id in bordes:
                _cerrar_paso(p)

    def cancelar_paso(self, p: BPMNInstanceStep) -> None:
        """Cancela un paso activo y lo que cuelga de el (aprobacion abierta, instancia hija)."""
        if p.status != "active":
            return
        _cerrar_paso(p)
        if p.wait_kind == ESPERA_APROBACION:
            from app.services.approval_engine import fuentes
            fuentes.cerrar(self.db, TIPO_DE_APROBACION, p.id, "cancelled", "BPM")
        if p.wait_kind == ESPERA_LLAMADA:
            for hija in self.db.query(BPMNInstance).filter(BPMNInstance.parent_step_id == p.id,
                                                           BPMNInstance.status.in_(("running", "suspended"))).all():
                _cancelar_instancia(self.db, hija)

    def cancelar_ambito(self, ambito: Optional[str]) -> None:
        """Termina todo lo activo dentro de `ambito` (None: la instancia entera) y sus fichas."""
        for p in _activos(self.db, self.inst):
            if self.g.dentro(p.element_id, ambito) or p.element_id not in self.g.nodos and ambito is None:
                self.cancelar_paso(p)
        self.quitar_fichas(ambito)

    def interrumpir(self, host: Nodo) -> None:
        """Un borde que interrumpe: cancela la actividad, lo de dentro y sus otros bordes."""
        for p in _activos(self.db, self.inst):
            if p.element_id == host.id or p.element_id in host.bordes or self.g.dentro(p.element_id, host.id):
                self.cancelar_paso(p)
        self.quitar_fichas(host.id)

    def lanzar_error(self, ambito: Optional[str], codigo: str, desde: Optional[str] = None) -> bool:
        """Un error BPMN: lo captura el borde de error mas cercano; si no, sube al padre o falla."""
        cadena = []
        if desde and desde in self.g.nodos and self.g.nodos[desde].tipo in ACTIVIDADES:
            cadena.append(desde)
        a = ambito
        while a is not None:
            cadena.append(a)
            a = self.g.nodos[a].padre
        for host_id in cadena:
            for b in self.g.bordes_de(host_id, "errorEventDefinition"):
                if b.error_code in (None, codigo):
                    self.interrumpir(self.g.nodos[host_id])
                    _paso(self.db, self.inst, b, "completed", result=json.dumps({"error": codigo}))
                    self.salir(b)
                    return True
        self.cancelar_ambito(None)
        self.pendientes.clear()
        _fallar(self.inst, "bpmn_error", f"Error BPMN «{codigo}» sin capturar", code=codigo)
        return False

    def llamar(self, n: Nodo, paso: BPMNInstanceStep, variables: dict) -> None:
        """callActivity: arranca la hija con la version publicada del proceso llamado."""
        if self.profundidad >= _MAX_PROFUNDIDAD:
            self.lanzar_error(n.padre, "call_depth", desde=n.id)
            return
        q = self.db.query(BPMNProcess).filter(BPMNProcess.key == n.llamado, BPMNProcess.is_active.is_(True))
        if self.inst.organization_id:
            q = q.filter(BPMNProcess.organization_id == self.inst.organization_id)
        proc = q.first()
        try:
            if proc is None:
                raise error(404, "no_encontrado", que="proceso")
            if proc.status == BPMNProcessStatus.archived:
                raise error(409, "bpm_proceso_archivado")
            v = version_ejecutable(self.db, proc)
            g = leer(v.bpmn_xml)
            if g.problemas:
                raise error(422, "bpm_diagrama_no_ejecutable", problemas="; ".join(map(str, g.problemas[:5])))
        except Exception:   # noqa: BLE001 — el motivo concreto va en el paso; la ficha sigue como error BPMN
            logger.info("BPMN: la llamada %s de la instancia %s no arranca", n.llamado, self.inst.id, exc_info=True)
            paso.result = json.dumps({"called": n.llamado, "error": "call_failed"})
            self.lanzar_error(n.padre, "call_failed", desde=n.id)
            return
        hija = BPMNInstance(process_id=proc.id, version=v.version, organization_id=self.inst.organization_id,
                            status="running", variables=json.dumps(variables),
                            started_by_user_id=self.inst.started_by_user_id, business_key=self.inst.business_key,
                            parent_instance_id=self.inst.id, parent_step_id=paso.id)
        self.db.add(hija)
        self.db.flush()
        paso.result = json.dumps({"called": n.llamado, "child": hija.id})
        _Corrida(self.db, hija, g, self.profundidad + 1, avisar_padre=False).avanzar([(g.inicio, None)])
        # La hija puede terminar sin esperar nada: se sigue aqui mismo, en esta corrida.
        if hija.status == "completed":
            self.inst.variables = json.dumps({**_variables(self.inst), **_variables(hija)})
            _cerrar_paso(paso, "completed")
            self.cancelar_bordes(n.id)
            self.salir(n)
        elif hija.status in ("failed", "cancelled"):
            codigo = _json(hija.error_params).get("code") or "call_failed"
            self.lanzar_error(n.padre, codigo, desde=n.id)

    # -- avisos --
    def avisar(self) -> None:
        for uid, p in self.avisos:
            _avisar_asignacion(self.db, uid, self.inst, p)
        self.avisos = []


def _avanzar(db: Session, inst: BPMNInstance, g: Grafo, entradas: list[tuple[str, Optional[str]]]) -> None:
    """Compatibilidad: entra en cada (nodo, flujo por el que llega) y sigue hasta que todo espera."""
    _Corrida(db, inst, g).avanzar(entradas)


def _al_terminar(db: Session, inst: BPMNInstance, profundidad: int = 0) -> None:
    """Una instancia hija termina: su padre sigue (completada) o recibe un error (fallida o cancelada)."""
    if not inst.parent_step_id or not inst.parent_instance_id:
        return
    padre = db.query(BPMNInstance).filter(BPMNInstance.id == inst.parent_instance_id).first()
    paso = db.query(BPMNInstanceStep).filter(BPMNInstanceStep.id == inst.parent_step_id).first()
    if padre is None or paso is None or padre.status != "running" or paso.status != "active":
        return
    g = _grafo(db, padre)
    n = g.nodos.get(paso.element_id)
    if n is None:
        return
    corrida = _Corrida(db, padre, g, max(0, profundidad - 1))
    if inst.status == "completed":
        padre.variables = json.dumps({**_variables(padre), **_variables(inst)})
        _cerrar_paso(paso, "completed")
        corrida.cancelar_bordes(n.id)
        corrida.salir(n)
    else:
        codigo = inst.error_params and _json(inst.error_params).get("code") or \
            ("call_cancelled" if inst.status == "cancelled" else "call_failed")
        corrida.lanzar_error(n.padre, codigo, desde=n.id)
    corrida.avanzar([])


def _cancelar_instancia(db: Session, inst: BPMNInstance) -> None:
    """Cancela la instancia, sus pasos activos (con aprobaciones abiertas) y sus hijas."""
    g = None
    try:
        g = _grafo(db, inst)
    except Exception:   # noqa: BLE001 — sin diagrama se cancela igual paso a paso
        logger.debug("BPMN: cancelar %s sin grafo", inst.id, exc_info=True)
    corrida = _Corrida(db, inst, g or Grafo({}, {}, None, []))
    for p in _activos(db, inst):
        corrida.cancelar_paso(p)
    inst.status = "cancelled"
    inst.ended_at = _ahora()


def _avisar_asignacion(db: Session, user_id: str, inst: BPMNInstance, paso: BPMNInstanceStep) -> None:
    """Aviso en la campana a quien se le asigna una tarea. Un fallo del aviso no para el proceso."""
    try:
        from app.services.notifications import notify_user
        nombre = paso.name or paso.element_id
        notify_user(db, user_id, "task_assigned", f"Tarea de proceso: {nombre}", None, "bpmn_instance", inst.id,
                    "/inbox?tab=procesos", aviso={"titulo": "bpm.tarea_asignada", "params": {"tarea": nombre}})
    except Exception:   # noqa: BLE001 — accesorio
        logger.warning("BPMN: no se pudo avisar de la tarea %s", paso.id, exc_info=True)


TIPO_DE_APROBACION = "bpmn_step"


def iniciar(db: Session, proc: BPMNProcess, user, variables: Optional[dict] = None,
            business_key: Optional[str] = None) -> BPMNInstance:
    if proc.status == BPMNProcessStatus.archived:
        raise error(409, "bpm_proceso_archivado")
    variables = validar_variables(db, proc.organization_id, variables)
    variables = tipar_variables(esquema(proc), variables)
    v = version_ejecutable(db, proc)
    g = leer(v.bpmn_xml)
    if g.problemas:
        raise error(422, "bpm_diagrama_no_ejecutable", problemas="; ".join(map(str, g.problemas[:20])))
    inst = BPMNInstance(process_id=proc.id, version=v.version, organization_id=proc.organization_id,
                        status="running", variables=json.dumps(variables), started_by_user_id=user.id,
                        business_key=(business_key or "").strip()[:120] or None)
    db.add(inst)
    db.flush()
    _Corrida(db, inst, g).avanzar([(g.inicio, None)])
    _auditar(db, user, "CREATE", inst, proc.name, {"version": v.version, "status": inst.status,
                                                   "business_key": inst.business_key})
    db.commit()
    ejecutar_trabajos(db, instancia_id=inst.id)
    return inst


def es_humano(paso: BPMNInstanceStep) -> bool:
    """¿Lo completa una persona? (tarea humana o decision manual)."""
    if paso.wait_kind is not None:
        return paso.wait_kind in ESPERAS_HUMANAS
    return paso.element_type in HUMANOS   # pasos anteriores a la migracion 169


def _es_aprobacion(paso: BPMNInstanceStep) -> bool:
    return paso.wait_kind in (ESPERA_DECISION, ESPERA_APROBACION) or bool(_json(paso.result).get("approval"))


def exigir_segregacion(db: Session, inst: BPMNInstance, paso: BPMNInstanceStep, user) -> None:
    """Quien diseño o publico la version que corre no aprueba en ella, si la empresa lo exige.

    Ajuste `BPMN_SEGREGACION_DE_FUNCIONES` (por empresa, apagado de serie).
    Aplica a decisiones, tareas marcadas `approval` y aprobaciones del motor.
    El admin no se la salta: la segregacion es justo para el que puede todo.
    """
    from app.services.settings_service import get_runtime_bool
    if not _es_aprobacion(paso) or not get_runtime_bool(db, "BPMN_SEGREGACION_DE_FUNCIONES", inst.organization_id,
                                                         default=False):
        return
    v = db.query(BPMNProcessVersion).filter(BPMNProcessVersion.process_id == inst.process_id,
                                            BPMNProcessVersion.version == inst.version).first()
    if v is not None and user.id in (v.created_by_user_id, v.published_by_user_id):
        from app.services.audit import audit_log
        audit_log(db, user, "SOD_BLOCKED", "bpmn_instance", inst.id, None,
                  new_values={"step_id": paso.id, "version": inst.version})
        db.commit()
        raise error(403, "bpm_segregacion_de_funciones")


def completar(db: Session, inst: BPMNInstance, paso_id: str, user, variables: Optional[dict] = None,
              flow_id: Optional[str] = None, flow_ids: Optional[list] = None,
              error_code: Optional[str] = None) -> BPMNInstance:
    paso = db.query(BPMNInstanceStep).filter(BPMNInstanceStep.id == paso_id,
                                             BPMNInstanceStep.instance_id == inst.id).first()
    if paso is None:
        raise error(404, "no_encontrado", detail="Paso no encontrado", que="paso")
    if inst.status != "running" or paso.status != "active" or not es_humano(paso):
        raise error(409, "bpm_paso_no_pendiente")
    if not puede_completar(paso, user, db):
        raise error(403, "bpm_paso_de_otro_rol", rol=paso.candidate_role or "-")
    exigir_segregacion(db, inst, paso, user)
    variables = validar_variables(db, inst.organization_id, variables)
    g = _grafo(db, inst)
    n = g.nodos.get(paso.element_id)
    if n is None:
        raise error(409, "bpm_paso_fuera_de_diagrama")
    corrida = _Corrida(db, inst, g)
    if error_code:
        # Quien confirma una tarea puede decir que fallo: lo captura su borde de error.
        if not any(b.error_code in (None, error_code) for b in g.bordes_de(n.id, "errorEventDefinition")):
            raise error(422, "bpm_error_sin_captura", codigo=error_code)
        variables = tipar_variables(esquema(_proceso_de(db, inst)), variables)
        if variables:
            inst.variables = json.dumps({**_variables(inst), **variables})
        _anotar(paso, user, {**variables, "error_code": error_code})
        corrida.lanzar_error(n.padre, error_code, desde=n.id)
        corrida.avanzar([])
        _auditar(db, user, "UPDATE", inst, None, {"step": paso.element_id, "error_code": error_code})
        db.commit()
        ejecutar_trabajos(db, instancia_id=inst.id)
        return inst
    if paso.wait_kind == ESPERA_DECISION:
        multiple = bool(_json(paso.result).get("multiple"))
        elegidas = [f for f in (flow_ids or ([flow_id] if flow_id else [])) if f]
        if not elegidas or any(f not in n.salidas for f in elegidas) or (len(elegidas) > 1 and not multiple):
            raise error(422, "bpm_elige_salida")
        salidas = list(dict.fromkeys(elegidas))
    else:
        salidas = None
    if n.formulario:
        variables = tipar_variables(n.formulario, variables, exigir=True, solo_declaradas=True)
    variables = tipar_variables(esquema(_proceso_de(db, inst)), variables)
    if variables:
        inst.variables = json.dumps({**_variables(inst), **variables})
    _anotar(paso, user, {**variables, **({"flow_ids": salidas} if salidas else {})})
    corrida.cancelar_bordes(n.id)
    if paso.wait_kind == ESPERA_DECISION:
        corrida.salir(n, salidas)
    else:
        corrida.salir(n)
    corrida.avanzar([])
    _auditar(db, user, "COMPLETE", inst, None, {"step": paso.element_id, "step_id": paso.id,
                                                **({"flow_ids": salidas} if salidas else {})})
    db.commit()
    ejecutar_trabajos(db, instancia_id=inst.id)
    return inst


def _anotar(paso: BPMNInstanceStep, user, aporte: dict) -> None:
    previo = _json(paso.result)
    paso.status = "completed"
    paso.completed_at = _ahora()
    paso.completed_by_user_id = getattr(user, "id", None)
    paso.result = json.dumps({**{k: v for k, v in previo.items() if k in ("automatic", "tipo", "approval")},
                              **aporte}, default=str)


def _proceso_de(db: Session, inst: BPMNInstance) -> Optional[BPMNProcess]:
    return db.query(BPMNProcess).filter(BPMNProcess.id == inst.process_id).first()


def cancelar(db: Session, inst: BPMNInstance, user=None) -> BPMNInstance:
    if inst.status not in ("running", "suspended"):
        raise error(409, "bpm_instancia_terminada")
    _cancelar_instancia(db, inst)
    _auditar(db, user, "CANCEL", inst, None, {"status": "cancelled"})
    _al_terminar(db, inst)
    db.commit()
    return inst


def suspender(db: Session, inst: BPMNInstance, user) -> BPMNInstance:
    """Para la instancia: nadie completa sus pasos y sus temporizadores esperan."""
    if inst.status != "running":
        raise error(409, "bpm_instancia_no_en_curso")
    inst.status, inst.suspended_at = "suspended", _ahora()
    _auditar(db, user, "SUSPEND", inst, None, {"status": "suspended"})
    db.commit()
    return inst


def reanudar(db: Session, inst: BPMNInstance, user) -> BPMNInstance:
    """Reanuda una instancia suspendida; lo vencido mientras tanto salta en la siguiente pasada."""
    if inst.status != "suspended":
        raise error(409, "bpm_instancia_no_suspendida")
    inst.status, inst.suspended_at = "running", None
    _auditar(db, user, "RESUME", inst, None, {"status": "running"})
    db.commit()
    ejecutar_trabajos(db, instancia_id=inst.id)
    return inst


def migrar(db: Session, inst: BPMNInstance, version: int, user) -> BPMNInstance:
    """Pasa una instancia en curso a otra version del mismo proceso.

    Solo si cada paso activo existe en la version destino con el mismo tipo y
    en el mismo ambito; si no, 409 con los elementos que lo impiden.
    """
    if inst.status not in ("running", "suspended"):
        raise error(409, "bpm_instancia_terminada")
    if version == inst.version:
        return inst
    destino = _Grafos(db).version(inst.process_id, version)
    if destino.problemas:
        raise error(422, "bpm_diagrama_no_ejecutable", problemas="; ".join(map(str, destino.problemas[:20])))
    origen = _grafo(db, inst)
    malos = []
    for p in _activos(db, inst):
        a, b = origen.nodos.get(p.element_id), destino.nodos.get(p.element_id)
        if b is None or a is None or a.tipo != b.tipo or a.padre != b.padre:
            malos.append(p.name or p.element_id)
    if malos:
        raise error(409, "bpm_migracion_incompatible", elementos=", ".join(malos[:20]))
    anterior = inst.version
    inst.version = version
    _auditar(db, user, "MIGRATE", inst, None, {"from_version": anterior, "to_version": version})
    db.commit()
    return inst


def reasignar(db: Session, inst: BPMNInstance, paso_id: str, user_id: Optional[str], actor) -> BPMNInstance:
    """Asigna (o libera, con None) un paso humano pendiente a una persona de la empresa."""
    paso = db.query(BPMNInstanceStep).filter(BPMNInstanceStep.id == paso_id,
                                             BPMNInstanceStep.instance_id == inst.id).first()
    if paso is None:
        raise error(404, "no_encontrado", detail="Paso no encontrado", que="paso")
    if inst.status not in ("running", "suspended") or paso.status != "active" or not es_humano(paso):
        raise error(409, "bpm_paso_no_pendiente")
    nuevo = None
    if user_id:
        nuevo = _Resolutor(db, inst.organization_id).usuario(user_id)
        if nuevo is None:
            raise error(404, "no_encontrado", detail="Usuario no encontrado", que="usuario")
    anterior = paso.assignee_user_id
    paso.assignee_user_id = nuevo
    _auditar(db, actor, "REASSIGN", inst, None, {"step_id": paso.id, "step": paso.element_id,
                                                 "from_user": anterior, "to_user": nuevo})
    if nuevo:
        _avisar_asignacion(db, nuevo, inst, paso)
    db.commit()
    return inst


def reintentar(db: Session, inst: BPMNInstance, paso_id: str, actor) -> BPMNInstance:
    """Un incidente (accion automatica que fallo tras sus reintentos) vuelve a la cola."""
    paso = db.query(BPMNInstanceStep).filter(BPMNInstanceStep.id == paso_id,
                                             BPMNInstanceStep.instance_id == inst.id).first()
    if paso is None or paso.status != "active" or paso.wait_kind != ESPERA_INCIDENTE:
        raise error(409, "bpm_paso_no_pendiente")
    paso.wait_kind, paso.attempts, paso.due_at = ESPERA_TRABAJO, 0, _ahora()
    _auditar(db, actor, "RETRY", inst, None, {"step_id": paso.id, "step": paso.element_id})
    db.commit()
    ejecutar_trabajos(db, instancia_id=inst.id)
    return inst


def correlacionar(db: Session, mensaje: str, user, *, instancia_id: Optional[str] = None,
                  business_key: Optional[str] = None, variables: Optional[dict] = None) -> list[str]:
    """Entrega un mensaje a las instancias que lo esperan (por instancia o por clave de negocio).

    Devuelve los ids de las instancias que lo recibieron; 404 si ninguna lo esperaba.
    """
    variables = validar_variables(db, getattr(user, "organization_id", None), variables)
    q = db.query(BPMNInstanceStep).join(BPMNInstance, BPMNInstance.id == BPMNInstanceStep.instance_id).filter(
        BPMNInstanceStep.status == "active", BPMNInstanceStep.wait_kind == ESPERA_MENSAJE,
        BPMNInstance.status == "running")
    q = _de_la_organizacion(q, BPMNInstance, user)
    if instancia_id:
        q = q.filter(BPMNInstance.id == instancia_id)
    elif business_key:
        q = q.filter(BPMNInstance.business_key == business_key)
    else:
        raise error(422, "bpm_mensaje_sin_destino")
    recibidas = []
    grafos = _Grafos(db)
    for paso in q.order_by(BPMNInstanceStep.created_at).all():
        if _json(paso.result).get("message") != mensaje or paso.status != "active":
            continue
        inst = db.query(BPMNInstance).filter(BPMNInstance.id == paso.instance_id).with_for_update().first()
        if inst is None or inst.status != "running":
            continue
        g = grafos.de(inst)
        n = g.nodos.get(paso.element_id)
        if n is None:
            continue
        variables_t = tipar_variables(esquema(_proceso_de(db, inst)), variables)
        if variables_t:
            inst.variables = json.dumps({**_variables(inst), **variables_t})
        corrida = _Corrida(db, inst, g)
        _anotar(paso, user, {**variables_t, "message": mensaje})
        if n.tipo == "boundaryEvent":
            host = g.nodos[n.adjunto]
            if n.interrumpe:
                corrida.interrumpir(host)
            corrida.salir(n)
        else:
            corrida.cancelar_bordes(n.id)
            corrida.salir(n)
        corrida.avanzar([])
        _auditar(db, user, "MESSAGE", inst, None, {"message": mensaje, "step": paso.element_id})
        recibidas.append(inst.id)
        db.commit()
        ejecutar_trabajos(db, instancia_id=inst.id)
    if not recibidas:
        raise error(404, "bpm_mensaje_sin_receptor", mensaje=mensaje)
    return recibidas


def _auditar(db: Session, user, accion: str, inst: BPMNInstance, nombre: Optional[str], valores: dict) -> None:
    from app.services.audit import audit_log
    audit_log(db, user, accion, "bpmn_instance", inst.id, nombre, new_values=valores)


# ── Trabajos: acciones automaticas, reintentos e incidentes ─────────────────

def _reintentos(db: Session, n: Optional[Nodo], org) -> int:
    from app.services.settings_service import get_runtime_int
    if n is not None and n.ext.get("retries"):
        try:
            return max(0, min(20, int(n.ext["retries"])))
        except ValueError:
            pass
    v = get_runtime_int(db, "BPMN_SERVICE_RETRIES", org)
    return 3 if v is None else max(0, v)


def ejecutar_trabajos(db: Session, instancia_id: Optional[str] = None, limite: int = 50) -> dict:
    """Ejecuta las acciones automaticas vencidas (cada una en su transaccion).

    Exito: el paso se completa con las variables que devuelve la accion y la
    instancia sigue. Fallo: se deshace lo de esa accion, se cuenta el intento y
    se programa el siguiente (1, 2, 4… minutos); agotados, si la tarea tiene un
    borde de error que lo captura (codigo `action_failed` o sin codigo) la
    ficha sale por el; si no, el paso queda como **incidente** (visible en la
    instancia y en las metricas; se reintenta a mano).
    """
    from app.services import bpmn_acciones

    hechos = fallos = 0
    for _ in range(limite):
        q = (db.query(BPMNInstanceStep).join(BPMNInstance, BPMNInstance.id == BPMNInstanceStep.instance_id)
             .filter(BPMNInstanceStep.status == "active",
                     BPMNInstanceStep.wait_kind.in_((ESPERA_TRABAJO, ESPERA_REINTENTO)),
                     BPMNInstanceStep.due_at <= _ahora(), BPMNInstance.status == "running"))
        if instancia_id:
            q = q.filter(BPMNInstance.id == instancia_id)
        paso = q.order_by(BPMNInstanceStep.due_at).first()
        if paso is None:
            break
        paso_id, inst_id = paso.id, paso.instance_id
        inst = db.query(BPMNInstance).filter(BPMNInstance.id == inst_id).first()
        g = _grafo(db, inst)
        n = g.nodos.get(paso.element_id)
        try:
            if n is None:
                raise RuntimeError("paso fuera del diagrama")
            salida = bpmn_acciones.ejecutar(db, inst, paso, n)
            if salida is bpmn_acciones.ESPERAR:
                db.commit()
                hechos += 1
                continue
            salida = salida or {}
            if salida:
                inst.variables = json.dumps({**_variables(inst), **salida}, default=str)
            _anotar(paso, None, {"automatic": True, "action": n.accion, **salida})
            corrida = _Corrida(db, inst, g)
            corrida.cancelar_bordes(n.id)
            corrida.salir(n)
            corrida.avanzar([])
            _auditar(db, None, "AUTOMATIC_STEP", inst, None, {"step": n.id, "action": n.accion})
            db.commit()
            hechos += 1
        except Exception as exc:   # noqa: BLE001 — cualquier fallo de la accion se cuenta y se reintenta
            db.rollback()
            fallos += 1
            logger.warning("BPMN: la accion de %s (instancia %s) fallo", paso_id, inst_id, exc_info=True)
            _anotar_fallo(db, paso_id, inst_id, exc)
    return {"jobs_done": hechos, "jobs_failed": fallos}


def _anotar_fallo(db: Session, paso_id: str, inst_id: str, exc: Exception) -> None:
    paso = db.query(BPMNInstanceStep).filter(BPMNInstanceStep.id == paso_id).first()
    inst = db.query(BPMNInstance).filter(BPMNInstance.id == inst_id).first()
    if paso is None or inst is None:
        return
    g = _grafo(db, inst)
    n = g.nodos.get(paso.element_id)
    paso.attempts = (paso.attempts or 0) + 1
    motivo = getattr(exc, "code", None) or type(exc).__name__
    detalle = str(getattr(exc, "detail", None) or exc)[:300]
    if paso.attempts <= _reintentos(db, n, inst.organization_id):
        paso.wait_kind = ESPERA_REINTENTO
        paso.due_at = _ahora() + timedelta(minutes=2 ** (paso.attempts - 1))
        paso.result = json.dumps({**_json(paso.result), "last_error": motivo, "detail": detalle})
    elif n is not None and any(b.error_code in (None, "action_failed") for b in g.bordes_de(n.id, "errorEventDefinition")):
        corrida = _Corrida(db, inst, g)
        _anotar(paso, None, {"automatic": True, "action": n.accion, "error": motivo, "detail": detalle})
        corrida.lanzar_error(n.padre, "action_failed", desde=n.id)
        corrida.avanzar([])
    else:
        paso.wait_kind = ESPERA_INCIDENTE
        paso.result = json.dumps({**_json(paso.result), "last_error": motivo, "detail": detalle})
        _auditar(db, None, "INCIDENT", inst, None, {"step": paso.element_id, "error": motivo})
    db.commit()


def aplicar_desde_bandeja(req, decision: str, actor, db: Session) -> None:
    """Decision final del motor de aprobaciones sobre un paso BPMN (`fuentes.aplicar`)."""
    paso = db.query(BPMNInstanceStep).filter(BPMNInstanceStep.id == req.entity_id).first()
    if paso is None or paso.status != "active" or paso.wait_kind != ESPERA_APROBACION:
        return
    inst = db.query(BPMNInstance).filter(BPMNInstance.id == paso.instance_id).first()
    if inst is None or inst.status != "running":
        return
    g = _grafo(db, inst)
    n = g.nodos.get(paso.element_id)
    if n is None:
        return
    var = (n.ext.get("resultVariable") or "aprobado").strip()
    aporte = {var: decision == "approved", "approval_status": decision}
    inst.variables = json.dumps({**_variables(inst), **aporte})
    _anotar(paso, actor, {**aporte, "approval_request_id": req.id})
    corrida = _Corrida(db, inst, g)
    corrida.cancelar_bordes(n.id)
    corrida.salir(n)
    corrida.avanzar([])
    _auditar(db, actor, "APPROVE" if decision == "approved" else "REJECT", inst, None,
             {"step": n.id, "approval_request_id": req.id})
    db.commit()
    ejecutar_trabajos(db, instancia_id=inst.id)


def comprobar_en_bandeja(req, actor, db: Session) -> None:
    """Antes de anotar la decision del motor de aprobaciones: segregacion de funciones BPM."""
    if actor is None:
        return
    paso = db.query(BPMNInstanceStep).filter(BPMNInstanceStep.id == req.entity_id).first()
    if paso is None:
        return
    inst = db.query(BPMNInstance).filter(BPMNInstance.id == paso.instance_id).first()
    if inst is not None:
        exigir_segregacion(db, inst, paso, actor)


# ── Tarea periodica ─────────────────────────────────────────────────────────

def vencer_temporizadores(db: Session) -> dict:
    """La pasada del worker (cada minuto): temporizadores, acciones en cola y plazos de tareas."""
    from app.services.entrada_service import organizacion_desactivada
    from app.services.service_desk.ticket_events import como_organizacion
    vencidos = (db.query(BPMNInstanceStep)
                .join(BPMNInstance, BPMNInstance.id == BPMNInstanceStep.instance_id)
                .options(contains_eager(BPMNInstanceStep.instance))
                .filter(BPMNInstanceStep.status == "active",
                        (BPMNInstanceStep.wait_kind == ESPERA_TEMPORIZADOR)
                        | (BPMNInstanceStep.wait_kind.is_(None)
                           & (BPMNInstanceStep.element_type == "intermediateCatchEvent")),
                        BPMNInstanceStep.due_at <= _ahora(),
                        BPMNInstance.status == "running")
                .all())
    grafos = _Grafos(db)
    n = fallos = 0
    for paso in vencidos:
        inst = paso.instance
        # Segunda auditoría 2026-11 (#10): organización desactivada → se salta;
        # el temporizador sigue vencido y salta si se reactiva.
        if organizacion_desactivada(db, inst.organization_id):
            continue
        with como_organizacion(db, inst.organization_id):
            if inst.status != "running" or paso.status != "active":
                continue   # otro temporizador de la misma instancia la termino
            # M75 (auditoría 22-11-2026): un fallo en una instancia se deshace
            # y se anota; ya no deja la sesión abortada para las demás.
            try:
                g = grafos.de(inst)
                nodo = g.nodos[paso.element_id]
                corrida = _Corrida(db, inst, g)
                _cerrar_paso(paso, "completed")
                if nodo.tipo == "boundaryEvent":
                    if nodo.interrumpe:
                        corrida.interrumpir(g.nodos[nodo.adjunto])
                    corrida.salir(nodo)
                else:
                    corrida.salir(nodo)
                corrida.avanzar([])
                db.commit()
                n += 1
            except Exception:
                db.rollback()
                fallos += 1
                logger.exception("BPMN: temporizador %s de la instancia %s", paso.id, inst.id)
    trabajos = {"jobs_done": 0, "jobs_failed": 0}
    orgs = {o for (o,) in db.query(BPMNInstance.organization_id).join(
        BPMNInstanceStep, BPMNInstanceStep.instance_id == BPMNInstance.id).filter(
        BPMNInstanceStep.status == "active", BPMNInstanceStep.wait_kind.in_((ESPERA_TRABAJO, ESPERA_REINTENTO)),
        BPMNInstanceStep.due_at <= _ahora(), BPMNInstance.status == "running").distinct().all()}
    for org in orgs:
        if organizacion_desactivada(db, org):
            continue
        with como_organizacion(db, org):
            r = ejecutar_trabajos(db)
            trabajos = {k: trabajos[k] + r[k] for k in trabajos}
    escalados = escalar_plazos(db)
    return {"timers_fired": n, "failed": fallos, **trabajos, "escalated": escalados}


def escalar_plazos(db: Session) -> int:
    """Tareas humanas con el plazo vencido: se marcan, se avisa y queda en la auditoria (una vez)."""
    from app.services.entrada_service import organizacion_desactivada
    from app.services.service_desk.ticket_events import como_organizacion
    vencidas = (db.query(BPMNInstanceStep).join(BPMNInstance, BPMNInstance.id == BPMNInstanceStep.instance_id)
                .options(contains_eager(BPMNInstanceStep.instance))
                .filter(BPMNInstanceStep.status == "active", BPMNInstanceStep.sla_due_at <= _ahora(),
                        BPMNInstanceStep.escalated_at.is_(None), BPMNInstance.status == "running")
                .limit(500).all())
    n = 0
    for paso in vencidas:
        inst = paso.instance
        if organizacion_desactivada(db, inst.organization_id):
            continue
        with como_organizacion(db, inst.organization_id):
            try:
                paso.escalated_at = _ahora()
                destinatarios = {u for u in (paso.assignee_user_id, inst.started_by_user_id) if u}
                from app.services.notifications import notify_user
                for uid in destinatarios:
                    try:
                        nombre = paso.name or paso.element_id
                        notify_user(db, uid, "task_overdue", f"Tarea de proceso vencida: {nombre}", None,
                                    "bpmn_instance", inst.id, "/inbox?tab=procesos",
                                    aviso={"titulo": "bpm.tarea_vencida", "params": {"tarea": nombre}})
                    except Exception:   # noqa: BLE001 — el aviso es accesorio
                        logger.warning("BPMN: aviso de plazo %s", paso.id, exc_info=True)
                _auditar(db, None, "ESCALATE", inst, None, {"step": paso.element_id, "step_id": paso.id,
                                                            "sla_due_at": str(paso.sla_due_at)})
                db.commit()
                n += 1
            except Exception:
                db.rollback()
                logger.exception("BPMN: escalado del paso %s", paso.id)
    return n


# ── Simulacion ──────────────────────────────────────────────────────────────

def simular(xml: str, variables: Optional[dict] = None, decisiones: Optional[dict] = None,
            max_pasos: int = 500) -> dict:
    """Recorre el diagrama en memoria, sin tocar la base: para probar antes de publicar.

    Las tareas humanas se dan por completadas, los temporizadores y mensajes
    llegan al momento, las acciones automaticas no se ejecutan (se anotan), las
    llamadas a otros procesos se dan por terminadas y los bordes no saltan.
    `decisiones`: {id de compuerta: flow_id o [flow_ids]}; sin ella, la salida
    por defecto o la primera. Devuelve el recorrido, si llega al final y donde
    se queda colgada (uniones que esperan una ficha que no llegara).
    """
    g = leer(xml)
    salida = {"problems": [p.como_dict() for p in g.problemas], "warnings": [p.como_dict() for p in g.avisos],
              "path": [], "completed": False, "stuck": [], "actions": [], "error": None}
    if g.problemas:
        return salida
    variables = dict(variables or {})
    decisiones = decisiones or {}
    cola: list[tuple[str, Optional[str]]] = [(g.inicio, None)]
    uniones: dict[str, set] = {}
    pasos = 0

    def anotar(n: Nodo) -> None:
        salida["path"].append({"element_id": n.id, "name": n.nombre, "type": n.tipo})

    def salir(n: Nodo, flujos=None) -> None:
        for f in (n.salidas if flujos is None else flujos):
            cola.append((g.flujos[f].destino, f))

    def elegir(n: Nodo) -> None:
        if len(n.salidas) <= 1:
            salir(n)
            return
        if n.decision or n.id in decisiones:
            pedido = decisiones.get(n.id)
            elegidas = [f for f in (pedido if isinstance(pedido, list) else [pedido]) if f in n.salidas]
            elegidas = elegidas or [n.defecto or n.salidas[0]]
        else:
            elegidas = [f for f in n.salidas if f != n.defecto and g.flujos[f].condicion
                        and cumple(g.flujos[f].condicion, variables)]
            elegidas = elegidas or ([n.defecto] if n.defecto else [])
        if n.tipo == "exclusiveGateway":
            elegidas = elegidas[:1]
        if not elegidas:
            salida["error"] = "no_route"
            return
        salir(n, elegidas)

    def vivo_dentro(ambito: str) -> bool:
        return any(g.dentro(c, ambito) for c, _ in cola) or any(g.dentro(u, ambito) for u in uniones)

    while True:
        while cola and salida["error"] is None:
            pasos += 1
            if pasos > max_pasos:
                salida["error"] = "loop_limit"
                break
            nid, flujo = cola.pop(0)
            n = g.nodos[nid]
            if n.tipo in ("parallelGateway", "inclusiveGateway") and len(n.entradas) > 1:
                uniones.setdefault(n.id, set()).add(flujo)
                if n.tipo == "parallelGateway" and set(n.entradas) <= uniones[n.id]:
                    uniones.pop(n.id)
                    anotar(n)
                    salir(n)
                elif n.tipo == "inclusiveGateway" and not any(c == n.id or g.alcanza(c, n.id) for c, _ in cola):
                    uniones.pop(n.id)
                    anotar(n)
                    elegir(n)
                continue
            anotar(n)
            if n.tipo == "endEvent":
                if n.error_code:
                    salida["error"] = f"bpmn_error:{n.error_code}"
                elif n.terminar and n.padre is None:
                    cola.clear()
                    uniones.clear()
                elif n.terminar:
                    cola[:] = [(c, f) for c, f in cola if not g.dentro(c, n.padre)]
                    for u in [u for u in uniones if g.dentro(u, n.padre)]:
                        uniones.pop(u)
                if n.padre and salida["error"] is None and not vivo_dentro(n.padre):
                    salir(g.nodos[n.padre])
                continue
            if n.tipo == "subProcess":
                cola.append((n.inicio_interno, None))
                continue
            if n.tipo in ("exclusiveGateway", "inclusiveGateway"):
                elegir(n)
                continue
            if n.tipo in AUTOMATICOS and n.accion:
                salida["actions"].append({"element_id": n.id, "action": n.accion})
            salir(n)
        # Una union inclusiva espera mientras quede algo que pueda llegar; al vaciarse la cola, pasa.
        inclusivas = [u for u in uniones if g.nodos[u].tipo == "inclusiveGateway"]
        if not inclusivas or salida["error"] is not None:
            break
        anotar(g.nodos[inclusivas[0]])
        uniones.pop(inclusivas[0])
        elegir(g.nodos[inclusivas[0]])
    for uid, llegados in uniones.items():
        u = g.nodos[uid]
        salida["stuck"].append({"element_id": uid, "name": u.nombre, "arrived": len(llegados),
                                "expected": len(u.entradas)})
    salida["completed"] = not salida["stuck"] and salida["error"] is None
    return salida


# ── Serializacion ───────────────────────────────────────────────────────────

def serializar(inst: BPMNInstance, con_pasos: bool = True, grafos: Optional[_Grafos] = None,
               nombres: Optional[dict] = None) -> dict:
    out = {
        "id": inst.id, "process_id": inst.process_id, "version": inst.version, "status": inst.status,
        "variables": _variables(inst), "error": inst.error, "error_code": inst.error_code,
        "error_params": json.loads(inst.error_params) if inst.error_params else None,
        "started_by_user_id": inst.started_by_user_id,
        "started_at": inst.started_at.isoformat() if inst.started_at else None,
        "ended_at": inst.ended_at.isoformat() if inst.ended_at else None,
        "business_key": inst.business_key, "parent_instance_id": inst.parent_instance_id,
        "suspended_at": inst.suspended_at.isoformat() if inst.suspended_at else None,
        "active_steps": [s.name or s.element_id for s in inst.steps if s.status == "active"],
        "incidents": sum(1 for s in inst.steps if s.status == "active" and s.wait_kind == ESPERA_INCIDENTE),
    }
    if con_pasos:
        out["steps"] = [serializar_paso(s, grafos, nombres) for s in inst.steps]
    return out


def serializar_paso(s: BPMNInstanceStep, grafos: Optional[_Grafos] = None, nombres: Optional[dict] = None) -> dict:
    nombres = nombres or {}
    out = {
        "id": s.id, "instance_id": s.instance_id, "element_id": s.element_id, "element_type": s.element_type,
        "name": s.name, "status": s.status, "candidate_role": s.candidate_role, "wait_kind": s.wait_kind,
        "candidate_groups": candidatos(s) if s.candidate_groups else [],
        "assignee_user_id": s.assignee_user_id, "assignee_name": nombres.get(s.assignee_user_id),
        "due_at": s.due_at.isoformat() if s.due_at else None,
        "sla_due_at": s.sla_due_at.isoformat() if s.sla_due_at else None,
        "escalated": s.escalated_at is not None,
        "overdue": bool(s.status == "active" and s.sla_due_at and _aware(s.sla_due_at) <= _ahora()),
        "attempts": s.attempts or 0,
        "completed_by_user_id": s.completed_by_user_id, "completed_by_name": nombres.get(s.completed_by_user_id),
        "result": json.loads(s.result) if s.result else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        "human": es_humano(s),
    }
    if s.status == "active" and grafos is not None and es_humano(s):
        try:
            g = grafos.de(s.instance)
            n = g.nodos.get(s.element_id)
            if s.wait_kind == ESPERA_DECISION:
                out["options"] = g.opciones(s.element_id)
                out["multiple"] = bool(_json(s.result).get("multiple"))
            if n is not None:
                out["form"] = n.formulario or []
                out["approval"] = n.es_aprobacion or bool(_json(s.result).get("approval"))
                out["error_codes"] = [b.error_code or "" for b in g.bordes_de(n.id, "errorEventDefinition")]
        except Exception:   # noqa: BLE001 — sin diagrama el paso se pinta igual
            logger.debug("BPMN: sin grafo para el paso %s", s.id, exc_info=True)
    return out


# ── Consultas para la API (la capa API no consulta la base) ─────────────────

def _de_la_organizacion(q, modelo, user):
    return q if getattr(user, "is_superadmin", False) else q.filter(modelo.organization_id == user.organization_id)


def proceso_para_arrancar(db: Session, process_id: str, user) -> Optional[BPMNProcess]:
    return _de_la_organizacion(db.query(BPMNProcess).filter(BPMNProcess.id == process_id,
                                                            BPMNProcess.is_active.is_(True)), BPMNProcess, user).first()


def instancia(db: Session, instance_id: str, user, bloquear: bool = False) -> BPMNInstance:
    """La instancia, si es de la organizacion del usuario.

    `bloquear`: `SELECT … FOR UPDATE` para completar y cancelar. Revision BPM
    2026-11-16: dos personas completando a la vez las dos ramas de una union
    paralela leian las dos `arrived = 1` y la union no se cerraba nunca.
    """
    q = _de_la_organizacion(db.query(BPMNInstance).filter(BPMNInstance.id == instance_id), BPMNInstance, user)
    if bloquear:
        q = q.with_for_update()
    inst = q.first()
    if inst is None:
        raise error(404, "no_encontrado", detail="Instancia no encontrada", que="instancia")
    return inst


def _personas(db: Session, ids: Iterable) -> dict:
    from app.models.user import User
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {i: (n or e) for i, n, e in db.query(User.id, User.full_name, User.email).filter(User.id.in_(ids)).all()}


def detalle(db: Session, inst: BPMNInstance) -> dict:
    """La instancia con su historial (y quien hizo cada paso) y las opciones de lo pendiente."""
    nombres = _personas(db, [s.completed_by_user_id for s in inst.steps] + [s.assignee_user_id for s in inst.steps]
                        + [inst.started_by_user_id])
    out = serializar(inst, grafos=_Grafos(db), nombres=nombres)
    out["started_by_name"] = nombres.get(inst.started_by_user_id)
    out["process_name"] = _nombres(db, [inst.process_id]).get(inst.process_id)
    out["children"] = [{"id": i, "status": st} for i, st in db.query(BPMNInstance.id, BPMNInstance.status)
                       .filter(BPMNInstance.parent_instance_id == inst.id).all()]
    return out


def _nombres(db: Session, ids) -> dict:
    return dict(db.query(BPMNProcess.id, BPMNProcess.name).filter(BPMNProcess.id.in_(set(ids) or {""})).all())


def listar(db: Session, user, status: Optional[str], process_id: Optional[str], limite: int,
           q: Optional[str] = None) -> list[dict]:
    # selectinload: `active_steps` lee los pasos; sin esto, una consulta por fila.
    consulta = _de_la_organizacion(db.query(BPMNInstance).options(selectinload(BPMNInstance.steps)), BPMNInstance, user)
    if status:
        consulta = consulta.filter(BPMNInstance.status == status)
    if process_id:
        consulta = consulta.filter(BPMNInstance.process_id == process_id)
    if q:
        patron = f"%{q.strip()[:100]}%"
        ids = [i for (i,) in db.query(BPMNProcess.id).filter(BPMNProcess.name.ilike(patron)).all()]
        consulta = consulta.filter(BPMNInstance.business_key.ilike(patron) | BPMNInstance.process_id.in_(ids or [""])
                                   | (BPMNInstance.id == q.strip()))
    filas = consulta.order_by(BPMNInstance.started_at.desc()).limit(limite).all()
    nombres = _nombres(db, {i.process_id for i in filas})
    return [{**serializar(i, con_pasos=False), "process_name": nombres.get(i.process_id)} for i in filas]


def bandeja(db: Session, user) -> list[dict]:
    from sqlalchemy import or_

    pasos = _de_la_organizacion(
        db.query(BPMNInstanceStep).join(BPMNInstance, BPMNInstance.id == BPMNInstanceStep.instance_id)
        .options(contains_eager(BPMNInstanceStep.instance))
        .filter(BPMNInstanceStep.status == "active", BPMNInstance.status == "running",
                or_(BPMNInstanceStep.wait_kind.in_(ESPERAS_HUMANAS),
                    (BPMNInstanceStep.wait_kind.is_(None)) & BPMNInstanceStep.element_type.in_(HUMANOS))),
        BPMNInstanceStep, user).order_by(BPMNInstanceStep.created_at).all()
    yo = perfil(db, user)
    mios = [p for p in pasos if puede_completar(p, yo)]
    nombres = _nombres(db, {p.instance.process_id for p in mios})
    personas = _personas(db, [p.assignee_user_id for p in mios])
    grafos = _Grafos(db)
    return [{**serializar_paso(p, grafos, personas), "process_id": p.instance.process_id,
             "process_name": nombres.get(p.instance.process_id), "business_key": p.instance.business_key,
             "variables": _variables(p.instance)} for p in mios]
