"""Motor de ejecucion de los procesos BPMN guardados en /bpm.

Auditoria 2026-11: /bpm era un catalogo y un editor; nada de un diagrama se
ejecutaba. Este motor recorre el XML de la version publicada (o la ultima si
no hay ninguna publicada) con fichas, y guarda cada elemento que atraviesa
como un paso de la instancia (`bpmn_instance_steps`): eso es tambien su
historial.

Elementos que sabe ejecutar:

- **startEvent**: el de inicio (si hay varios, el que no tiene definicion de evento).
- **task, userTask, manualTask**: paso humano. Espera a que alguien lo complete
  (bandeja de /bpm y pestaña «Procesos» de /inbox). Si la tarea esta en una
  calle (lane) cuyo nombre es un rol base (admin, pm, team_lead, hr, employee,
  o su nombre en la pantalla en es/en/zh), solo ese rol (o un admin) puede
  completarlo; si no, cualquiera de la organizacion. Al completarlo se pueden
  aportar variables.
- **serviceTask, scriptTask, sendTask, businessRuleTask**: se anotan como hechos
  y la ficha sigue. **No ejecutan nada**: no hay a que enlazarlos todavia.
- **exclusiveGateway**: la primera salida cuya condicion se cumple; si ninguna,
  la de por defecto; si no hay, la instancia falla con el motivo.
  Condiciones: `variable op valor` (==, !=, >, <, >=, <=), unidas por `and`/`or`
  (o `&&`/`||`), con `${…}` opcional. Lo que no se puede evaluar no se cumple.
  Revision BPM 2026-11-16: si **ninguna** salida lleva condicion, la compuerta
  es una **decision manual**: espera en la bandeja (con el rol de su calle) y
  quien la completa elige la salida (`flow_id`). El editor de /bpm no permite
  escribir condiciones y todo el catalogo usa compuertas con salidas
  etiquetadas sin condicion: antes cualquier instancia fallaba al llegar a una.
- **parallelGateway**: con varias entradas espera a todas (union); con varias
  salidas las sigue todas.
- **intermediateCatchEvent** con temporizador `timeDuration` (ISO 8601, p. ej.
  PT2H, P1D) o `timeDate`: espera; lo despierta la tarea periodica.
- **intermediateThrowEvent** sin definicion: pasa.
- **endEvent**: consume la ficha; con `terminateEventDefinition` termina la
  instancia entera. La instancia acaba cuando no queda nada pendiente.

Cualquier otro elemento (subprocesos, eventos de borde, compuertas inclusivas,
mensajes, senales, errores, compensacion…) hace que el arranque se rechace con
la lista de lo que no se soporta: mejor no arrancar que arrancar y quedarse a
medias. `validar()` devuelve esos problemas con un codigo por problema para que
la interfaz los traduzca (`bpm.problema_<code>`); el fallo en ejecucion queda
igual, con `error_code` y `error_params` (`bpm.error_<code>`).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from defusedxml.ElementTree import fromstring as _xml_seguro
from sqlalchemy.orm import Session, contains_eager, selectinload

from app.models.bpmn_process import (BPMNInstance, BPMNInstanceStep, BPMNProcess, BPMNProcessStatus,
                                     BPMNProcessVersion)
from app.core.errores import ErrorDeDominio

_NS = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"

HUMANOS = {"task", "userTask", "manualTask"}
AUTOMATICOS = {"serviceTask", "scriptTask", "sendTask", "businessRuleTask"}
_SOPORTADOS = HUMANOS | AUTOMATICOS | {"startEvent", "endEvent", "exclusiveGateway", "parallelGateway",
                                       "intermediateCatchEvent", "intermediateThrowEvent"}

#: Por que espera un paso (`BPMNInstanceStep.wait_kind`). Los dos primeros los
#: completa una persona desde la bandeja.
ESPERA_TAREA, ESPERA_DECISION, ESPERA_TEMPORIZADOR, ESPERA_UNION = "task", "decision", "timer", "join"
ESPERAS_HUMANAS = {ESPERA_TAREA, ESPERA_DECISION}

#: Estados de una instancia (la API valida el filtro contra esta lista).
ESTADOS_DE_INSTANCIA = ("running", "completed", "cancelled", "failed")

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


def rol_de_calle(nombre: Optional[str]) -> Optional[str]:
    """El rol que exige una calle por su nombre, o None si no es un rol."""
    from app.models.user import UserRole

    clave = (nombre or "").strip().lower()
    if not clave:
        return None
    for rol in UserRole:
        if rol.value not in _ALIAS_DE_ROL:
            continue   # subcontractor: no entra en la bandeja (`require_internal_user`)
        if clave == rol.value or clave in _ALIAS_DE_ROL[rol.value]:
            return rol.value
    return None


@dataclass
class Nodo:
    id: str
    tipo: str
    nombre: Optional[str]
    entradas: list = field(default_factory=list)
    salidas: list = field(default_factory=list)
    defecto: Optional[str] = None
    rol: Optional[str] = None
    terminar: bool = False
    temporizador: Optional[tuple] = None    # ("duration"|"date", texto)
    definiciones: list = field(default_factory=list)
    decision: bool = False                  # exclusiveGateway sin condiciones: elige una persona


@dataclass
class Flujo:
    id: str
    origen: str
    destino: str
    condicion: Optional[str]
    nombre: Optional[str] = None


@dataclass
class Problema:
    """Lo que impide ejecutar un diagrama.

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


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _etiqueta(n: Nodo) -> str:
    return n.nombre or n.id


