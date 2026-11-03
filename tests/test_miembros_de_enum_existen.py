"""Ningún sitio de `app/` usa un miembro de enumerado que no existe.

Auditoría 2026-08. Este guardián sale de un hallazgo concreto y de la pregunta
que dejó abierta.

## El hallazgo

Hay **dos** clases `ChangeStatus` en el repositorio, con valores distintos: la
del modelo tiene `cab_review`, y un enumerado local de un servicio —que no usaba
nadie— tenía `in_approval`. Tres consumidores importaban la del modelo y
escribían `ChangeStatus.in_approval`:

* el endpoint que puntúa el riesgo de los cambios pendientes respondía **500
  siempre** y nunca puntuó ninguno;
* el panel del CAB **no listaba ningún cambio en revisión del CAB**;
* la tarea programada que corre cada 10 minutos **fallaba en cada tic**,
  dejando una línea de log.

## La pregunta general, y lo que respondió

«¿Cuántos más hay?» Un detector por AST sobre `app/` encontró **seis más**, en
tres enumerados distintos, y todos en caminos que se ejecutan de verdad:

| dónde | qué usaba | qué pasaba |
|---|---|---|
| `inbound_email_service` | `TicketStatus.open` | **cada correo entrante** reventaba: no se creaba el ticket |
| `multichannel_service` | `TicketStatus.open` | lo mismo con **cada SMS entrante** |
| `asset_service` | `TicketStatus.open` | el ticket de renovación de un activo, roto |
| `bookings_service` ×2 | `OpportunityStage.closed_won` | **convertir una oportunidad ganada en proyecto**, roto en su primera línea útil |
| `metrics/okr_nps` | `OKRStatus.at_risk` | atrapado por un `except`: la métrica de progreso de OKR devolvía **lista vacía** en silencio |

Los valores correctos eran `new` (que además es el `default` de la columna y lo
que usan las otras tres vías de creación de tickets), `won`, y —para el de
OKR— sólo `active`, porque «en riesgo» no es un estado que exista ni una columna
que se pueda consultar.

## Por qué es un test y no una revisión

Es un `AttributeError` en un camino que nadie ejercita: no lo ve un linter
—`ruff` no resuelve el enumerado—, no lo ve el tipado, y no lo ve la suite si
ese camino no tiene test. Lo único que lo caza sistemáticamente es preguntarle
al AST.

## Dos reglas, y por qué hacen falta las dos

* **La regla de la unión** (`test_ningun_acceso_a_un_miembro_de_enum_que_no_existe`):
  un miembro tiene que existir en **alguna** definición de ese nombre. No tiene
  falsos positivos, así que puede ser de tolerancia cero, y es la que encontró
  los seis de la tabla.
* **La regla por import**
  (`test_ningun_fichero_usa_un_miembro_que_su_propio_import_no_tiene`): el
  miembro tiene que existir en la definición que **ese fichero importa de
  verdad**. Es la estricta, y es la única que puede cazar el caso de
  `ChangeStatus` — porque el enumerado muerto **sí** tenía `in_approval`, así
  que para la regla de la unión aquellos tres sitios eran correctos.

**Comprobado que discriminan, y con precisión sobre cuál coge qué.** Ejecutados
contra el código anterior en un `git worktree`:

* la regla de la unión encuentra **los seis** de la tabla — no puede coger los
  de `ChangeStatus`, porque el enumerado muerto **sí** tenía `in_approval`;
* la regla por import encuentra **los nueve**.

Y hubo que medirlo dos veces. Escribí primero que este fichero cogía los nueve
(falso: la unión coge seis), y después que la regla por import cogía los tres de
`ChangeStatus` (también falso: su primera versión no seguía las reexportaciones
de los `__init__`, así que se callaba precisamente en los casos que motivaron el
test, y sólo cogía tres — los de `bookings_service` y el de OKR). Con las
reexportaciones resueltas coge los nueve. **Una afirmación sobre qué caza un
detector no vale hasta ejecutarla contra el código defectuoso.**
"""
from __future__ import annotations

