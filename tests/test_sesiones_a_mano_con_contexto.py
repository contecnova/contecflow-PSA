"""Una sesión creada a mano en la capa API tiene que publicar su contexto.

Auditoría 2026-08 (hallazgo 22). Este defecto apareció **tres veces**, siempre
con la misma forma: un `SessionLocal()` creado a mano en un endpoint, un
WebSocket o un generador, y nadie poblando `db.info`.

Las tres capas de aislamiento de `TenantSession` —`query()`, `execute()` y el
escuchador `do_orm_execute`— salen por la puerta de atrás cuando `info` no trae
`is_superadmin`. Esa rama existe para los trabajos de fondo y los tests
(«sesión no inicializada»), **no** para una petición autenticada.

Los tres, en el orden en que se encontraron:

1. **El WebSocket del chat de colaboración.** Sesión propia, sin contexto.
2. **`get_current_client`**, de la que cuelgan **41 dependencias** del portal.
   Medido: sin contexto, `db.query(Client)` devolvía `['ORG-A', 'ORG-B']`.
3. **Ocho más**, encontrados al buscar el patrón entero: los dos WebSocket de
   BI, el de política de caché de colaboración BI, los dos generadores de SSE
   del chat de IA y los cuatro de `ws.py` —el ticket del portal, las
   notificaciones de usuario, las del portal y el de documentos—. En los de
   notificaciones importa especialmente: la sesión vive lo que dure la conexión
   y sobre ella corre un bucle de sondeo que **lee y escribe**.

## Por qué un ayudante y no tres líneas repetidas

Tres veces el mismo arreglo escrito a mano es una señal. Existe
`publicar_contexto_de_tenant(session, sujeto)` en `app/db/session.py` para que
sea **una línea** — y para que este test pueda buscarla.

## Lo que este test comprueba, y lo que no

Comprueba que **toda función de `app/api/` que crea una sesión a mano publique
el contexto o esté declarada** con su razón, siguiendo un nivel de llamadas
locales: el WebSocket de colaboración crea la sesión y su ayudante
`_abrir_conexion` publica el contexto, y eso es legítimo.

No comprueba que lo haga en el **sitio** correcto: el orden —después de
resolver al sujeto, porque la búsqueda por id todavía no sabe de qué
organización es— no se puede verificar por AST y está escrito en cada sitio.
"""
from __future__ import annotations

import ast
import io
from pathlib import Path

RAIZ = Path("app/api")

#: Cómo se crea una sesión a mano en este repositorio.
_FABRICAS = {"SessionLocal", "worker_db_session"}

#: La llamada que publica el contexto, y las formas de hacerlo a mano.
_PUBLICA = "publicar_contexto_de_tenant"
_A_MANO = "organization_id"

#: Las que están exentas, con su razón. Una entrada aquí es una decisión
#: escrita, no una excepción por inercia.
EXENTAS = {
    # Auditoría 2026-11 (#21): la tarea de fondo de auto-resolución
    # (`_run_job_in_background`) estaba aquí exenta; se movió con su
    # transacción a `services/service_desk/auto_resolucion_operaciones.py`, que
    # este detector (solo `app/api`) no recorre.
    # Revisión 2026-11. Sólo identifica la conexión del flujo de BI (ticket de
    # un uso o JWT): todavía no hay sujeto cuyo contexto publicar, y no lee
    # datos de negocio. Los datos los lee `_organizacion_del_usuario`, que abre
    # su propia sesión y sí publica el contexto.
    ("app/api/v1/endpoints/bi_intelligence.py", "_autorizar_flujo_de_bi"),
}


def _funciones_con_sesion_propia():
    """(fichero, función, ¿publica contexto?) por cada sesión creada a mano."""
    salida = []
    for ruta in sorted(RAIZ.rglob("*.py")):
        if "__pycache__" in ruta.parts:
            continue
        try:
            arbol = ast.parse(io.open(ruta, encoding="utf-8").read())
        except SyntaxError:
            continue

        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            crea, publica, llamadas = _analizar(nodo)

            # El contexto se puede publicar en una funcion a la que esta llama
            # —el WebSocket de colaboracion crea la sesion y su ayudante
            # `_abrir_conexion` publica el contexto—, asi que se siguen las
            # llamadas locales. Un nivel de profundidad basta para la forma que
            # tiene este repositorio y evita razonar sobre recursion.
            if crea and not publica:
                locales = _funciones_del_modulo(arbol)
                for llamada in llamadas:
                    destino = locales.get(llamada)
                    if destino is None:
                        continue
                    _, publica_destino, _ = _analizar(destino)
                    if publica_destino:
                        publica = True
                        break

            if crea:
                salida.append((ruta.as_posix(), nodo.name, publica))
    return salida