def leer(xml: str) -> Grafo:
    """El grafo ejecutable del diagrama y lo que impide ejecutarlo.

    Revision BPM 2026-11-16: se parsea con `defusedxml` (el XML lo sube el
    usuario: sin entidades externas ni expansiones) y cada problema lleva un
    codigo traducible.
    """
    try:
        raiz = _xml_seguro(xml)
    except Exception as exc:   # ParseError y los rechazos de defusedxml (DTD, entidades)
        return Grafo({}, {}, None, [Problema("invalid_xml", f"XML no valido: {exc}", extra=str(exc)[:200])])
    procesos = [p for p in raiz.iter(f"{_NS}process")]
    con_inicio = [p for p in procesos if p.find(f"{_NS}startEvent") is not None]
    if not con_inicio:
        return Grafo({}, {}, None, [Problema("no_start", "El diagrama no tiene evento de inicio")])
    if len(con_inicio) > 1:
        return Grafo({}, {}, None, [Problema("multiple_pools",
                                             "Hay varios procesos (piscinas) con inicio: no se soporta")])
    proceso = con_inicio[0]

    roles = {}
    for calle in proceso.iter(f"{_NS}lane"):
        rol = rol_de_calle(calle.get("name"))
        for ref in calle.findall(f"{_NS}flowNodeRef"):
            if rol and ref.text:
                roles[ref.text.strip()] = rol

    nodos, flujos, problemas = {}, {}, []
    for hijo in proceso:
        tipo = _local(hijo.tag)
        if tipo in ("laneSet", "documentation", "extensionElements", "textAnnotation", "association",
                    "dataObject", "dataObjectReference", "dataStoreReference", "group"):
            continue
        if tipo == "sequenceFlow":
            cond = hijo.find(f"{_NS}conditionExpression")
            flujos[hijo.get("id")] = Flujo(hijo.get("id"), hijo.get("sourceRef"), hijo.get("targetRef"),
                                          (cond.text or "").strip() if cond is not None and cond.text else None,
                                          hijo.get("name"))
            continue
        defs = [_local(d.tag) for d in hijo if _local(d.tag).endswith("EventDefinition")]
        n = Nodo(hijo.get("id"), tipo, hijo.get("name"), defecto=hijo.get("default"),
                 rol=roles.get(hijo.get("id")), definiciones=defs)
        if tipo not in _SOPORTADOS:
            problemas.append(Problema("unsupported_element", f"{tipo} «{_etiqueta(n)}»", _etiqueta(n), tipo))
        elif tipo == "endEvent":
            n.terminar = "terminateEventDefinition" in defs
            otras = [d for d in defs if d != "terminateEventDefinition"]
            if otras:
                problemas.append(Problema("end_with_definition",
                                          f"endEvent con {', '.join(defs)} «{_etiqueta(n)}»",
                                          _etiqueta(n), ", ".join(otras)))
        elif tipo == "intermediateCatchEvent":
            timer = hijo.find(f"{_NS}timerEventDefinition")
            if timer is None or defs != ["timerEventDefinition"]:
                problemas.append(Problema("catch_without_timer",
                                          f"intermediateCatchEvent sin temporizador «{_etiqueta(n)}»",
                                          _etiqueta(n)))
            else:
                dur, fecha = timer.find(f"{_NS}timeDuration"), timer.find(f"{_NS}timeDate")
                if dur is not None and dur.text and _duracion(dur.text.strip()) is not None:
                    n.temporizador = ("duration", dur.text.strip())
                elif fecha is not None and fecha.text and _fecha(fecha.text.strip()) is not None:
                    n.temporizador = ("date", fecha.text.strip())
                else:
                    problemas.append(Problema("invalid_timer",
                                              f"temporizador sin duración ni fecha válidas «{_etiqueta(n)}»",
                                              _etiqueta(n)))
        elif tipo == "intermediateThrowEvent" and defs:
            problemas.append(Problema("throw_with_definition",
                                      f"intermediateThrowEvent con {', '.join(defs)} «{_etiqueta(n)}»",
                                      _etiqueta(n), ", ".join(defs)))
        nodos[n.id] = n
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
        if n.tipo == "exclusiveGateway" and len(n.salidas) > 1:
            n.decision = not any(flujos[f].condicion for f in n.salidas)
        if n.defecto and n.defecto not in n.salidas:
            problemas.append(Problema("bad_default", f"la salida por defecto de «{_etiqueta(n)}» no sale de él",
                                      _etiqueta(n)))

    inicios = [n for n in nodos.values() if n.tipo == "startEvent"]
    simples = [n for n in inicios if not n.definiciones]
    inicio = (simples or inicios)[0].id if inicios else None
    for n in nodos.values():
        if n.tipo != "endEvent" and not n.salidas and n.tipo in _SOPORTADOS:
            problemas.append(Problema("no_outgoing", f"«{_etiqueta(n)}» no tiene salida", _etiqueta(n)))
    return Grafo(nodos, flujos, inicio, problemas)


