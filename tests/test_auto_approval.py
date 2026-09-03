"""La auto-aprobación y las condiciones de paso del motor de aprobaciones.

Auditoría 2026-08 (P3-18). `_check_auto_approval` era complejidad 18 y decide si
una solicitud se aprueba **sin revisión humana**. Tenía **cero** tests: buscando
`auto_approval`, `_check_auto_approval` o `auto_approve` en todo `tests/` no
aparecía nada.

Es la misma clase de hallazgo que el middleware ABAC muerto y que las reglas de
enrutado de tickets: un control escrito, configurable desde la interfaz, que
decide accesos, y sin una sola prueba que lo ejecute.

Lo que estos tests fijan:

  · que **todo lo dudoso significa «no auto-aprobar»** — sin reglas, con reglas
    ilegibles, con una regla sin condiciones, o con un importe que no se puede
    leer. Especialmente la regla **sin condiciones**: si «ninguna condición»
    contara como «todas cumplidas», una regla mal configurada aprobaría
    absolutamente todo sin que nada fallara;
  · que las condiciones de importe son **estrictas** — un importe igual al
    umbral no cumple ni `amount_lt` ni `amount_gt`;
  · que las condiciones de una regla se combinan con **Y** y no con **O**;
  · la asimetría deliberada entre los dos evaluadores: en la auto-aprobación un
    importe ilegible hace que la regla no aplique, y en la condición de un paso
    deja el paso **activo**. Las dos fallan hacia pedir una firma humana, y si
    alguien las uniformara «para que sean coherentes», una de las dos se
    volvería insegura sin que ningún test lo notara.
"""
from __future__ import annotations

import json
from types import SimpleNamespace


from app.services.approval_engine.requests import (
    _check_auto_approval,
    _step_condition_met,
)


def _flujo(*reglas) -> SimpleNamespace:
    """Un workflow con las reglas dadas, serializadas como las guarda la base."""
    return SimpleNamespace(auto_approval_rules=json.dumps(list(reglas)) if reglas else None)


def _regla(*, etiqueta="regla de prueba", accion="auto_approve", **condiciones) -> dict:
    return {"action": accion, "label": etiqueta, "conditions": condiciones}


def _peticion(contexto=None) -> SimpleNamespace:
    return SimpleNamespace(context=contexto)


# ── Todo lo dudoso significa «no auto-aprobar» ────────────────────────────────

def test_sin_reglas_no_se_auto_aprueba():
    assert _check_auto_approval(_flujo(), _peticion({"amount": 10})) is None


def test_con_reglas_ilegibles_no_se_auto_aprueba():
    """JSON corrupto en la columna. Se registra y no se aprueba nada."""
    flujo = SimpleNamespace(auto_approval_rules="{esto no es json")
    assert _check_auto_approval(flujo, _peticion({"amount": 10})) is None


def test_una_regla_sin_condiciones_no_auto_aprueba_nada():
    """El caso que más importa de todo este fichero.

    Una regla de auto-aprobación con `conditions` vacío es una regla mal
    configurada. Si «ninguna condición» contara como «todas cumplidas»,
    aprobaría **absolutamente todo** sin que nada fallara — y en un motor de
    aprobaciones eso es saltarse el control interno por completo.
    """
    assert _check_auto_approval(_flujo(_regla()), _peticion({"amount": 999_999})) is None


def test_una_regla_que_no_es_de_auto_aprobacion_se_ignora():
    flujo = _flujo(_regla(accion="notify", amount_lt=1_000))
    assert _check_auto_approval(flujo, _peticion({"amount": 10})) is None


def test_un_contexto_que_no_es_diccionario_se_trata_como_vacio():
    """`payload.context` es `Optional[Any]`: puede llegar una lista o una cadena.

    Se trata como contexto vacío, así que `amount` vale 0 y sólo cumplen las
    reglas que un importe de cero cumpliría. No revienta.
    """
    flujo = _flujo(_regla(department="Ventas"))
    assert _check_auto_approval(flujo, _peticion("no soy un dict")) is None
    assert _check_auto_approval(flujo, _peticion(None)) is None


def test_un_importe_ilegible_hace_que_la_regla_no_aplique():
    """El sentido del fallo en la auto-aprobación: si el importe del contexto no
    se puede convertir a número, la regla no aplica y no se auto-aprueba."""
    flujo = _flujo(_regla(amount_lt=1_000))
    assert _check_auto_approval(flujo, _peticion({"amount": "no es un número"})) is None


