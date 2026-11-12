"""La capa API no accede a la base de datos. Cero, y que siga en cero.

Auditoría 2026-08, hallazgo 22 — **cerrado**. Medido con
`scripts/audit_db_access_in_api.py`, que lo cuenta por árbol de sintaxis sobre
`app/api/` entera:

```
antes de la tanda 1 (collaboration)   257 puntos de acceso en 41 ficheros
al empezar la última jornada           46 en 23
ahora                                   0 en 0
```

Quedan **109 fronteras de transacción** —`commit`, `rollback`, `close` y
`refresh`—, y quedan a propósito: no son acceso a datos. `refresh` es releer la
fila que el servicio acaba de devolver para recoger lo que pone la base, y va
pegado a un `commit`; moverlo al servicio obligaría a que el servicio confirme,
que es exactamente lo contrario de lo que estas tandas hicieron.

## Por qué esto es un test y no una nota en un documento

El número bajó de 257 a 0 en varias tandas, y en cada una **mover el acceso
funcionó como detector**: salieron el sellado de la columna de tenant, el portal
corriendo sin aislamiento en 41 dependencias, las credenciales de e-firma como
valor global, `approve-baseline` que no podía aprobar nada, y los dos
enumerados con el mismo nombre. Sin un guardián, el primer endpoint nuevo que
consulte la base directamente reabre la puerta — y no se notaría, porque un
`db.query()` en un endpoint funciona perfectamente.

## Qué cuenta como acceso y qué no

Lo decide el script, no este test: se importa de ahí a propósito, para que la
regla viva en un solo sitio y el guardián no pueda divergir de la medición.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RUTA_DEL_SCRIPT = Path("scripts/audit_db_access_in_api.py")


def _detector():
    """Carga el script de medición como módulo.

    Se usa **el mismo** código que mide, no una copia: si la regla cambia, el
    guardián cambia con ella. Dos implementaciones de la misma pregunta es cómo
    aparecieron las dos puertas del marketplace.
    """
    if not RUTA_DEL_SCRIPT.exists():
        pytest.skip("no hay scripts/ en este árbol de trabajo")
    spec = importlib.util.spec_from_file_location(
        "_audit_db_access", RUTA_DEL_SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["_audit_db_access"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def test_la_capa_api_no_accede_a_la_base_de_datos():
    """Tolerancia cero. Si esto falla, la consulta va a un servicio.

    El mensaje da fichero y línea exactos porque es lo único que hace falta
    para arreglarlo: mover la consulta y llamarla desde el endpoint.
    """
    datos = _detector().medir()

    culpables = []
    for fichero, info in datos["ficheros"].items():
        for punto in info["puntos"]:
            if punto["clase"] == "acceso":
                culpables.append(
                    f"{fichero}:{punto['linea']} db.{punto['metodo']}()")

    assert not culpables, (
        "la capa API ha vuelto a acceder a la base de datos directamente. "
        "Mueve la consulta a un servicio y llámala desde el endpoint — y "
        "aprovecha para preguntarte de quién son las filas que devuelve, que "
        "es lo que destapó la mitad de los hallazgos de esta auditoría:\n  "
        + "\n  ".join(culpables))


def test_las_transacciones_viven_en_el_servicio():
    """Auditoria 2026-11 (#21): decision cambiada a proposito.

    Antes el diseño era "el servicio prepara y el endpoint confirma" (>50
    commits en app/api). Se movieron todos al servicio para que los workers y la
    orquestacion reutilicen la misma unidad de trabajo; lo vigila
    tests/test_sin_commits_en_la_api.py. Aqui solo quedan rollback/close de
    tareas de fondo y streaming.
    """
    datos = _detector().medir()
    assert datos["total_transaccion"] < 50, datos["total_transaccion"]


def test_el_detector_mide_algo_de_verdad():
    """Que el guardián no pase por vacío.

    Si `app/api/` desapareciera o el script dejara de encontrar ficheros, el
    test de arriba pasaría sin comprobar nada.
    """
    datos = _detector().medir()
    assert len(datos["ficheros"]) > 10, (  # 2026-11: menos tras sacar los commits
        f"el detector sólo ve {len(datos['ficheros'])} ficheros con acceso o "
        "transacciones en app/api: revisar si sigue funcionando")