import ast
import io
from collections import defaultdict
from pathlib import Path

RAIZ = Path("app")


def _miembros_declarados(nodo: ast.ClassDef) -> set[str]:
    """Los nombres asignados o definidos directamente en el cuerpo de la clase."""
    nombres: set[str] = set()
    for hijo in nodo.body:
        if isinstance(hijo, ast.Assign):
            for destino in hijo.targets:
                if isinstance(destino, ast.Name):
                    nombres.add(destino.id)
        elif isinstance(hijo, ast.AnnAssign) and isinstance(hijo.target, ast.Name):
            nombres.add(hijo.target.id)
        elif isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nombres.add(hijo.name)
    return nombres


def _hereda_de_enum(nodo: ast.ClassDef) -> bool:
    for base in nodo.bases:
        nombre = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
        if "Enum" in str(nombre):
            return True
    return False


def _arboles() -> dict[str, ast.Module]:
    salida = {}
    for ruta in sorted(RAIZ.rglob("*.py")):
        if "__pycache__" in ruta.parts:
            continue
        try:
            salida[ruta.as_posix()] = ast.parse(
                io.open(ruta, encoding="utf-8").read())
        except SyntaxError:
            # Un fichero que no compila es problema de otro test.
            continue
    return salida


def _enumerados(arboles) -> dict[str, set[str]]:
    """Nombre de enumerado -> unión de sus miembros en todas sus definiciones.

    Se usa la unión a propósito: así este test sólo señala lo que **ninguna**
    definición tiene, que es un error seguro. Los homónimos con miembros
    distintos los cubre el test de abajo.
    """
    por_nombre: dict[str, set[str]] = defaultdict(set)
    for arbol in arboles.values():
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ClassDef) and _hereda_de_enum(nodo):
                por_nombre[nodo.name] |= _miembros_declarados(nodo)
    return dict(por_nombre)


def test_ningun_acceso_a_un_miembro_de_enum_que_no_existe():
    arboles = _arboles()
    enums = _enumerados(arboles)
    assert enums, "no se ha encontrado ningún enumerado: el detector está roto"

    culpables = []
    for fichero, arbol in arboles.items():
        for nodo in ast.walk(arbol):
            if not (isinstance(nodo, ast.Attribute)
                    and isinstance(nodo.value, ast.Name)):
                continue
            nombre = nodo.value.id
            if nombre not in enums:
                continue
            if nodo.attr.startswith("_") or nodo.attr in enums[nombre]:
                continue
            culpables.append(
                f"{fichero}:{nodo.lineno} -> {nombre}.{nodo.attr}")

    assert not culpables, (
        "estos sitios acceden a un miembro que ninguna definición de ese "
        "enumerado tiene, así que revientan con AttributeError al "
        "ejecutarse: " + "; ".join(culpables))