# ── Los umbrales de importe ───────────────────────────────────────────────────

def test_por_debajo_del_umbral_se_auto_aprueba():
    flujo = _flujo(_regla(etiqueta="gasto menor", amount_lt=1_000))
    assert _check_auto_approval(flujo, _peticion({"amount": 999})) == "gasto menor"


def test_por_encima_del_umbral_no_se_auto_aprueba():
    flujo = _flujo(_regla(amount_lt=1_000))
    assert _check_auto_approval(flujo, _peticion({"amount": 1_001})) is None


def test_un_importe_igual_al_umbral_no_cumple():
    """Estricto a propósito, y en las dos direcciones: si `amount_lt: 1000`
    admitiera exactamente 1.000, el límite documentado y el real no coincidirían
    y alguien acabaría aprobando un gasto de justo el tope sin firma."""
    assert _check_auto_approval(_flujo(_regla(amount_lt=1_000)),
                                _peticion({"amount": 1_000})) is None
    assert _check_auto_approval(_flujo(_regla(amount_gt=1_000)),
                                _peticion({"amount": 1_000})) is None


def test_el_umbral_inferior_funciona_al_reves():
    flujo = _flujo(_regla(etiqueta="gasto grande", amount_gt=1_000))
    assert _check_auto_approval(flujo, _peticion({"amount": 1_001})) == "gasto grande"
    assert _check_auto_approval(flujo, _peticion({"amount": 999})) is None


def test_un_rango_combina_los_dos_umbrales():
    """Entre 100 y 1.000, ambos excluidos."""
    flujo = _flujo(_regla(etiqueta="tramo medio", amount_gt=100, amount_lt=1_000))
    assert _check_auto_approval(flujo, _peticion({"amount": 500})) == "tramo medio"
    assert _check_auto_approval(flujo, _peticion({"amount": 50})) is None
    assert _check_auto_approval(flujo, _peticion({"amount": 5_000})) is None


def test_sin_importe_en_el_contexto_cuenta_como_cero():
    """`ctx.get("amount", 0)`. Con `amount_lt` se cumple, con `amount_gt` no."""
    assert _check_auto_approval(_flujo(_regla(etiqueta="x", amount_lt=1_000)),
                                _peticion({})) == "x"
    assert _check_auto_approval(_flujo(_regla(amount_gt=1_000)),
                                _peticion({})) is None


# ── Igualdades y combinación ──────────────────────────────────────────────────

def test_el_departamento_tiene_que_coincidir_exacto():
    flujo = _flujo(_regla(etiqueta="solo ventas", department="Ventas"))
    assert _check_auto_approval(flujo, _peticion({"department": "Ventas"})) == "solo ventas"
    assert _check_auto_approval(flujo, _peticion({"department": "ventas"})) is None
    assert _check_auto_approval(flujo, _peticion({"department": "Compras"})) is None
    assert _check_auto_approval(flujo, _peticion({})) is None


def test_las_condiciones_de_una_regla_se_combinan_con_y():
    """Y no con O. Si se combinaran con O, una regla de «importe pequeño **y**
    departamento de ventas» aprobaría cualquier importe del resto de
    departamentos."""
    flujo = _flujo(_regla(etiqueta="ambas", amount_lt=1_000, department="Ventas"))
    assert _check_auto_approval(flujo, _peticion(
        {"amount": 500, "department": "Ventas"})) == "ambas"
    assert _check_auto_approval(flujo, _peticion(
        {"amount": 500, "department": "Compras"})) is None
    assert _check_auto_approval(flujo, _peticion(
        {"amount": 5_000, "department": "Ventas"})) is None


def test_las_cuatro_condiciones_a_la_vez():
    flujo = _flujo(_regla(etiqueta="todas", amount_gt=100, amount_lt=1_000,
                          department="Ventas", category="viajes"))
    completo = {"amount": 500, "department": "Ventas", "category": "viajes"}
    assert _check_auto_approval(flujo, _peticion(completo)) == "todas"
    for clave, valor in (("amount", 5_000), ("department", "Compras"),
                         ("category", "material")):
        assert _check_auto_approval(flujo, _peticion({**completo, clave: valor})) is None, clave