def validar(xml: str) -> dict:
    """¿Se puede ejecutar este diagrama? Con los problemas, cada uno con su codigo."""
    g = leer(xml)
    return {"executable": not g.problemas, "problems": [p.como_dict() for p in g.problemas]}


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
    """[[(var, op, valor)]] (or de ands) o None si no se puede leer."""
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
    m = _DURACION.match(texto)
    if not m or not any(m.groups()):
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return timedelta(days=d, hours=h, minutes=mi, seconds=s)


def _fecha(texto: str) -> Optional[datetime]:
    try:
        f = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    return f if f.tzinfo else f.replace(tzinfo=timezone.utc)


# ── Variables ───────────────────────────────────────────────────────────────

def validar_variables(db: Session, org, variables: Optional[dict]) -> dict:
    """Las variables que llegan de la API, comprobadas.

    Revision BPM 2026-11-16: se guardaban tal cual. Un nombre que no es un
    identificador nunca lo puede leer una condicion, y sin tope de tamaño una
    peticion metia megas en la fila de la instancia.
    """
    from app.services.settings_service import get_runtime_int

    variables = variables or {}
    malos = [k for k in variables if not isinstance(k, str) or not _NOMBRE_DE_VARIABLE.match(k)]
    if malos:
        raise ErrorDeDominio(422, "Nombres de variable no válidos (letras, números, _ y .; empiezan por letra o _): "
                                  + ", ".join(map(str, malos[:10])))
    tope = get_runtime_int(db, "BPMN_MAX_VARIABLES_BYTES", org)
    tamano = len(json.dumps(variables, default=str).encode("utf8"))
    if tope and tamano > tope:
        raise ErrorDeDominio(413, f"Las variables ocupan {tamano} bytes; el máximo es {tope}")
    return variables


# ── Ejecucion ───────────────────────────────────────────────────────────────

def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def version_ejecutable(db: Session, proc: BPMNProcess) -> BPMNProcessVersion:
    """La version que se ejecuta: la publicada; si no hay ninguna, la ultima."""
    q = db.query(BPMNProcessVersion).filter(BPMNProcessVersion.process_id == proc.id)
    v = q.filter(BPMNProcessVersion.is_published.is_(True)).order_by(BPMNProcessVersion.version.desc()).first() \
        or q.order_by(BPMNProcessVersion.version.desc()).first()
    if v is None:
        raise ErrorDeDominio(422, "El proceso no tiene ningún diagrama guardado")
    return v


