"""El catálogo de métricas de alertas inteligentes se resuelve por completo.

Auditoría 2026-08 (P3-18). `_fetch_metric_series` era la función más compleja de
la solución con diferencia: complejidad ciclomática **247** en 945 líneas, cuando
la siguiente del proyecto está en 67. Eran 55 `if metric_key == ...` secuenciales
al mismo nivel, cada uno con su propia consulta y su propio `return`: una tabla de
despacho escrita como una única función.

Estos tests son la red que permite reorganizarla sin cambiar ni un valor. Fijan
las propiedades que deben cumplirse antes y después:

  · las 133 claves del catálogo se resuelven, ninguna lanza;
  · todas devuelven una serie de la MISMA longitud (se comparan entre sí en los
    paneles: longitudes distintas descuadrarían las gráficas);
  · ninguna cae por descuido en un camino vacío por defecto — que es el fallo que
    esconde un despacho por cadenas de `if`, y el mismo patrón que dejó muerto el
    endpoint `/analytics/adhoc` y el reconocimiento ASC 606.

Y fijan la propiedad estructural que evita que el catálogo y el código vuelvan a
separarse: `SUPPORTED_METRICS` y las claves atendidas deben coincidir exactamente.
"""
from __future__ import annotations

import pytest

from app.services.bi_smart_alerts.constants import SUPPORTED_METRICS
from app.services.bi_smart_alerts.metrics import _fetch_metric_series

CLAVES = sorted(SUPPORTED_METRICS)


def test_el_catalogo_no_esta_vacio():
    """Guarda de cordura: si el catálogo se vacía, los tests de abajo pasarían
    en vacío y no medirían nada."""
    assert len(CLAVES) >= 130, f"el catálogo ha adelgazado a {len(CLAVES)} claves"


@pytest.mark.parametrize("clave", CLAVES)
def test_cada_clave_del_catalogo_devuelve_una_serie(clave, db):
    """Ninguna de las 133 claves puede lanzar ni devolver algo que no sea serie.

    Con 55 ramas secuenciales, una clave del catálogo sin rama caía al final de
    la función. Este test recorre el catálogo entero, así que ese caso ya no puede
    pasar desapercibido.
    """
    serie = _fetch_metric_series(db, clave, None)
    assert isinstance(serie, list), f"{clave} no devuelve una lista"
    assert serie, f"{clave} devuelve una serie vacía"
    assert all(isinstance(v, (int, float)) for v in serie), (
        f"{clave} devuelve valores que no son numéricos"
    )


def test_todas_las_series_tienen_la_misma_longitud(db):
    """Los paneles comparan métricas entre sí: longitudes distintas las
    descuadran, y el desajuste no da error, sólo gráficas mal alineadas."""
    longitudes = {}
    for clave in CLAVES:
        longitudes.setdefault(len(_fetch_metric_series(db, clave, None)), []).append(clave)
    assert len(longitudes) == 1, (
        "hay series de distinta longitud: "
        + "; ".join(f"{n} valores → {v[:4]}" for n, v in longitudes.items())
    )


def test_una_clave_desconocida_no_lanza_y_devuelve_serie_neutra(db):
    """Una regla guardada con una métrica que ya se retiró no puede tumbar el
    motor de alertas: debe degradar."""
    serie = _fetch_metric_series(db, "metrica_que_no_existe_xyz", None)
    assert isinstance(serie, list)
    assert all(v == 0.0 for v in serie), (
        "una clave desconocida debería dar una serie a cero, no valores inventados"
    )


# ── Catálogo y código no pueden separarse ─────────────────────────────────────

def test_el_catalogo_y_las_claves_atendidas_coinciden():
    """Sin este test, añadir una métrica al catálogo sin implementarla —o al
    revés— pasa desapercibido: la clave sin rama devuelve ceros y el panel
    presenta una línea plana en vez de un error."""
    from app.services.bi_smart_alerts.metrics import claves_atendidas

    atendidas = set(claves_atendidas())
    catalogo = set(SUPPORTED_METRICS)

    assert catalogo - atendidas == set(), (
        "claves en SUPPORTED_METRICS que nadie resuelve: "
        f"{sorted(catalogo - atendidas)}"
    )
    assert atendidas - catalogo == set(), (
        "claves resueltas que no están en el catálogo, así que la interfaz no las "
        f"ofrece: {sorted(atendidas - catalogo)}"
    )