def _funciones_del_modulo(arbol: ast.Module) -> dict:
    """Nombre -> nodo, de todas las funciones definidas en el modulo."""
    salida = {}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            salida[nodo.name] = nodo
    return salida


def _analizar(nodo):
    """(¿crea sesion?, ¿publica contexto?, nombres llamados) de una funcion."""
    crea = False
    publica = False
    llamadas = set()
    for hijo in ast.walk(nodo):
        if isinstance(hijo, ast.Call):
            f = hijo.func
            nombre = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")
            llamadas.add(nombre)
            if nombre in _FABRICAS:
                crea = True
            elif nombre == _PUBLICA:
                publica = True
        # `db.info["organization_id"] = ...`
        elif (isinstance(hijo, ast.Subscript)
              and isinstance(hijo.slice, ast.Constant)
              and hijo.slice.value == _A_MANO):
            publica = True
    return crea, publica, llamadas


def test_toda_sesion_creada_a_mano_publica_su_contexto_de_tenant():
    """El guardián. Sin esto, el aislamiento no actúa en esa sesión.

    Si una sesión nueva no lo necesita de verdad —un trabajo de fondo sin
    sujeto—, va a `EXENTAS` **con su razón escrita**, no se relaja la regla.
    """
    culpables = [
        f"{fichero}::{funcion}"
        for fichero, funcion, publica in _funciones_con_sesion_propia()
        if not publica and (fichero, funcion) not in EXENTAS
    ]
    assert not culpables, (
        "estas funciones crean una sesión a mano y no publican el contexto de "
        "tenant, así que `TenantSession` no filtra nada en ella: "
        + "; ".join(culpables))


def test_hay_sesiones_creadas_a_mano_que_vigilar():
    """Que el detector siga midiendo algo.

    Si un refactor quita todas las sesiones creadas a mano, el test de arriba
    pasaría por vacío y dejaría de proteger sin que nadie lo note.
    """
    encontradas = _funciones_con_sesion_propia()
    assert len(encontradas) >= 5, (
        f"sólo se han encontrado {len(encontradas)} sesiones creadas a mano en "
        "la capa API: revisar si el detector sigue funcionando")


def test_las_exentas_siguen_creando_sesion(  ):
    """`EXENTAS` no es una alfombra: cada entrada tiene que seguir existiendo."""
    reales = {(f, n) for f, n, _ in _funciones_con_sesion_propia()}
    obsoletas = sorted(EXENTAS - reales)
    assert not obsoletas, (
        "estas exenciones ya no corresponden a ninguna función que cree sesión: "
        + "; ".join(f"{f}::{n}" for f, n in obsoletas))


# -- El ayudante ------------------------------------------------------------

def test_el_ayudante_publica_las_tres_claves(db):
    """Las tres, y `is_superadmin` es la que decide si el filtro actúa."""
    from app.db.session import publicar_contexto_de_tenant

    class _Usuario:
        id = "u-1"
        organization_id = "ORG-A"
        is_superadmin = False

    publicar_contexto_de_tenant(db, _Usuario())
    assert db.info["organization_id"] == "ORG-A"
    assert db.info["is_superadmin"] is False
    assert db.info["current_user"].id == "u-1"


def test_un_usuario_de_portal_nunca_es_superadmin(db):
    """`ClientUser` no tiene ese atributo, así que el parámetro es explícito.

    Un `getattr(..., False)` daría `False` por casualidad y no por decisión, y
    esa diferencia es la que hace que el filtro se pueda razonar.
    """
    from app.db.session import publicar_contexto_de_tenant

    class _Cliente:
        id = "c-1"
        organization_id = "ORG-B"
        # A propósito: un atributo que, si se leyera, daría lo contrario.
        is_superadmin = True

    publicar_contexto_de_tenant(db, _Cliente(), es_cliente=True)
    assert db.info["is_superadmin"] is False, (
        "un usuario del portal no puede quedar marcado como superadmin de la "
        "plataforma ni por accidente")
    assert db.info["current_client"].id == "c-1"
    assert "current_user" not in db.info


def test_un_superadmin_queda_marcado_como_tal(db):
    from app.db.session import publicar_contexto_de_tenant

    class _Superadmin:
        id = "s-1"
        organization_id = None
        is_superadmin = True

    publicar_contexto_de_tenant(db, _Superadmin())
    assert db.info["is_superadmin"] is True
    assert db.info["organization_id"] is None