class _Grafos:
    """Grafos por (proceso, version), leidos una sola vez por peticion."""

    def __init__(self, db: Session):
        self.db = db
        self._cache: dict[tuple[str, int], Grafo] = {}

    def de(self, inst: BPMNInstance) -> Grafo:
        clave = (inst.process_id, inst.version)
        if clave not in self._cache:
            v = self.db.query(BPMNProcessVersion).filter(BPMNProcessVersion.process_id == inst.process_id,
                                                         BPMNProcessVersion.version == inst.version).first()
            if v is None:
                raise ErrorDeDominio(409, "La versión del diagrama de esta instancia ya no existe")
            self._cache[clave] = leer(v.bpmn_xml)
        return self._cache[clave]


def _grafo(db: Session, inst: BPMNInstance) -> Grafo:
    return _Grafos(db).de(inst)


def _variables(inst: BPMNInstance) -> dict:
    return json.loads(inst.variables or "{}")


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


def _fallar(inst: BPMNInstance, codigo: str, motivo: str, **params) -> None:
    inst.status = "failed"
    inst.error = motivo[:500]
    inst.error_code = codigo
    inst.error_params = json.dumps(params, default=str) if params else None
    inst.ended_at = _ahora()


def _avanzar(db: Session, inst: BPMNInstance, g: Grafo, entradas: list[tuple[str, Optional[str]]]) -> None:
    """Entra en cada (nodo, flujo por el que llega) y sigue hasta que todo espera."""
    pendientes = list(entradas)
    limite = _limite(db, inst.organization_id)
    vueltas = 0
    while pendientes and inst.status == "running":
        vueltas += 1
        if vueltas > limite:
            _fallar(inst, "loop_limit", f"Más de {limite} pasos automáticos seguidos: ¿un bucle sin espera?",
                    limit=limite)
            break
        nodo_id, _flujo = pendientes.pop(0)
        n = g.nodos[nodo_id]
        siguientes = [g.flujos[f].destino for f in n.salidas]
        if n.tipo in HUMANOS:
            _paso(db, inst, n, "active", candidate_role=n.rol, wait_kind=ESPERA_TAREA)
        elif n.tipo == "intermediateCatchEvent":
            clase, texto = n.temporizador
            vence = _ahora() + _duracion(texto) if clase == "duration" else _fecha(texto)
            _paso(db, inst, n, "active", due_at=vence, wait_kind=ESPERA_TEMPORIZADOR)
        elif n.tipo == "endEvent":
            _paso(db, inst, n, "completed")
            if n.terminar:
                for p in db.query(BPMNInstanceStep).filter(BPMNInstanceStep.instance_id == inst.id,
                                                           BPMNInstanceStep.status == "active"):
                    p.status = "cancelled"
                    p.completed_at = _ahora()
                pendientes.clear()
                inst.status = "completed"
                inst.ended_at = _ahora()
        elif n.tipo == "exclusiveGateway":
            if len(n.salidas) <= 1:
                _paso(db, inst, n, "completed")
                pendientes += [(d, None) for d in siguientes]
                continue
            if n.decision:
                _paso(db, inst, n, "active", candidate_role=n.rol, wait_kind=ESPERA_DECISION)
                continue
            _paso(db, inst, n, "completed")
            variables = _variables(inst)
            elegido = next((f for f in n.salidas if f != n.defecto and g.flujos[f].condicion
                            and cumple(g.flujos[f].condicion, variables)), None) or n.defecto
            if elegido is None:
                _fallar(inst, "no_route",
                        f"Ninguna condición de «{_etiqueta(n)}» se cumple y no hay salida por defecto",
                        element=_etiqueta(n))
                break
            pendientes.append((g.flujos[elegido].destino, elegido))
        elif n.tipo == "parallelGateway" and len(n.entradas) > 1:
            db.flush()
            union = db.query(BPMNInstanceStep).filter(
                BPMNInstanceStep.instance_id == inst.id, BPMNInstanceStep.element_id == n.id,
                BPMNInstanceStep.status == "active").first()
            if union is None:
                union = _paso(db, inst, n, "active", arrived=1, wait_kind=ESPERA_UNION)
            else:
                union.arrived += 1
            if union.arrived >= len(n.entradas):
                union.status = "completed"
                union.completed_at = _ahora()
                pendientes += [(d, None) for d in siguientes]
        else:
            # startEvent, parallelGateway de reparto, automaticos, throw sin definicion
            _paso(db, inst, n, "completed", result=json.dumps({"automatic": True}) if n.tipo in AUTOMATICOS else None)
            pendientes += [(d, None) for d in siguientes]
    db.flush()
    if inst.status == "running" and not db.query(BPMNInstanceStep.id).filter(
            BPMNInstanceStep.instance_id == inst.id, BPMNInstanceStep.status == "active").first():
        inst.status = "completed"
        inst.ended_at = _ahora()


