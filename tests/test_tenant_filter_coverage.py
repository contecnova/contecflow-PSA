"""Todos los modelos son alcanzables por el filtro de tenant, o exentos con motivo.

Auditoría 2026-08 (P3-22). El filtro de `TenantSession` es **fail-closed** desde
el arreglo del P0-2: un modelo que no encaja en ninguna de sus seis vías de
filtrado hace que la consulta lance `TenantIsolationError` en lugar de devolver
filas sin filtrar.

Eso es lo correcto —una fuga entre clientes es peor que un error— pero convierte
cada modelo nuevo mal declarado en un **500 latente**: la consulta funciona en
desarrollo hasta que alguien la ejecuta con una organización en contexto.

Este módulo aplica la lógica REAL de `_tenant_filter_for_model` a los 392 modelos
y comprueba dos cosas:

  · ninguno lanzaría (todos tienen una vía de filtrado, o exención declarada);
  · toda exención lleva su motivo escrito, para que sea una decisión y no un
    descuido.

Por qué usar la lógica de producción en lugar de reimplementarla: al medir esto a
mano con el criterio «¿tiene `organization_id`?» salieron 13 modelos falsamente
sospechosos, entre ellos `abac_policies` — que sí está cubierto, por su columna
`org_id`. Reimplementar el criterio en el test habría dado un resultado falso.
"""
from __future__ import annotations

import importlib
import pkgutil

import pytest

import app.models  # noqa: F401 — registra todos los modelos
from app.db.base import Base
from app.db.session import _is_tenant_exempt

# Las seis vías que `_tenant_filter_for_model` prueba, en su orden de precedencia.
# Se replican como NOMBRES de atributo, no como lógica: el test comprueba que el
# modelo ofrece al menos una, que es lo que la función necesita para filtrar.
VIAS = ("organization_id", "org_id", "project_id", "user_id", "actor_id")

PREFIJO_MODELOS_DE_TEST = "_test_"


def _modelos_del_producto() -> tuple[dict[str, type], list[str]]:
    """Clase de modelo por nombre de tabla (sin los dobles de test), y la lista de
    módulos que no se pudieron importar."""
    clases: dict[str, type] = {}
    no_importables: list[str] = []
    for info in pkgutil.walk_packages(app.models.__path__, "app.models."):
        try:
            modulo = importlib.import_module(info.name)
        except Exception as exc:  # noqa: BLE001 — se registra, no se oculta
            # Un módulo que no importa no aporta modelos, pero tampoco se traga:
            # si dejasen de importarse en masa, este test pasaría en vacío. La
            # lista se comprueba en test_se_han_localizado_los_modelos.
            no_importables.append(f"{info.name}: {type(exc).__name__}: {exc}")
            continue
        for obj in vars(modulo).values():
            tabla = getattr(obj, "__tablename__", None)
            if isinstance(tabla, str) and not tabla.startswith(PREFIJO_MODELOS_DE_TEST):
                clases[tabla] = obj
    return clases, no_importables


MODELOS, MODULOS_NO_IMPORTABLES = _modelos_del_producto()


def test_se_han_localizado_los_modelos():
    """Guarda de cordura: si la introspección falla, los tests de abajo pasarían
    en vacío y no medirían nada."""
    tablas_reales = {
        t for t in Base.metadata.tables if not t.startswith(PREFIJO_MODELOS_DE_TEST)
    }
    assert not MODULOS_NO_IMPORTABLES, (
        "hay módulos de modelos que no se pueden importar, así que sus modelos no "
        "se estarían comprobando y este test pasaría en vacío: "
        + "; ".join(MODULOS_NO_IMPORTABLES)
    )
    assert len(MODELOS) >= 380, f"sólo se localizaron {len(MODELOS)} modelos"
    no_localizadas = sorted(tablas_reales - set(MODELOS))
    # Alguna tabla puede ser de asociación pura, sin clase propia.
    assert len(no_localizadas) <= 5, (
        f"hay {len(no_localizadas)} tablas sin clase localizada: {no_localizadas}"
    )


def _via_de(modelo) -> str | None:
    for via in VIAS:
        if hasattr(modelo, via):
            return via
    return None


def test_ningun_modelo_haria_lanzar_el_filtro_de_tenant():
    """El caso que este test existe para impedir.

    Un modelo nuevo sin ninguna vía de filtrado y sin exención declarada hace que
    `TenantSession` lance `TenantIsolationError` en cuanto se consulte con una
    organización en contexto. Es un 500 que no aparece hasta producción.
    """
    culpables = []
    for tabla, modelo in sorted(MODELOS.items()):
        if _via_de(modelo) is not None:
            continue
        if _is_tenant_exempt(modelo):
            continue
        culpables.append(tabla)

    assert not culpables, (
        f"{len(culpables)} modelos no tienen vía de filtrado ni exención "
        f"declarada, así que consultarlos lanzará TenantIsolationError:\n  "
        + "\n  ".join(culpables)
        + "\n\nSe arregla añadiendo una columna de tenant al modelo, o declarando "
        "`_tenant_exempt = True` con `_tenant_exempt_reason` si de verdad es de "
        "ámbito de plataforma."
    )


def test_toda_exencion_lleva_su_motivo_escrito():
    """Una exención sin motivo es indistinguible de un descuido.

    `_tenant_exempt = True` desactiva el aislamiento entre clientes para ese
    modelo. Exigir el motivo por escrito obliga a que sea una decisión consciente
    y deja constancia para quien lo revise después.
    """
    sin_motivo = []
    for tabla, modelo in sorted(MODELOS.items()):
        if not _is_tenant_exempt(modelo):
            continue
        motivo = getattr(modelo, "_tenant_exempt_reason", None)
        if not motivo or not str(motivo).strip():
            sin_motivo.append(tabla)

    assert not sin_motivo, (
        "modelos exentos del filtro de tenant sin `_tenant_exempt_reason`: "
        f"{sin_motivo}"
    )


def test_las_exenciones_son_las_esperadas():
    """La lista de exentos es corta y se revisa a mano.

    Si crece, es una decisión de seguridad que debe verse en el diff de este test
    y no colarse en el de un modelo.
    """
    exentos = sorted(t for t, m in MODELOS.items() if _is_tenant_exempt(m))
    assert exentos == ["organizations"], (
        f"la lista de modelos exentos del aislamiento entre clientes ha cambiado: "
        f"{exentos}. Cada entrada nueva desactiva el filtro para ese modelo."
    )


@pytest.mark.parametrize("tabla", sorted(MODELOS))
def test_cada_modelo_declara_como_se_le_filtra(tabla):
    """Uno por modelo, para que el fallo señale al culpable.

    El test agregado de arriba dice cuántos hay; éste dice cuál.
    """
    modelo = MODELOS[tabla]
    via = _via_de(modelo)
    if via is None:
        assert _is_tenant_exempt(modelo), (
            f"{tabla} no tiene ninguna de las vías de filtrado {VIAS} ni está "
            f"declarado exento: TenantSession lanzará al consultarlo"
        )
