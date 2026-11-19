"""Diseñador gráfico de flujos de aprobación e información (tarea #26).

El diagrama (`approval_workflows.diagrama`) es lo que dibuja la pantalla:

    nodos   = [{id, type, position: {x, y}, data: {...}}]
    aristas = [{id, source, target, sourceHandle: "si" | "no" | None}]

Tipos de nodo: `start`, `end`, `approve` (persona, rol, responsable, nivel de
responsable, departamento o grupo; quórum, caducidad y escalado), `inform`
(avisa y sigue), `condition` (rama sí/no con una condición del catálogo del
dominio) y `split` / `join` (ramas en paralelo).

Al guardar se COMPILA a los pasos de siempre (`ApprovalStep`), que es lo que
ejecuta el motor de aprobaciones —no hay un segundo motor—:

- cada nodo aprobar/informar es una etapa (`step_order`) propia;
- una división en paralelo da UNA etapa con un paso por rama (cada rama, un
  único nodo, que llega al mismo `join`);
- una condición da las etapas de la rama «sí» con la condición y las de la
  rama «no» con la condición negada (`step_condition = {"dominio", "arbol"}`);
  solo se activa la rama que toca, las otras se saltan. Las condiciones
  anidadas se combinan con Y.

Un flujo sin diagrama se edita igual: `diagrama_de` lo genera desde sus pasos.
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.billing_reports import ApprovalRequest, ApprovalStep, ApprovalWorkflow
from app.core.codigos_de_error import error

TIPOS = ("start", "end", "approve", "inform", "condition", "split", "join")
CAMPOS_DE_PASO = ("approver_type", "approver_role", "approver_user_id", "approver_department", "approver_group_id",
                  "approver_level", "required_approvals", "timeout_hours", "on_timeout", "escalate_to_user_id",
                  "reminder_hours", "requires_attachment")
APROBADORES = ("user", "role", "manager", "manager_level", "any_in_department", "group")
_FALTA = {"user": "approver_user_id", "role": "approver_role", "any_in_department": "approver_department",
          "group": "approver_group_id", "manager_level": "approver_level"}


def _wf(db: Session, workflow_id: str) -> ApprovalWorkflow:
    wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id).first()
    if wf is None:
        raise error(404, "no_encontrado", detail="Flujo no encontrado", que="flujo")
    return wf


def _dominio_de(wf):
    from app.services.politicas.catalogo import dominio_de_aprobacion
    return dominio_de_aprobacion(wf.entity_type)


def diagrama_de(db: Session, workflow_id: str) -> dict:
    """El diagrama guardado o, si no hay, uno generado desde los pasos."""
    wf = _wf(db, workflow_id)
    dom = _dominio_de(wf)
    base = {"workflow_id": wf.id, "entity_type": wf.entity_type, "dominio": dom.clave if dom else None,
            "solicitudes_pendientes": db.query(ApprovalRequest.id).filter(
                ApprovalRequest.workflow_id == wf.id, ApprovalRequest.status == "pending").count()}
    if wf.diagrama:
        try:
            return {**base, **json.loads(wf.diagrama), "generado": False}
        except ValueError:
            pass
    return {**base, **_desde_pasos(list(wf.steps or [])), "generado": True}


def _desde_pasos(pasos: list) -> dict:
    nodos = [{"id": "inicio", "type": "start", "position": {"x": 0, "y": 120}, "data": {}}]
    aristas = []
    previo, x = "inicio", 220
    for orden in sorted({p.step_order for p in pasos}):
        etapa = [p for p in pasos if p.step_order == orden]
        datos = [{"nombre": p.name, **{k: getattr(p, k, None) for k in CAMPOS_DE_PASO},
                  "condicion_legado": p.step_condition if p.step_condition and "arbol" not in (p.step_condition or "") else None}
                 for p in etapa]
        tipos = ["inform" if (getattr(p, "kind", None) == "inform") else "approve" for p in etapa]
        if len(etapa) == 1:
            nid = f"paso-{orden}"
            nodos.append({"id": nid, "type": tipos[0], "position": {"x": x, "y": 120}, "data": datos[0]})
            aristas.append({"id": f"e-{previo}-{nid}", "source": previo, "target": nid})
            previo, x = nid, x + 220
            continue
        div, union = f"div-{orden}", f"union-{orden}"
        nodos.append({"id": div, "type": "split", "position": {"x": x, "y": 120}, "data": {}})
        aristas.append({"id": f"e-{previo}-{div}", "source": previo, "target": div})
        for i, (d, t) in enumerate(zip(datos, tipos)):
            nid = f"paso-{orden}-{i}"
            nodos.append({"id": nid, "type": t, "position": {"x": x + 200, "y": 40 + i * 140}, "data": d})
            aristas += [{"id": f"e-{div}-{nid}", "source": div, "target": nid},
                        {"id": f"e-{nid}-{union}", "source": nid, "target": union}]
        nodos.append({"id": union, "type": "join", "position": {"x": x + 420, "y": 120}, "data": {}})
        previo, x = union, x + 640
    nodos.append({"id": "fin", "type": "end", "position": {"x": x, "y": 120}, "data": {}})
    aristas.append({"id": f"e-{previo}-fin", "source": previo, "target": "fin"})
    return {"nodos": nodos, "aristas": aristas}


class _Grafo:
    def __init__(self, diagrama: dict):
        self.nodos = {n["id"]: n for n in diagrama.get("nodos") or []}
        self.salidas: dict = {i: [] for i in self.nodos}
        self.entradas: dict = {i: [] for i in self.nodos}
        for a in diagrama.get("aristas") or []:
            if a.get("source") in self.nodos and a.get("target") in self.nodos:
                self.salidas[a["source"]].append(a)
                self.entradas[a["target"]].append(a)

    def siguiente(self, nid: str, rama: Optional[str] = None) -> Optional[str]:
        sal = [a for a in self.salidas[nid] if rama is None or a.get("sourceHandle") == rama]
        return sal[0]["target"] if sal else None

    def alcanzables(self, nid: str) -> list:
        orden, vistos, cola = [], {nid}, [nid]
        while cola:
            n = cola.pop(0)
            orden.append(n)
            for a in self.salidas[n]:
                if a["target"] not in vistos:
                    vistos.add(a["target"])
                    cola.append(a["target"])
        return orden

    def confluencia(self, a: str, b: str) -> Optional[str]:
        """El primer nodo al que se llega desde las dos ramas (en anchura desde `a`)."""
        desde_b = set(self.alcanzables(b))
        return next((n for n in self.alcanzables(a) if n in desde_b), None)


def validar(diagrama: dict, dominio=None) -> list[dict]:
    """Errores con el nodo al que se refieren (`nodo`) para señalarlo en el lienzo."""
    g = _Grafo(diagrama)
    errores: list[dict] = []
    if not g.nodos:
        return [{"nodo": None, "mensaje": "el diagrama está vacío"}]
    for n in g.nodos.values():
        if n.get("type") not in TIPOS:
            errores.append({"nodo": n["id"], "mensaje": f"tipo de nodo desconocido: {n.get('type')}"})
    inicios = [i for i, n in g.nodos.items() if n["type"] == "start"]
    if len(inicios) != 1:
        return errores + [{"nodo": None, "mensaje": "tiene que haber exactamente un inicio"}]
    if not any(n["type"] == "end" for n in g.nodos.values()):
        errores.append({"nodo": None, "mensaje": "falta el nodo fin"})
    alcanzables = set(g.alcanzables(inicios[0]))
    for i, n in g.nodos.items():
        if i not in alcanzables:
            errores.append({"nodo": i, "mensaje": "no se llega a este nodo desde el inicio"})
        t, sal = n["type"], g.salidas[i]
        if t == "end" and sal:
            errores.append({"nodo": i, "mensaje": "el fin no tiene salidas"})
        if t in ("start", "approve", "inform", "join") and len(sal) != 1:
            errores.append({"nodo": i, "mensaje": "necesita exactamente una salida"})
        if t == "condition":
            ramas = sorted(a.get("sourceHandle") or "" for a in sal)
            if ramas != ["no", "si"]:
                errores.append({"nodo": i, "mensaje": "una condición tiene una salida «sí» y otra «no»"})
            if dominio is None:
                errores.append({"nodo": i, "mensaje": "este tipo de solicitud no tiene catálogo de campos para condiciones"})
            else:
                from app.services.politicas.condiciones import validar_arbol
                errs: list = []
                arbol = (n.get("data") or {}).get("arbol")
                if not arbol or not (arbol.get("hijos") if arbol.get("tipo") == "grupo" else True):
                    errs.append({"mensaje": "la condición está vacía"})
                validar_arbol(dominio, arbol, "arbol", errs)
                errores += [{"nodo": i, "mensaje": e["mensaje"]} for e in errs]
        if t == "split":
            if len(sal) < 2:
                errores.append({"nodo": i, "mensaje": "una división en paralelo necesita al menos dos ramas"})
            destinos = set()
            for a in sal:
                rama = g.nodos[a["target"]]
                if rama["type"] not in ("approve", "inform"):
                    errores.append({"nodo": rama["id"], "mensaje": "cada rama en paralelo es un único paso aprobar o informar"})
                    continue
                destinos.add(g.siguiente(rama["id"]))
            if len(destinos) > 1 or any(d is None or g.nodos[d]["type"] != "join" for d in destinos):
                errores.append({"nodo": i, "mensaje": "todas las ramas en paralelo se unen en el mismo nodo «unir»"})
        if t in ("approve", "inform"):
            d = n.get("data") or {}
            if not (d.get("nombre") or "").strip():
                errores.append({"nodo": i, "mensaje": "ponle nombre al paso"})
            if d.get("approver_type") not in APROBADORES:
                errores.append({"nodo": i, "mensaje": "elige quién aprueba" if t == "approve" else "elige a quién se informa"})
            elif _FALTA.get(d["approver_type"]) and not d.get(_FALTA[d["approver_type"]]):
                errores.append({"nodo": i, "mensaje": "falta la persona, el rol, el departamento, el grupo o el nivel"})
            if t == "approve" and int(d.get("required_approvals") or 1) < 1:
                errores.append({"nodo": i, "mensaje": "el quórum es al menos 1"})
            if d.get("on_timeout") and d["on_timeout"] not in ("escalate", "auto_approve", "reject"):
                errores.append({"nodo": i, "mensaje": "acción al caducar no válida"})
    if not errores and _hay_ciclo(g):
        errores.append({"nodo": None, "mensaje": "el diagrama tiene un ciclo"})
    return errores


def _hay_ciclo(g: _Grafo) -> bool:
    estado: dict = {}

    def visitar(n) -> bool:
        estado[n] = 1
        for a in g.salidas[n]:
            t = a["target"]
            if estado.get(t) == 1 or (t not in estado and visitar(t)):
                return True
        estado[n] = 2
        return False
    return any(visitar(n) for n in g.nodos if n not in estado)


def compilar(diagrama: dict, dominio=None) -> list[dict]:
    """Lista de pasos (dicts con los campos de ApprovalStep) en orden de etapa."""
    g = _Grafo(diagrama)
    inicio = next(i for i, n in g.nodos.items() if n["type"] == "start")
    etapas: list = []

    def condicion(conds: list) -> Optional[str]:
        if not conds:
            return None
        return json.dumps({"dominio": dominio.clave, "arbol": {"tipo": "grupo", "op": "and", "hijos": conds}},
                          ensure_ascii=False)

    def paso(n: dict, conds: list) -> dict:
        d = n.get("data") or {}
        quorum = int(d.get("required_approvals") or 1)
        sal = {k: d.get(k) for k in CAMPOS_DE_PASO if d.get(k) not in (None, "")}
        sal.update(name=(d.get("nombre") or "Paso")[:100], kind="inform" if n["type"] == "inform" else "approve",
                   required_approvals=quorum, parallel_quorum=quorum > 1,
                   step_condition=condicion(conds) or d.get("condicion_legado"))
        sal.setdefault("timeout_hours", 72)
        sal.setdefault("on_timeout", "escalate")
        return sal

    def tramo(nid: Optional[str], parar: Optional[str], conds: list) -> None:
        while nid and nid != parar:
            n = g.nodos[nid]
            t = n["type"]
            if t == "end":
                return
            if t in ("approve", "inform"):
                etapas.append([paso(n, conds)])
                nid = g.siguiente(nid)
            elif t == "condition":
                arbol = (n.get("data") or {}).get("arbol")
                si, no = g.siguiente(nid, "si"), g.siguiente(nid, "no")
                union = g.confluencia(si, no)
                tramo(si, union, conds + [arbol])
                tramo(no, union, conds + [{"tipo": "grupo", "op": "and", "negar": True, "hijos": [arbol]}])
                nid = union
            elif t == "split":
                ramas = [g.nodos[a["target"]] for a in g.salidas[nid]]
                etapas.append([paso(r, conds) for r in ramas])
                nid = g.siguiente(g.siguiente(ramas[0]["id"]))   # el join y lo que le sigue
            else:   # start, join
                nid = g.siguiente(nid)
    tramo(g.siguiente(inicio), None, [])
    return [{**p, "step_order": i + 1} for i, etapa in enumerate(etapas) for p in etapa]


def guardar(db: Session, usuario, workflow_id: str, diagrama: dict) -> dict:
    """Valida, compila a pasos (sustituye los del flujo) y guarda el diagrama."""
    wf = _wf(db, workflow_id)
    dominio = _dominio_de(wf)
    limpio = {"nodos": diagrama.get("nodos") or [], "aristas": diagrama.get("aristas") or []}
    errores = validar(limpio, dominio)
    if errores:
        raise ErrorDeDominio(422, {"message": "El diagrama tiene errores", "errors": errores})
    pasos = compilar(limpio, dominio)
    if not pasos:
        raise ErrorDeDominio(422, {"message": "El diagrama tiene errores",
                                   "errors": [{"nodo": None, "mensaje": "añade al menos un paso"}]})
    for s in list(wf.steps):
        wf.steps.remove(s)
    db.flush()
    for p in pasos:
        wf.steps.append(ApprovalStep(id=str(uuid.uuid4()), organization_id=wf.organization_id, **p))
    wf.diagrama = json.dumps(limpio, ensure_ascii=False)
    db.commit()
    return {**diagrama_de(db, wf.id), "pasos": len(pasos)}


def comprobar(db: Session, workflow_id: str, diagrama: dict) -> dict:
    wf = _wf(db, workflow_id)
    dominio = _dominio_de(wf)
    errores = validar(diagrama, dominio)
    return {"valido": not errores, "errores": errores,
            "pasos": [] if errores else compilar(diagrama, dominio)}