def iniciar(db: Session, proc: BPMNProcess, user, variables: Optional[dict] = None) -> BPMNInstance:
    if proc.status == BPMNProcessStatus.archived:
        raise ErrorDeDominio(409, "El proceso está archivado: no se pueden iniciar instancias")
    variables = validar_variables(db, proc.organization_id, variables)
    v = version_ejecutable(db, proc)
    g = leer(v.bpmn_xml)
    if g.problemas:
        raise ErrorDeDominio(422, "El diagrama no se puede ejecutar: " + "; ".join(map(str, g.problemas[:20])))
    inst = BPMNInstance(process_id=proc.id, version=v.version, organization_id=proc.organization_id,
                        status="running", variables=json.dumps(variables), started_by_user_id=user.id)
    db.add(inst)
    db.flush()
    _avanzar(db, inst, g, [(g.inicio, None)])
    _auditar(db, user, "CREATE", inst, proc.name, {"version": v.version, "status": inst.status})
    db.commit()
    return inst


def _rol(user) -> Optional[str]:
    return getattr(user.role, "value", user.role)


def es_humano(paso: BPMNInstanceStep) -> bool:
    """¿Lo completa una persona? (tarea humana o decision manual)."""
    if paso.wait_kind is not None:
        return paso.wait_kind in ESPERAS_HUMANAS
    return paso.element_type in HUMANOS   # pasos anteriores a la migracion 169


def puede_completar(paso: BPMNInstanceStep, user) -> bool:
    if getattr(user, "is_superadmin", False) or _rol(user) == "admin":
        return True
    return paso.candidate_role is None or paso.candidate_role == _rol(user)


def completar(db: Session, inst: BPMNInstance, paso_id: str, user, variables: Optional[dict] = None,
              flow_id: Optional[str] = None) -> BPMNInstance:
    paso = db.query(BPMNInstanceStep).filter(BPMNInstanceStep.id == paso_id,
                                             BPMNInstanceStep.instance_id == inst.id).first()
    if paso is None:
        raise ErrorDeDominio(404, "Paso no encontrado")
    if inst.status != "running" or paso.status != "active" or not es_humano(paso):
        raise ErrorDeDominio(409, "Ese paso no está pendiente de completar")
    if not puede_completar(paso, user):
        raise ErrorDeDominio(403, f"Este paso es para el rol {paso.candidate_role}")
    variables = validar_variables(db, inst.organization_id, variables)
    g = _grafo(db, inst)
    n = g.nodos.get(paso.element_id)
    if n is None:
        raise ErrorDeDominio(409, "El paso ya no está en el diagrama de esta instancia")
    if paso.wait_kind == ESPERA_DECISION:
        if flow_id not in n.salidas:
            raise ErrorDeDominio(422, "Elige una de las salidas de la decisión")
        salidas = [flow_id]
    else:
        salidas = list(n.salidas)
    if variables:
        inst.variables = json.dumps({**_variables(inst), **variables})
    paso.status = "completed"
    paso.completed_at = _ahora()
    paso.completed_by_user_id = user.id
    paso.result = json.dumps({**variables, **({"flow_id": flow_id} if paso.wait_kind == ESPERA_DECISION else {})})
    _avanzar(db, inst, g, [(g.flujos[f].destino, f) for f in salidas])
    db.commit()
    return inst


def cancelar(db: Session, inst: BPMNInstance, user=None) -> BPMNInstance:
    if inst.status != "running":
        raise ErrorDeDominio(409, "La instancia ya ha terminado")
    for p in inst.steps:
        if p.status == "active":
            p.status = "cancelled"
            p.completed_at = _ahora()
    inst.status = "cancelled"
    inst.ended_at = _ahora()
    _auditar(db, user, "UPDATE", inst, None, {"status": "cancelled"})
    db.commit()
    return inst


def _auditar(db: Session, user, accion: str, inst: BPMNInstance, nombre: Optional[str], valores: dict) -> None:
    from app.services.audit import audit_log
    audit_log(db, user, accion, "bpmn_instance", inst.id, nombre, new_values=valores)


