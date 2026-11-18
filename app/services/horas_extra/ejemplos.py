"""«Cargar ejemplos» del dominio `horas_extra` (18-11-2026).

Dos políticas de ejemplo que se crean como BORRADOR (hay que revisarlas y
publicarlas en Políticas; nunca se aplican solas). Todas las cifras son
editables: son ejemplos, no constantes del producto.

- «Horas extra: límites legales y de empresa»: el máximo legal español de
  80 h/año pagadas (art. 35.2 ET; las compensadas con descanso no cuentan),
  4 h/día, 10 h/semana (aviso), 12 h de descanso entre jornadas, 6 días seguidos,
  antelación de 24 h (aviso) y presupuesto agotado (+1 nivel).
- «Horas extra: compensación y aprobación»: factor 1,75 en festivo y 1,5 en día
  no laborable, la guardia se paga y necesita sustituto, festivos con un nivel
  más de aprobación y motivo obligatorio a partir de 2 h.
"""
from __future__ import annotations


def _c(campo, operador, valor=None, valor2=None):
    return {"tipo": "condicion", "campo": campo, "operador": operador, "valor": valor, "valor2": valor2}


def _y(*hijos):
    return {"tipo": "grupo", "op": "and", "hijos": list(hijos)}


def _regla(nombre, condicion, *resultados):
    return {"nombre": nombre, "activa": True, "detener": False, "exceso": None, "condicion": condicion,
            "resultados": list(resultados)}


def _bloquear(m):
    return {"tipo": "block", "mensaje": m}


def _avisar(m):
    return {"tipo": "warn", "mensaje": m}


NOMBRE_LIMITES = "Horas extra: límites legales y de empresa (ejemplo)"
NOMBRE_COMPENSACION = "Horas extra: compensación y aprobación (ejemplo)"


def politicas() -> list[dict]:
    ambito = {"departamentos": [], "equipos": [], "roles": [], "ubicaciones": [], "personas": []}
    return [
        {"nombre": NOMBRE_LIMITES, "prioridad": 200, "ambito": ambito,
         "descripcion": "Ejemplo editable. El máximo legal español de horas extraordinarias es 80 al año "
                        "(art. 35.2 del Estatuto de los Trabajadores); no cuentan las compensadas con descanso, "
                        "por eso la regla mira las pagadas. El resto de cifras son de empresa.",
         "reglas": [
             _regla("Máximo legal: 80 h/año pagadas", _y(_c("horas_en_anio_pago", "gt", 80)),
                    _bloquear("Superaría el máximo legal de 80 horas extra pagadas al año")),
             _regla("Como mucho 4 h en un día", _y(_c("horas_en_dia", "gt", 4)),
                    _bloquear("Como mucho 4 horas extra en un día")),
             _regla("Aviso a partir de 10 h en la semana", _y(_c("horas_en_semana", "gt", 10)),
                    _avisar("Más de 10 horas extra en la semana")),
             _regla("Descanso mínimo de 12 h entre jornadas", _y(_c("descanso_horas", "lt", 12)),
                    _bloquear("No respeta el descanso mínimo de 12 horas entre jornadas")),
             _regla("Como mucho 6 días seguidos", _y(_c("dias_seguidos", "gt", 6)),
                    _bloquear("Más de 6 días seguidos de trabajo")),
             _regla("Antelación de 24 h", _y(_c("origen", "eq", "previa"), _c("antelacion_horas", "lt", 24)),
                    _avisar("Pedida con menos de 24 horas de antelación")),
             _regla("Presupuesto agotado: un nivel más", _y(_c("presupuesto_restante", "lt", 0)),
                    {"tipo": "add_approval_levels", "niveles": 1}),
         ]},
        {"nombre": NOMBRE_COMPENSACION, "prioridad": 150, "ambito": ambito,
         "descripcion": "Ejemplo editable: factores de pago por tipo de día, guardias y niveles de aprobación.",
         "reglas": [
             _regla("Festivo: factor 1,75 y un nivel más", _y(_c("clase_dia", "eq", "festivo")),
                    {"tipo": "set_field", "campo": "factor", "valor": 1.75},
                    {"tipo": "add_approval_levels", "niveles": 1}),
             _regla("Día no laborable: factor 1,5", _y(_c("clase_dia", "eq", "no_laborable")),
                    {"tipo": "set_field", "campo": "factor", "valor": 1.5}),
             _regla("La guardia se paga", _y(_c("tipo", "eq", "guardia")),
                    {"tipo": "set_field", "campo": "compensacion", "valor": "pago"}),
             _regla("La guardia necesita sustituto", _y(_c("tipo", "eq", "guardia"), _c("sustituto", "empty")),
                    _bloquear("Una guardia necesita sustituto")),
             _regla("Motivo a partir de 2 h", _y(_c("horas", "gt", 2)),
                    {"tipo": "require_justification", "mensaje": "Explica el motivo de más de 2 horas extra"}),
         ]},
    ]
