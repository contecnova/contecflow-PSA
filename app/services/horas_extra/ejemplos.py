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


# 23-11-2026: nombres, descripciones y mensajes salen de `textos_de_salida` (`horas_extra.ej.*`), en el
# idioma de quien carga los ejemplos; antes eran castellano fijo. Las cifras siguen siendo editables.
NOMBRE_LIMITES = "horas_extra.ej.limites.nombre"
NOMBRE_COMPENSACION = "horas_extra.ej.compensacion.nombre"


def politicas(idioma=None) -> list[dict]:
    from app.services.textos_de_salida import texto as _texto

    def t(clave):
        return _texto(f"horas_extra.ej.{clave}", idioma)

    ambito = {"departamentos": [], "equipos": [], "roles": [], "ubicaciones": [], "personas": []}
    return [
        {"nombre": t("limites.nombre"), "prioridad": 200, "ambito": ambito,
         "descripcion": t("limites.descripcion"),
         "reglas": [
             _regla(t("l1.nombre"), _y(_c("horas_en_anio_pago", "gt", 80)), _bloquear(t("l1.mensaje"))),
             _regla(t("l2.nombre"), _y(_c("horas_en_dia", "gt", 4)), _bloquear(t("l2.mensaje"))),
             _regla(t("l3.nombre"), _y(_c("horas_en_semana", "gt", 10)), _avisar(t("l3.mensaje"))),
             _regla(t("l4.nombre"), _y(_c("descanso_horas", "lt", 12)), _bloquear(t("l4.mensaje"))),
             _regla(t("l5.nombre"), _y(_c("dias_seguidos", "gt", 6)), _bloquear(t("l5.mensaje"))),
             _regla(t("l6.nombre"), _y(_c("origen", "eq", "previa"), _c("antelacion_horas", "lt", 24)),
                    _avisar(t("l6.mensaje"))),
             _regla(t("l7.nombre"), _y(_c("presupuesto_restante", "lt", 0)),
                    {"tipo": "add_approval_levels", "niveles": 1}),
         ]},
        {"nombre": t("compensacion.nombre"), "prioridad": 150, "ambito": ambito,
         "descripcion": t("compensacion.descripcion"),
         "reglas": [
             _regla(t("c1.nombre"), _y(_c("clase_dia", "eq", "festivo")),
                    {"tipo": "set_field", "campo": "factor", "valor": 1.75},
                    {"tipo": "add_approval_levels", "niveles": 1}),
             _regla(t("c2.nombre"), _y(_c("clase_dia", "eq", "no_laborable")),
                    {"tipo": "set_field", "campo": "factor", "valor": 1.5}),
             _regla(t("c3.nombre"), _y(_c("tipo", "eq", "guardia")),
                    {"tipo": "set_field", "campo": "compensacion", "valor": "pago"}),
             _regla(t("c4.nombre"), _y(_c("tipo", "eq", "guardia"), _c("sustituto", "empty")),
                    _bloquear(t("c4.mensaje"))),
             _regla(t("c5.nombre"), _y(_c("horas", "gt", 2)),
                    {"tipo": "require_justification", "mensaje": t("c5.mensaje")}),
         ]},
    ]