def test_los_enumerados_homonimos_estan_declarados_aqui():
    """Los nombres de enumerado definidos más de una vez, con miembros distintos.

    No falla por existir: fallar por eso obligaría a renombrar clases de dominios
    que no se hablan entre sí, y eso es una decisión, no un defecto. Lo que hace
    es **fijar la lista**: si aparece un homónimo nuevo, este test lo dice, y
    entonces hay que mirar si alguien está importando el que no toca.

    `ChangeStatus` **no** está en la lista a propósito: su segundo enumerado
    estaba muerto y se quitó, que es lo que había que hacer con él.
    """
    arboles = _arboles()
    por_nombre: dict[str, list[tuple[str, frozenset]]] = defaultdict(list)
    for fichero, arbol in arboles.items():
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ClassDef) and _hereda_de_enum(nodo):
                por_nombre[nodo.name].append(
                    (fichero, frozenset(_miembros_declarados(nodo))))

    homonimos = {
        nombre: defs for nombre, defs in por_nombre.items()
        if len(defs) > 1 and len({m for _, m in defs}) > 1
    }

    # Los conocidos, revisados uno a uno en la auditoría de 2026-08. De cada uno
    # se comprobó que **ningún fichero usa un miembro que su propio import no
    # tiene**, que es lo que convierte un homónimo en defecto.
    CONOCIDOS = {
        # Dos dominios que no se hablan: la validación de un entregable en el
        # portal de cliente y el estado de una fila RACI.
        "UATStatus",
        # `models/service_desk/_enums.py` -> standard, normal, emergency: es el
        # de la columna. El del servicio de automatización añade `pilot` y
        # `misc.py` lo importa **con alias** (`ChangeAutomationType`), derivando
        # su valor del de la columna y sin escribirlo nunca de vuelta.
        #
        # Anotado y no tocado: `pilot` no lo usa nadie y la columna no puede
        # almacenarlo, así que es un valor inerte. Quitarlo es una decisión de
        # producto —¿existe el concepto «cambio piloto»?—, no un arreglo.
        "ChangeType",
    }

    nuevos = sorted(set(homonimos) - CONOCIDOS)
    assert not nuevos, (
        "hay enumerados homónimos con miembros distintos que no estaban "
        "declarados. Revisar si alguien importa el que no toca —así apareció "
        "el defecto de ChangeStatus— y añadirlos aquí si son legítimos: "
        + "; ".join(
            f"{n} en {[f for f, _ in homonimos[n]]}" for n in nuevos))


def test_el_estado_inicial_de_un_ticket_es_el_mismo_en_todas_las_vias():
    """Tres vías usaban `new` y tres `open`, que no existe.

    La asimetría entre sitios que hacen lo mismo es la que destapó estos
    defectos, así que se fija: todas las creaciones de ticket que fijan el
    estado a mano usan el mismo, y ese es el `default` de la columna.
    """
    from app.models.service_desk import Ticket, TicketStatus

    columna = Ticket.__table__.columns["status"]
    inicial = columna.default.arg if columna.default else None
    assert inicial == TicketStatus.new, (
        f"el default de la columna ha cambiado a {inicial}: revisar las vías "
        "de creación de tickets")

    culpables = []
    for fichero, arbol in _arboles().items():
        if "/db/seed_parts/" in fichero:
            continue  # la siembra crea tickets en todos los estados a proposito
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            if not (isinstance(nodo.func, ast.Name) and nodo.func.id == "Ticket"):
                continue
            for kw in nodo.keywords:
                if kw.arg != "status":
                    continue
                valor = kw.value
                nombre = getattr(valor, "attr", None) if isinstance(
                    valor, ast.Attribute) else None
                if nombre and nombre != "new":
                    culpables.append(
                        f"{fichero}:{nodo.lineno} -> status=TicketStatus.{nombre}")

    assert not culpables, (
        "estas creaciones de ticket fijan un estado inicial distinto de `new`: "
        + "; ".join(culpables))


def _origen_del_import(arbol: ast.Module, nombre: str) -> str | None:
    """De qué módulo importa este fichero la clase `nombre`, si lo importa."""
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.module:
            for alias in nodo.names:
                if (alias.asname or alias.name) == nombre:
                    return nodo.module
    return None


def _modulo_de(fichero: str) -> str:
    """`app/x/y.py` -> `app.x.y`; un `__init__.py` es su propio paquete."""
    modulo = fichero[:-3].replace("/", ".")
    if modulo.endswith(".__init__"):
        modulo = modulo[: -len(".__init__")]
    return modulo


def _resolver_absoluto(modulo_actual: str, nodo: ast.ImportFrom) -> str:
    """El módulo absoluto de un `from ... import`, resolviendo los relativos."""
    if not nodo.level:
        return nodo.module or ""
    partes = modulo_actual.split(".")
    # Un `from .x import y` dentro de `a.b` (paquete) apunta a `a.b.x`; dentro
    # de `a.b.c` (módulo), a `a.b.x`. `_arboles` normaliza los `__init__`, así
    # que aquí un paquete ya llega como `a.b`.
    base = partes[: len(partes) - (nodo.level - 1)] if nodo.level > 1 else partes
    return ".".join(base + ([nodo.module] if nodo.module else []))


