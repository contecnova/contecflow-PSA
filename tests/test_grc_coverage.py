"""Límites conocidos del módulo GRC (auditoría 2026-08, hallazgos 27 y 28).

La versión anterior de este fichero constataba que la matriz de permisos NO se
aplicaba y que cubría 15 de 126 dominios. Las dos cosas están resueltas: la
matriz se aplica (ver tests/test_grc_enforcement.py, que lo prueba por HTTP) y la
cobertura se deriva de las rutas, así que alcanza todos los dominios no exentos.

Lo que queda aquí es la parte de SoD que sigue siendo parcial. Está escrito para
que la limitación sea visible y para que el día que se cierre, el test avise en
lugar de quedarse callado.
"""
from __future__ import annotations

import pathlib

import pytest

from app.api.v1.endpoints.grc import DEFAULT_MATRIX

REPO = pathlib.Path(__file__).resolve().parents[1]


# ── La SoD que SÍ se aplica ───────────────────────────────────────────────────

def test_el_motor_de_aprobaciones_bloquea_la_autoaprobacion():
    """La regla nuclear de SoD: el solicitante no aprueba su propia solicitud.

    Es la única regla de SoD que impide una acción, y vive en el motor de
    aprobaciones, no en la tabla SodRule.
    """
    f = REPO / "app" / "services" / "approval_engine" / "requests.py"
    txt = f.read_text(encoding="utf-8")
    assert "req.requested_by == current_user.id" in txt, (
        "desapareció la comprobación de auto-aprobación: es la única regla SoD "
        "que se aplica de verdad."
    )
    assert "SoD" in txt, "el 403 de auto-aprobación debe seguir citando SoD"


# ── El límite que queda abierto ───────────────────────────────────────────────

def test_las_reglas_sod_entre_modulos_distintos_no_se_evaluan():
    """Limitación conocida, no un contrato a preservar.

    El registrador único (`grc_sod.regla_de_autoaprobacion`, revisión GRC
    2026-11b) exige `module_b == module_a` (la entidad o su módulo GRC) y
    `aprobar` en el segundo lado, así que una regla como "no puede crear
    facturas y aprobar gastos" (módulos distintos) nunca se evalúa en tiempo de
    ejecución; sólo la ve la comprobación estática `/grc/sod-check`.

    Si este test falla, alguien generalizó la evaluación: buena noticia. Actualiza
    el fichero y la cabecera de app/api/v1/endpoints/grc.py.
    """
    f = REPO / "app" / "services" / "grc_sod.py"
    txt = f.read_text(encoding="utf-8")
    assert "SodRule.module_b == SodRule.module_a" in txt and 'SodRule.action_b == "aprobar"' in txt, (
        "cambió la consulta de SodRule; comprueba si ahora se evalúan reglas "
        "personalizadas entre módulos y actualiza este fichero."
    )
    base = (REPO / "app" / "services" / "approval_engine" / "_base.py").read_text(encoding="utf-8")
    assert base.count("record_self_approval_violation_for_request(") >= 2, (
        "la bandeja y las rutas de aprobación directa deben registrar con el mismo registrador"
    )


# ── Coherencia de lo declarado ────────────────────────────────────────────────

@pytest.mark.parametrize("rol", sorted(DEFAULT_MATRIX))
def test_la_matriz_por_defecto_declara_las_seis_acciones(rol):
    acciones = {"ver", "crear", "editar", "eliminar", "aprobar", "exportar"}
    for modulo, perms in DEFAULT_MATRIX[rol].items():
        faltan = acciones - set(perms)
        assert not faltan, f"{rol}/{modulo} no declara: {sorted(faltan)}"


def test_la_matriz_por_defecto_da_todo_al_admin():
    """El rol admin no debe quedar restringido por la semilla.

    Con la matriz ya aplicada, una casilla en False para admin sería una
    denegación real en producción.
    """
    for modulo, perms in DEFAULT_MATRIX["admin"].items():
        negadas = [a for a, ok in perms.items() if not ok]
        assert not negadas, f"admin tiene denegado {modulo}: {negadas}"


def test_check_permission_ya_no_existe():
    """Se retiró al conectar la matriz: era código muerto con docstring falso.

    Decía "Used by other API endpoints to enforce GRC" y tenía cero
    invocaciones. La aplicación real la hace `enforce_grc_matrix` leyendo la fila
    directamente. Si alguien la reintroduce, habrá dos caminos de decisión con
    semánticas distintas (uno cae a DEFAULT_MATRIX, el otro trata la ausencia de
    fila como permisiva).
    """
    import app.api.v1.endpoints.grc as grc_mod

    assert not hasattr(grc_mod, "check_permission"), (
        "check_permission ha vuelto: la aplicación de la matriz debe tener un "
        "único camino (enforce_grc_matrix)."
    )