def vencer_temporizadores(db: Session) -> dict:
    """Despierta los temporizadores vencidos. Lo llama la tarea periodica."""
    from app.services.entrada_service import organizacion_desactivada
    from app.services.service_desk.ticket_events import como_organizacion
    vencidos = (db.query(BPMNInstanceStep)
                .join(BPMNInstance, BPMNInstance.id == BPMNInstanceStep.instance_id)
                .options(contains_eager(BPMNInstanceStep.instance))
                .filter(BPMNInstanceStep.status == "active",
                        BPMNInstanceStep.element_type == "intermediateCatchEvent",
                        BPMNInstanceStep.due_at <= _ahora(),
                        BPMNInstance.status == "running")
                .all())
    grafos = _Grafos(db)
    n = 0
    for paso in vencidos:
        inst = paso.instance
        # Segunda auditoría 2026-11 (#10): organización desactivada → se salta;
        # el temporizador sigue vencido y salta si se reactiva.
        if organizacion_desactivada(db, inst.organization_id):
            continue
        with como_organizacion(db, inst.organization_id):
            if inst.status != "running" or paso.status != "active":
                continue   # otro temporizador de la misma instancia la termino
            paso.status = "completed"
            paso.completed_at = _ahora()
            g = grafos.de(inst)
            _avanzar(db, inst, g, [(g.flujos[f].destino, f) for f in g.nodos[paso.element_id].salidas])
            db.commit()
            n += 1
    return {"timers_fired": n}


def serializar(inst: BPMNInstance, con_pasos: bool = True, grafos: Optional[_Grafos] = None) -> dict:
    out = {
        "id": inst.id, "process_id": inst.process_id, "version": inst.version, "status": inst.status,
        "variables": _variables(inst), "error": inst.error, "error_code": inst.error_code,
        "error_params": json.loads(inst.error_params) if inst.error_params else None,
        "started_by_user_id": inst.started_by_user_id,
        "started_at": inst.started_at.isoformat() if inst.started_at else None,
        "ended_at": inst.ended_at.isoformat() if inst.ended_at else None,
        "active_steps": [s.name or s.element_id for s in inst.steps if s.status == "active"],
    }
    if con_pasos:
        out["steps"] = [serializar_paso(s, grafos) for s in inst.steps]
    return out


def serializar_paso(s: BPMNInstanceStep, grafos: Optional[_Grafos] = None) -> dict:
    out = {
        "id": s.id, "instance_id": s.instance_id, "element_id": s.element_id, "element_type": s.element_type,
        "name": s.name, "status": s.status, "candidate_role": s.candidate_role, "wait_kind": s.wait_kind,
        "due_at": s.due_at.isoformat() if s.due_at else None,
        "completed_by_user_id": s.completed_by_user_id,
        "result": json.loads(s.result) if s.result else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        "human": es_humano(s),
    }
    if s.wait_kind == ESPERA_DECISION and s.status == "active" and grafos is not None:
        out["options"] = grafos.de(s.instance).opciones(s.element_id)
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
        raise ErrorDeDominio(404, "Instancia no encontrada")
    return inst


def detalle(db: Session, inst: BPMNInstance) -> dict:
    """La instancia con su historial y las opciones de sus decisiones pendientes."""
    return serializar(inst, grafos=_Grafos(db))


def _nombres(db: Session, ids) -> dict:
    return dict(db.query(BPMNProcess.id, BPMNProcess.name).filter(BPMNProcess.id.in_(set(ids) or {""})).all())


def listar(db: Session, user, status: Optional[str], process_id: Optional[str], limite: int) -> list[dict]:
    # selectinload: `active_steps` lee los pasos; sin esto, una consulta por fila.
    q = _de_la_organizacion(db.query(BPMNInstance).options(selectinload(BPMNInstance.steps)), BPMNInstance, user)
    if status:
        q = q.filter(BPMNInstance.status == status)
    if process_id:
        q = q.filter(BPMNInstance.process_id == process_id)
    filas = q.order_by(BPMNInstance.started_at.desc()).limit(limite).all()
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
    mios = [p for p in pasos if puede_completar(p, user)]
    nombres = _nombres(db, {p.instance.process_id for p in mios})
    grafos = _Grafos(db)
    return [{**serializar_paso(p, grafos), "process_id": p.instance.process_id,
             "process_name": nombres.get(p.instance.process_id), "variables": _variables(p.instance)} for p in mios]