def test_ningun_fichero_usa_un_miembro_que_su_propio_import_no_tiene():
    """La regla estricta: resuelve de dónde viene cada enumerado de verdad.

    Es la única que puede cazar el caso de `ChangeStatus`, porque el enumerado
    muerto sí tenía `in_approval` y para la regla de la unión aquellos tres
    sitios parecían correctos.

    **Sigue las reexportaciones, incluidas las de `import *`.** Las dos
    primeras versiones de este test no cazaban ni `ChangeStatus` ni
    `TicketStatus`: en este repositorio los enumerados del Service Desk se
    definen en `app/models/service_desk/_enums.py` y se importan desde
    `app.models.service_desk`, que es un paquete que los reexporta **con
    `from ... import *`**. Sin seguir esa cadena la regla decía «no puedo
    resolverlo» y se callaba justamente en los casos que motivaron el test.

    Lo que sigue fuera de alcance, y queda dicho: un `import app.models.x`
    seguido de `x.Enum.miembro`. La regla de la unión cubre ese hueco para todo
    lo que ninguna definición tiene.
    """
    arboles = _arboles()

    # 1. Dónde se DEFINE cada enumerado.
    definiciones: dict[str, dict[str, set[str]]] = defaultdict(dict)
    for fichero, arbol in arboles.items():
        modulo = _modulo_de(fichero)
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ClassDef) and _hereda_de_enum(nodo):
                definiciones[nodo.name][modulo] = _miembros_declarados(nodo)

    # 2. Qué nombres REEXPORTA cada módulo, y desde dónde. Se distinguen las
    #    reexportaciones con nombre de las de `import *`, porque los enumerados
    #    del Service Desk llegan por la segunda vía: su paquete hace
    #    `from app.models.service_desk._enums import *`.
    reexportaciones: dict[tuple[str, str], str] = {}
    estrellas: dict[str, list[str]] = defaultdict(list)
    for fichero, arbol in arboles.items():
        modulo = _modulo_de(fichero)
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.ImportFrom):
                continue
            origen = _resolver_absoluto(modulo, nodo)
            if not origen:
                continue
            for alias in nodo.names:
                if alias.name == "*":
                    estrellas[modulo].append(origen)
                else:
                    reexportaciones[(modulo, alias.asname or alias.name)] = origen

    def _miembros_reales(nombre: str, modulo: str) -> set[str] | None:
        """Los miembros de `nombre` tal como lo ve quien lo importa de `modulo`.

        Sigue, en este orden: la definición en el propio módulo, la
        reexportación con nombre, y las de `import *`. Lo primero que resuelve
        gana, que es lo que hace el intérprete.
        """
        pendientes = [modulo]
        visto: set[str] = set()
        while pendientes:
            actual = pendientes.pop(0)
            if not actual or actual in visto:
                continue
            visto.add(actual)

            propios = definiciones.get(nombre, {}).get(actual)
            if propios is not None:
                return propios

            siguiente = reexportaciones.get((actual, nombre))
            if siguiente:
                pendientes.append(siguiente)
            pendientes.extend(estrellas.get(actual, []))
        return None

    culpables = []
    for fichero, arbol in arboles.items():
        for nombre in definiciones:
            modulo = _origen_del_import(arbol, nombre)
            if modulo is None:
                continue
            miembros = _miembros_reales(nombre, modulo)
            if miembros is None:
                continue
            for nodo in ast.walk(arbol):
                if (isinstance(nodo, ast.Attribute)
                        and isinstance(nodo.value, ast.Name)
                        and nodo.value.id == nombre
                        and not nodo.attr.startswith("_")
                        and nodo.attr not in miembros):
                    culpables.append(
                        f"{fichero}:{nodo.lineno} usa {nombre}.{nodo.attr} pero "
                        f"importa {nombre} de {modulo}, que no lo tiene")

    assert not culpables, (
        "estos sitios usan un miembro que la definición que importan no tiene: "
        + "; ".join(culpables))
