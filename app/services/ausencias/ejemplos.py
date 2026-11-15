"""«Cargar ejemplos» de ausencias: el caso del cliente, listo para revisar.

Tres turnos al día (mañana, tarde, noche), como mucho DOS personas de
vacaciones por día y turno, plaza por orden de llegada AL PEDIR, lista de
espera, aprobación del responsable y luego de RRHH, e informar al jefe de
equipo.

Nunca se aplica solo:
  · la política se crea como BORRADOR (hay que publicarla en Políticas);
  · el flujo se crea DESACTIVADO y sin enlazar a ningún tipo (hay que activarlo
    y elegirlo en el tipo «Vacaciones»);
  · los turnos se crean, pero no cambian nada hasta que alguien tenga
    cuadrante (rotación o cambios por día).
Es idempotente: lo que ya existe con ese nombre no se duplica.
"""
from __future__ import annotations

import uuid
from datetime import time

from sqlalchemy.orm import Session

from app.models.ausencias import Turno

NOMBRE_DE_POLITICA = "Vacaciones: dos por día y turno, por orden de llegada"
NOMBRE_DE_FLUJO = "Ausencias: responsable y RRHH, informa al jefe de equipo"
TURNOS = (("Mañana", "06:00", "14:00", "#f5b83d", 10), ("Tarde", "14:00", "22:00", "#4f8cff", 20),
          ("Noche", "22:00", "06:00", "#6b5bd6", 30))


def politica_de_ejemplo() -> dict:
    """El documento de la política (formato de `politicas.servicio.crear`)."""
    return {
        "dominio": "ausencias", "nombre": NOMBRE_DE_POLITICA, "prioridad": 200, "activa": True,
        "descripcion": "Como mucho dos personas de vacaciones a la vez en cada turno de cada día. La plaza es de "
                       "quien la pide antes; si no queda, la petición espera y, cuando alguien cancela o le "
                       "rechazan, pasa la siguiente y se avisa a la persona y al jefe de equipo.",
        "ambito": {"departamentos": [], "equipos": [], "roles": [], "ubicaciones": [], "personas": []},
        "reglas": [{
            "nombre": "Cupo de vacaciones por turno", "activa": True, "detener": False, "exceso": None,
            "condicion": {"tipo": "grupo", "op": "and", "hijos": [
                {"tipo": "condicion", "campo": "tipo", "operador": "eq", "valor": "vacation"}]},
            "resultados": [{
                "tipo": "cupo", "clave": str(uuid.uuid4()), "maximo": 2, "agrupar_por": "empresa",
                "por_turno": True, "momento": "solicitud",
                "si_lleno": [{"tipo": "waitlist", "mensaje": "No quedan plazas ese día y turno: entras en lista de espera"}],
                "avisar_al_promover": [{"tipo": "solicitante"}, {"tipo": "rol", "valor": "team_lead"}],
                "canales": ["app", "email"],
            }],
        }],
    }


def cargar(db: Session, usuario) -> dict:
    from app.models.billing_reports import ApprovalStep, ApprovalWorkflow
    from app.models.politicas import Politica
    from app.services.ausencias import turnos
    from app.services.politicas import servicio
    org = usuario.organization_id
    creados = {"turnos": [], "flujo": None, "politica": None}
    existentes = {t.nombre for t in turnos.turnos(db, incluir_inactivos=True)}
    for nombre, ini, fin, color, orden in TURNOS:
        if nombre in existentes:
            continue
        h0, h1 = (time(*map(int, x.split(":"))) for x in (ini, fin))
        db.add(Turno(id=str(uuid.uuid4()), organization_id=org, nombre=nombre, color=color, hora_inicio=h0,
                     hora_fin=h1, dias_semana=None, personas_requeridas=0, trabaja_festivos=True, activo=True,
                     orden=orden))
        creados["turnos"].append(nombre)
    wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.name == NOMBRE_DE_FLUJO).first()
    if wf is None:
        wf = ApprovalWorkflow(id=str(uuid.uuid4()), organization_id=org, name=NOMBRE_DE_FLUJO, entity_type="leave",
                              is_active=False, is_default=False, trigger_conditions="{}",
                              description="Ejemplo: actívalo y elígelo en el tipo «Vacaciones».")
        db.add(wf)
        db.flush()
        for orden, nombre, tipo, rol, kind in ((1, "Responsable", "manager", None, "approve"),
                                               (2, "RRHH", "role", "hr", "approve"),
                                               (3, "Informar al jefe de equipo", "role", "team_lead", "inform")):
            db.add(ApprovalStep(id=str(uuid.uuid4()), organization_id=org, workflow_id=wf.id, step_order=orden,
                                name=nombre, approver_type=tipo, approver_role=rol, kind=kind, timeout_hours=72,
                                on_timeout="escalate", required_approvals=1))
        creados["flujo"] = wf.id
    db.commit()
    hay = db.query(Politica.id).filter(Politica.dominio == "ausencias", Politica.nombre == NOMBRE_DE_POLITICA).first()
    if hay is None:
        creados["politica"] = servicio.crear(db, usuario, politica_de_ejemplo())["id"]
    return {**creados, "flujo_id": wf.id, "flujo_activo": bool(wf.is_active),
            "pasos_siguientes": ["publicar_politica", "activar_flujo", "elegir_flujo_en_vacaciones", "asignar_cuadrante"]}