def test_la_primera_regla_que_cumple_es_la_que_manda():
    """Se recorren en orden y se devuelve la primera. Importa porque la etiqueta
    acaba en el registro de auditoría como razón de la aprobación."""
    flujo = _flujo(
        _regla(etiqueta="primera", amount_lt=1_000),
        _regla(etiqueta="segunda", amount_lt=2_000),
    )
    assert _check_auto_approval(flujo, _peticion({"amount": 500})) == "primera"


def test_una_regla_sin_etiqueta_tiene_una_por_defecto():
    """La etiqueta se escribe en el registro de auditoría, así que no puede
    quedar vacía."""
    flujo = SimpleNamespace(auto_approval_rules=json.dumps(
        [{"action": "auto_approve", "conditions": {"amount_lt": 1_000}}]
    ))
    assert _check_auto_approval(flujo, _peticion({"amount": 1})) == "auto-rule"


# ── La asimetría con las condiciones de paso ──────────────────────────────────

def _paso(condicion=None, ident="paso-1"):
    return SimpleNamespace(
        step_condition=json.dumps(condicion) if condicion is not None else None,
        id=ident,
    )


def _solicitud(resumen=None):
    return SimpleNamespace(
        entity_summary=json.dumps(resumen) if resumen is not None else None,
        id="req-1",
    )


def test_un_paso_sin_condicion_esta_activo():
    assert _step_condition_met(_paso(), _solicitud()) is True


def test_un_paso_con_condicion_ilegible_esta_activo():
    """Fallo seguro en esta dirección: un paso activo exige aprobación."""
    paso = SimpleNamespace(step_condition="{no es json", id="paso-x")
    assert _step_condition_met(paso, _solicitud({"amount": 10})) is True


def test_un_resumen_ilegible_deja_el_contexto_vacio():
    solicitud = SimpleNamespace(entity_summary="{no es json", id="req-x")
    assert _step_condition_met(_paso({"amount_lt": 1_000}), solicitud) is True


def test_la_condicion_de_paso_filtra_por_importe():
    paso = _paso({"amount_gt": 1_000})
    assert _step_condition_met(paso, _solicitud({"amount": 5_000})) is True
    assert _step_condition_met(paso, _solicitud({"amount": 500})) is False


def test_la_condicion_de_paso_filtra_por_departamento_y_categoria():
    paso = _paso({"department": "Ventas", "category": "viajes"})
    assert _step_condition_met(paso, _solicitud(
        {"department": "Ventas", "category": "viajes"})) is True
    assert _step_condition_met(paso, _solicitud(
        {"department": "Compras", "category": "viajes"})) is False


def test_los_dos_evaluadores_fallan_hacia_pedir_firma_humana():
    """La asimetría, aislada en un solo test para que se lea de una vez.

    El mismo dato ilegible —un importe que no es un número— produce respuestas
    opuestas, y las dos son la segura en su contexto:

      · en la auto-aprobación devuelve None: **no** se salta la revisión;
      · en la condición de paso devuelve True: el paso **sigue** activo y hay
        que aprobarlo.

    Si alguien uniformara las dos «para que sean coherentes», una de ellas
    pasaría a fallar hacia aprobar sin firma. Este test lo impide.
    """
    ilegible = {"amount": "no es un número"}

    assert _check_auto_approval(_flujo(_regla(amount_lt=1_000)),
                                _peticion(ilegible)) is None
    assert _step_condition_met(_paso({"amount_lt": 1_000}),
                               _solicitud(ilegible)) is True


# ── Que la tabla y el esquema no se separen ───────────────────────────────────

def test_las_condiciones_del_esquema_estan_todas_implementadas():
    """`AutoApprovalRuleConditions` declara las condiciones que la interfaz
    ofrece configurar. Una declarada y no implementada se ignoraría en silencio:
    el administrador la configuraría, la regla aprobaría sin comprobarla, y nada
    fallaría. Es exactamente el patrón que atraviesa esta auditoría.
    """
    from app.schemas.approvals import AutoApprovalRuleConditions
    from app.services.approval_engine.requests import (
        _COMPARACIONES_DE_IMPORTE, _IGUALDADES,
    )

    declaradas = set(AutoApprovalRuleConditions.model_fields)
    implementadas = set(_COMPARACIONES_DE_IMPORTE) | set(_IGUALDADES)
    assert declaradas == implementadas, (
        f"declaradas sin implementar: {declaradas - implementadas}; "
        f"implementadas sin declarar: {implementadas - declaradas}"
    )
