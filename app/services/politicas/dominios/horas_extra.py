"""Dominio `horas_extra` del motor de políticas (18-11-2026, rev. 184).

Mapea `PeticionDeHorasExtra` al catálogo del motor. El ciclo de vida vive en
`app/services/horas_extra/`; aquí solo los CAMPOS tipados y cómo cargar,
resumir y fijar campos. La aprobación es la del motor común con el tipo
`overtime` (niveles, grupos, escalado por timeout, aprobación por correo).

Nada está fijado en el código: cada límite o control es una regla que se
escribe en la pantalla de Políticas. Ejemplos (los carga «Cargar ejemplos»
como BORRADORES, ver `app/services/horas_extra/ejemplos.py`):

  · máximo legal español: «Horas en el año (pagadas) > 80» → bloquear;
  · «Horas en el día > 4» / «en la semana > 10» / «en el mes > 20» → bloquear o avisar;
  · antelación mínima: «Origen es previa Y Antelación (horas) < 24» → avisar;
  · descanso mínimo entre jornadas: «Descanso (horas) < 12» → bloquear;
  · máximo de días seguidos: «Días seguidos > 6» → bloquear;
  · presupuesto por proyecto/departamento: «Presupuesto restante < 0» → +1 nivel;
  · quién puede pedir: «Rol está en [subcontractor]» → bloquear;
  · factores por tipo de día: «Clase de día es festivo» → fijar Factor = 1.75;
  · compensación elegible: «Tipo es guardia» → fijar Compensación = pago;
  · requisitos: «Tipo es guardia Y Sustituto está vacío» → bloquear;
    «Horas > 2» → exigir justificación (el motivo);
  · niveles extra: «Clase de día es festivo» → +1 nivel de aprobación.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.services.politicas.registro import Campo, Dominio, Opcion, registrar

_NUM = ("gt", "gte", "lt", "lte", "eq", "ne", "between")

TIPOS = (Opcion("laborable", "Horas extra en día laborable"), Opcion("fuera_de_franja", "Fuera de su franja"),
         Opcion("festivo", "Festivo"), Opcion("no_laborable", "Fin de semana o día libre"),
         Opcion("guardia", "Guardia"))
CLASES = (Opcion("laborable", "Laborable"), Opcion("festivo", "Festivo"), Opcion("no_laborable", "No laborable"))
COMPENSACIONES = (Opcion("pago", "Pago"), Opcion("bolsa", "Bolsa de horas"), Opcion("ninguna", "Ninguna"))

CAMPOS = [
    Campo("tipo", "Tipo de horas extra", "enum", opciones=TIPOS, categoria_de_tabla=True),
    Campo("origen", "Origen", "enum", opciones=(Opcion("previa", "Petición previa"),
                                                 Opcion("posterior", "Declaración posterior (imputado)"))),
    Campo("clase_dia", "Clase de día (según su horario)", "enum", opciones=CLASES),
    Campo("fecha", "Fecha", "fecha"),
    Campo("hora_inicio", "Hora de inicio", "hora"),
    Campo("hora_fin", "Hora de fin", "hora"),
    Campo("horas", "Horas de la petición", "numero", operadores=_NUM),
    Campo("horas_fuera_de_horario", "Horas de la franja fuera de su horario", "numero", operadores=_NUM),
    Campo("horario_del_dia", "Horas de su horario ese día", "numero", operadores=_NUM),
    Campo("imputado_del_dia", "Horas imputadas ese día", "numero", operadores=_NUM),
    Campo("exceso_imputado", "Exceso imputado ese día sobre su horario", "numero", operadores=_NUM),
    Campo("horas_en_dia", "Horas extra en el día (con esta)", "numero", operadores=_NUM),
    Campo("horas_en_semana", "Horas extra en la semana (con esta)", "numero", operadores=_NUM),
    Campo("horas_en_mes", "Horas extra en el mes (con esta)", "numero", operadores=_NUM),
    Campo("horas_en_anio", "Horas extra en el año (con esta)", "numero", operadores=_NUM),
    Campo("horas_en_anio_pago", "Horas extra pagadas en el año (con esta)", "numero", operadores=_NUM,
          ayuda="Solo las que se compensan con pago (el máximo legal no cuenta las compensadas con descanso)"),
    Campo("antelacion_horas", "Antelación (horas)", "numero", operadores=_NUM,
          ayuda="Horas entre la petición y el comienzo; negativa si se pide después"),
    Campo("descanso_horas", "Descanso entre jornadas (horas)", "numero", operadores=_NUM,
          ayuda="El menor descanso con el día anterior o el siguiente, contando estas horas"),
    Campo("dias_seguidos", "Días seguidos trabajando", "numero", operadores=_NUM),
    Campo("presupuesto_restante", "Presupuesto de horas que queda (tras esta)", "numero", operadores=_NUM,
          ayuda="El menor de los presupuestos que le aplican (empresa, departamento, equipo, proyecto); vacío si no hay"),
    Campo("compensacion", "Compensación", "enum", opciones=COMPENSACIONES, asignable=True),
    Campo("factor", "Factor de pago", "numero", operadores=_NUM, asignable=True,
          ayuda="Cuánto vale cada hora al pagarla (1,75 = 175 %)"),
    Campo("proyecto", "Proyecto", "entidad", entidad="proyecto"),
    Campo("ticket", "Ticket", "texto"),
    Campo("motivo", "Motivo", "texto"),
    Campo("sustituto", "Sustituto", "entidad", entidad="usuario"),
    Campo("persona", "Persona", "entidad", entidad="usuario"),
    Campo("pide_otro", "La pide otra persona (su responsable)", "booleano"),
    Campo("rol", "Rol", "entidad", entidad="rol"),
    Campo("departamento", "Departamento", "entidad", entidad="departamento"),
    Campo("equipo", "Equipo", "entidad", entidad="equipo"),
    Campo("sede", "Sede", "enum"),
    Campo("grupos", "Grupos de la persona", "entidad", entidad="grupo",
          operadores=("eq", "ne", "in", "not_in", "empty", "not_empty")),
    Campo("tipo_de_contrato", "Tipo de contrato", "enum"),
]


def contexto(db, p) -> dict:
    from app.services.horas_extra import reglas
    return reglas.contexto(db, p)


def cargar(db, entidad_id: str):
    from app.models.horas_extra import PeticionDeHorasExtra
    return db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.id == entidad_id).first()


def historicos(db, desde: Optional[date], hasta: Optional[date], limite: int) -> list:
    from app.models.horas_extra import PeticionDeHorasExtra
    q = db.query(PeticionDeHorasExtra).filter(PeticionDeHorasExtra.estado != "cancelada")
    if desde:
        q = q.filter(PeticionDeHorasExtra.fecha >= desde)
    if hasta:
        q = q.filter(PeticionDeHorasExtra.fecha <= hasta)
    return q.order_by(PeticionDeHorasExtra.fecha.desc(), PeticionDeHorasExtra.created_at.desc()).limit(limite).all()


def resumen(p) -> str:
    franja = f" {p.hora_inicio:%H:%M}–{p.hora_fin:%H:%M}" if p.hora_inicio and p.hora_fin else ""
    return f"Horas extra {p.fecha}{franja} · {p.horas:g} h · {p.tipo}"


def cumple_requisito(db, p, requisito: dict) -> bool:
    """Justificación = el motivo. Las peticiones de horas extra no llevan adjuntos:
    un `require_attachment` no se puede cumplir y la petición no se envía."""
    if requisito.get("tipo") == "require_justification":
        return bool((p.motivo or "").strip())
    if requisito.get("tipo") == "require_attachment":
        return False
    return True


def aplicar_campo(db, p, campo: str, valor) -> None:
    if campo == "compensacion" and valor in ("pago", "bolsa", "ninguna"):
        p.compensacion = valor
    elif campo == "factor":
        try:
            f = float(valor)
        except (TypeError, ValueError):
            return
        if 0 <= f <= 10:
            p.factor = f


def opciones_dinamicas(db) -> dict:
    from app.models.advanced_config import Office
    from app.models.user import User
    contratos = sorted({c for (c,) in db.query(User.employment_type).filter(User.employment_type.isnot(None)).distinct()
                        if c})
    return {"sede": [Opcion(o.id, o.name) for o in db.query(Office).order_by(Office.name).all()],
            "tipo_de_contrato": [Opcion(c, c) for c in contratos]}


def ejemplos(db, usuario) -> dict:
    from app.services.horas_extra import ejemplos as ej
    from app.services.formato_regional import idioma_de_salida
    return {"tablas": [], "politicas": ej.politicas(idioma_de_salida(
        db, user_id=getattr(usuario, "id", None), org_id=getattr(usuario, "organization_id", None)))}


registrar(Dominio(
    clave="horas_extra", etiqueta="Horas extra", campos=CAMPOS, contexto=contexto, cargar=cargar,
    historicos=historicos, propietario=lambda p: p.user_id, resumen=resumen, tipo_de_aprobacion="overtime",
    cumple_requisito=cumple_requisito, aplicar_campo=aplicar_campo, ejemplos=ejemplos,
    opciones_dinamicas=opciones_dinamicas,
))
