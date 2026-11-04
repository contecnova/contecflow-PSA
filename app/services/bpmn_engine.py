"""Motor de ejecucion de los procesos BPMN guardados en /bpm.

Auditoria 2026-11: /bpm era un catalogo y un editor; nada de un diagrama se
ejecutaba. Este motor recorre el XML de la version publicada (o la ultima si
no hay ninguna publicada) con fichas, y guarda cada elemento que atraviesa
como un paso de la instancia (`bpmn_instance_steps`): eso es tambien su
historial.

Elementos que sabe ejecutar:

- **startEvent**: el de inicio (si hay varios, el que no tiene definicion de evento).
- **task, userTask, manualTask**: paso humano. Espera a que alguien lo complete
  (bandeja de /bpm). Si la tarea esta en una calle (lane) cuyo nombre es un rol
  base (admin, pm, team_lead, hr, employee, o su nombre en la pantalla), solo
  ese rol (o un admin) puede completarlo; si no, cualquiera de la organizacion.
  Al completarlo se pueden aportar variables.
- **serviceTask, scriptTask, sendTask, businessRuleTask**: se anotan como hechos
  y la ficha sigue. **No ejecutan nada**: no hay a que enlazarlos todavia.
- **exclusiveGateway**: la primera salida cuya condicion se cumple; si ninguna,
  la de por defecto; si no hay, la instancia falla con el motivo.
  Condiciones: `variable op valor` (==, !=, >, <, >=, <=), unidas por `and`/`or`
  (o `&&`/`||`), con `${…}` opcional. Lo que no se puede evaluar no se cumple.
- **parallelGateway**: con varias entradas espera a todas (union); con varias
  salidas las sigue todas.
- **intermediateCatchEvent** con temporizador `timeDuration` (ISO 8601, p. ej.
  PT2H, P1D) o `timeDate`: espera; lo despierta la tarea periodica.
- **intermediateThrowEvent** sin definicion: pasa.
- **endEvent**: consume la ficha; con `terminateEventDefinition` termina la
  instancia entera. La instancia acaba cuando no queda nada pendiente.

Cualquier otro elemento (subprocesos, eventos de borde, compuertas inclusivas,
mensajes, senales…) hace que el arranque se rechace con la lista de lo que no
se soporta: mejor no arrancar que arrancar y quedarse a medias.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.bpmn_process import BPMNInstance, BPMNInstanceStep, BPMNProcess, BPMNProcessVersion

_NS = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
_XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"

HUMANOS = {"task", "userTask", "manualTask"}
AUTOMATICOS = {"serviceTask", "scriptTask", "sendTask", "businessRuleTask"}
_SOPORTADOS = HUMANOS | AUTOMATICOS | {"startEvent", "endEvent", "exclusiveGateway", "parallelGateway",
                                       "intermediateCatchEvent", "intermediateThrowEvent"}
_ROLES = {
    "admin": "admin", "dirección": "admin", "direccion": "admin", "dirección / admin": "admin",
    "pm": "pm", "project manager": "pm", "team_lead": "team_lead", "team lead": "team_lead",
    "hr": "hr", "rrhh": "hr", "employee": "employee", "empleado": "employee",
}


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


@dataclass
class Flujo:
    id: str
    origen: str
    destino: str
    condicion: Optional[str]


@dataclass
class Grafo:
    nodos: dict
    flujos: dict
    inicio: Optional[str]
    problemas: list


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def leer(xml: str) -> Grafo:
    """El grafo ejecutable del diagrama y lo que impide ejecutarlo."""
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError as exc:
        return Grafo({}, {}, None, [f"XML no valido: {exc}"])
    procesos = [p for p in raiz.iter(f"{_NS}process")]
    con_inicio = [p for p in procesos if p.find(f"{_NS}startEvent") is not None]
    if not con_inicio:
        return Grafo({}, {}, None, ["El diagrama no tiene evento de inicio"])
    if len(con_inicio) > 1:
        return Grafo({}, {}, None, ["Hay varios procesos (piscinas) con inicio: no se soporta"])
    proceso = con_inicio[0]

    roles = {}
    for calle in proceso.iter(f"{_NS}lane"):
        rol = _ROLES.get((calle.get("name") or "").strip().lower())
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
                                          (cond.text or "").strip() if cond is not None and cond.text else None)
            continue
        defs = [_local(d.tag) for d in hijo if _local(d.tag).endswith("EventDefinition")]
        n = Nodo(hijo.get("id"), tipo, hijo.get("name"), defecto=hijo.get("default"),
                 rol=roles.get(hijo.get("id")), definiciones=defs)
        if tipo not in _SOPORTADOS:
            problemas.append(f"{tipo} «{n.nombre or n.id}»")
        elif tipo == "endEvent":
            n.terminar = "terminateEventDefinition" in defs
            if [d for d in defs if d != "terminateEventDefinition"]:
                problemas.append(f"endEvent con {', '.join(defs)} «{n.nombre or n.id}»")
        elif tipo == "intermediateCatchEvent":
            timer = hijo.find(f"{_NS}timerEventDefinition")
            if timer is None or defs != ["timerEventDefinition"]:
                problemas.append(f"intermediateCatchEvent sin temporizador «{n.nombre or n.id}»")
            else:
                dur, fecha = timer.find(f"{_NS}timeDuration"), timer.find(f"{_NS}timeDate")
                if dur is not None and dur.text and _duracion(dur.text.strip()) is not None:
                    n.temporizador = ("duration", dur.text.strip())
                elif fecha is not None and fecha.text and _fecha(fecha.text.strip()) is not None:
                    n.temporizador = ("date", fecha.text.strip())
                else:
                    problemas.append(f"temporizador sin duración ni fecha válidas «{n.nombre or n.id}»")
        elif tipo == "intermediateThrowEvent" and defs:
            problemas.append(f"intermediateThrowEvent con {', '.join(defs)} «{n.nombre or n.id}»")
        nodos[n.id] = n
    for f in flujos.values():
        if f.origen in nodos:
            nodos[f.origen].salidas.append(f.id)
        if f.destino in nodos:
            nodos[f.destino].entradas.append(f.id)
        if f.condicion and _condicion(f.condicion) is None:
            problemas.append(f"condición que no se puede evaluar en el flujo «{f.id}»: {f.condicion}")

    inicios = [n for n in nodos.values() if n.tipo == "startEvent"]
    simples = [n for n in inicios if not n.definiciones]
    inicio = (simples or inicios)[0].id if inicios else None
    for n in nodos.values():
        if n.tipo not in ("endEvent",) and not n.salidas and n.tipo in _SOPORTADOS:
            problemas.append(f"«{n.nombre or n.id}» no tiene salida")
    return Grafo(nodos, flujos, inicio, problemas)


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


# ── Ejecucion ───────────────────────────────────────────────────────────────

def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _version(db: Session, proc: BPMNProcess) -> BPMNProcessVersion:
    q = db.query(BPMNProcessVersion).filter(BPMNProcessVersion.process_id == proc.id)
    v = q.filter(BPMNProcessVersion.is_published.is_(True)).order_by(BPMNProcessVersion.version.desc()).first() \
        or q.order_by(BPMNProcessVersion.version.desc()).first()
    if v is None:
        raise HTTPException(422, "El proceso no tiene ningún diagrama guardado")
    return v


def _grafo(db: Session, inst: BPMNInstance) -> Grafo:
    v = db.query(BPMNProcessVersion).filter(BPMNProcessVersion.process_id == inst.process_id,
                                            BPMNProcessVersion.version == inst.version).first()
    return leer(v.bpmn_xml)


def _variables(inst: BPMNInstance) -> dict:
    return json.loads(inst.variables or "{}")


def _limite(db: Session, org) -> int:
    from app.services.settings_service import get_runtime_int
    return get_runtime_int(db, "BPMN_MAX_AUTOMATIC_STEPS", org) or 500


def _paso(db, inst, nodo: Nodo, estado: str, **kw) -> BPMNInstanceStep:
    p = BPMNInstanceStep(instance_id=inst.id, organization_id=inst.organization_id, element_id=nodo.id,
                         element_type=nodo.tipo, name=nodo.nombre, status=estado,
                         completed_at=_ahora() if estado == "completed" else None, **kw)
    db.add(p)
    return p


def _fallar(inst: BPMNInstance, motivo: str) -> None:
    inst.status = "failed"
    inst.error = motivo[:500]
    inst.ended_at = _ahora()


def _avanzar(db: Session, inst: BPMNInstance, g: Grafo, entradas: list[tuple[str, Optional[str]]]) -> None:
    """Entra en cada (nodo, flujo por el que llega) y sigue hasta que todo espera."""
    pendientes = list(entradas)
    limite = _limite(db, inst.organization_id)
    vueltas = 0
    while pendientes and inst.status == "running":
        vueltas += 1
        if vueltas > limite:
            _fallar(inst, f"Más de {limite} pasos automáticos seguidos: ¿un bucle sin espera?")
            break
        nodo_id, _flujo = pendientes.pop(0)
        n = g.nodos[nodo_id]
        siguientes = [g.flujos[f].destino for f in n.salidas]
        if n.tipo in HUMANOS:
            _paso(db, inst, n, "active", candidate_role=n.rol)
        elif n.tipo == "intermediateCatchEvent":
            clase, texto = n.temporizador
            vence = _ahora() + _duracion(texto) if clase == "duration" else _fecha(texto)
            _paso(db, inst, n, "active", due_at=vence)
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
            _paso(db, inst, n, "completed")
            if len(n.salidas) <= 1:
                pendientes += [(d, None) for d in siguientes]
                continue
            variables = _variables(inst)
            elegido = next((f for f in n.salidas if f != n.defecto and g.flujos[f].condicion
                            and cumple(g.flujos[f].condicion, variables)), None) or n.defecto
            if elegido is None:
                _fallar(inst, f"Ninguna condición de «{n.nombre or n.id}» se cumple y no hay salida por defecto")
                break
            pendientes.append((g.flujos[elegido].destino, elegido))
        elif n.tipo == "parallelGateway" and len(n.entradas) > 1:
            db.flush()
            union = db.query(BPMNInstanceStep).filter(
                BPMNInstanceStep.instance_id == inst.id, BPMNInstanceStep.element_id == n.id,
                BPMNInstanceStep.status == "active").first()
            if union is None:
                union = _paso(db, inst, n, "active", arrived=1)
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
    v = _version(db, proc)
    g = leer(v.bpmn_xml)
    if g.problemas:
        raise HTTPException(422, "El diagrama no se puede ejecutar: " + "; ".join(g.problemas[:20]))
    inst = BPMNInstance(process_id=proc.id, version=v.version, organization_id=proc.organization_id,
                        status="running", variables=json.dumps(variables or {}), started_by_user_id=user.id)
    db.add(inst)
    db.flush()
    _avanzar(db, inst, g, [(g.inicio, None)])
    db.commit()
    return inst


def puede_completar(paso: BPMNInstanceStep, user) -> bool:
    if getattr(user, "is_superadmin", False) or getattr(user.role, "value", user.role) == "admin":
        return True
    return paso.candidate_role is None or paso.candidate_role == getattr(user.role, "value", user.role)


def completar(db: Session, inst: BPMNInstance, paso_id: str, user, variables: Optional[dict] = None) -> BPMNInstance:
    paso = db.query(BPMNInstanceStep).filter(BPMNInstanceStep.id == paso_id,
                                             BPMNInstanceStep.instance_id == inst.id).first()
    if paso is None:
        raise HTTPException(404, "Paso no encontrado")
    if inst.status != "running" or paso.status != "active" or paso.element_type not in HUMANOS:
        raise HTTPException(409, "Ese paso no está pendiente de completar")
    if not puede_completar(paso, user):
        raise HTTPException(403, f"Este paso es para el rol {paso.candidate_role}")
    if variables:
        inst.variables = json.dumps({**_variables(inst), **variables})
    paso.status = "completed"
    paso.completed_at = _ahora()
    paso.completed_by_user_id = user.id
    paso.result = json.dumps(variables or {})
    g = _grafo(db, inst)
    n = g.nodos[paso.element_id]
    _avanzar(db, inst, g, [(g.flujos[f].destino, f) for f in n.salidas])
    db.commit()
    return inst


def cancelar(db: Session, inst: BPMNInstance) -> BPMNInstance:
    if inst.status != "running":
        raise HTTPException(409, "La instancia ya ha terminado")
    for p in inst.steps:
        if p.status == "active":
            p.status = "cancelled"
            p.completed_at = _ahora()
    inst.status = "cancelled"
    inst.ended_at = _ahora()
    db.commit()
    return inst


def vencer_temporizadores(db: Session) -> dict:
    """Despierta los temporizadores vencidos. Lo llama la tarea periodica."""
    from app.services.service_desk.ticket_events import como_organizacion
    vencidos = db.query(BPMNInstanceStep).filter(
        BPMNInstanceStep.status == "active", BPMNInstanceStep.element_type == "intermediateCatchEvent",
        BPMNInstanceStep.due_at <= _ahora()).all()
    n = 0
    for paso in vencidos:
        inst = db.query(BPMNInstance).filter(BPMNInstance.id == paso.instance_id).first()
        if inst is None or inst.status != "running":
            continue
        with como_organizacion(db, inst.organization_id):
            paso.status = "completed"
            paso.completed_at = _ahora()
            g = _grafo(db, inst)
            _avanzar(db, inst, g, [(g.flujos[f].destino, f) for f in g.nodos[paso.element_id].salidas])
            db.commit()
            n += 1
    return {"timers_fired": n}


def serializar(inst: BPMNInstance, con_pasos: bool = True) -> dict:
    out = {
        "id": inst.id, "process_id": inst.process_id, "version": inst.version, "status": inst.status,
        "variables": _variables(inst), "error": inst.error, "started_by_user_id": inst.started_by_user_id,
        "started_at": inst.started_at.isoformat() if inst.started_at else None,
        "ended_at": inst.ended_at.isoformat() if inst.ended_at else None,
        "active_steps": [s.name or s.element_id for s in inst.steps if s.status == "active"],
    }
    if con_pasos:
        out["steps"] = [serializar_paso(s) for s in inst.steps]
    return out


def serializar_paso(s: BPMNInstanceStep) -> dict:
    return {
        "id": s.id, "instance_id": s.instance_id, "element_id": s.element_id, "element_type": s.element_type,
        "name": s.name, "status": s.status, "candidate_role": s.candidate_role,
        "due_at": s.due_at.isoformat() if s.due_at else None,
        "completed_by_user_id": s.completed_by_user_id,
        "result": json.loads(s.result) if s.result else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        "human": s.element_type in HUMANOS,
    }


# ── Consultas para la API (la capa API no consulta la base) ─────────────────

def _de_la_organizacion(q, modelo, user):
    return q if getattr(user, "is_superadmin", False) else q.filter(modelo.organization_id == user.organization_id)


def proceso_para_arrancar(db: Session, process_id: str, user) -> Optional[BPMNProcess]:
    return _de_la_organizacion(db.query(BPMNProcess).filter(BPMNProcess.id == process_id,
                                                            BPMNProcess.is_active.is_(True)), BPMNProcess, user).first()


def instancia(db: Session, instance_id: str, user) -> BPMNInstance:
    inst = _de_la_organizacion(db.query(BPMNInstance).filter(BPMNInstance.id == instance_id),
                               BPMNInstance, user).first()
    if inst is None:
        raise HTTPException(404, "Instancia no encontrada")
    return inst


def _nombres(db: Session, ids) -> dict:
    return dict(db.query(BPMNProcess.id, BPMNProcess.name).filter(BPMNProcess.id.in_(set(ids) or {""})).all())


def listar(db: Session, user, status: Optional[str], process_id: Optional[str], limite: int) -> list[dict]:
    q = _de_la_organizacion(db.query(BPMNInstance), BPMNInstance, user)
    if status:
        q = q.filter(BPMNInstance.status == status)
    if process_id:
        q = q.filter(BPMNInstance.process_id == process_id)
    filas = q.order_by(BPMNInstance.started_at.desc()).limit(limite).all()
    nombres = _nombres(db, {i.process_id for i in filas})
    return [{**serializar(i, con_pasos=False), "process_name": nombres.get(i.process_id)} for i in filas]


def bandeja(db: Session, user) -> list[dict]:
    pasos = _de_la_organizacion(
        db.query(BPMNInstanceStep).join(BPMNInstance, BPMNInstance.id == BPMNInstanceStep.instance_id).filter(
            BPMNInstanceStep.status == "active", BPMNInstanceStep.element_type.in_(HUMANOS),
            BPMNInstance.status == "running"),
        BPMNInstanceStep, user).order_by(BPMNInstanceStep.created_at).all()
    mios = [p for p in pasos if puede_completar(p, user)]
    nombres = _nombres(db, {p.instance.process_id for p in mios})
    return [{**serializar_paso(p), "process_id": p.instance.process_id,
             "process_name": nombres.get(p.instance.process_id), "variables": _variables(p.instance)} for p in mios]
