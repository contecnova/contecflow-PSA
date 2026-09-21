"""La complejidad de `app/` no puede empeorar.

Auditoría 2026-08 (hallazgo 18). El hallazgo decía «complejidad excesiva» y
llevaba abierto toda la auditoría por una razón que no era la falta de ganas:
**no había ninguna medida**. `ruff.toml` selecciona `E, F, W, S, B`, y `C901` no
está entre ellas, así que una función podía pasar de 10 a 20 sin que nada dijera
nada. Sin medida no hay «mejor» ni «peor», sólo opiniones.

Este fichero es el trinquete. La medida la hace `scripts/audit_complejidad.py`,
que **llama a ruff** en vez de reimplementar McCabe: la definición de
complejidad ya existe y tener dos sería peor que tener una.

## La lista está vacía, y esa es la noticia

`CONOCIDAS` está **vacía**: hoy no queda ni una función de `app/` por encima de
10. Se llegó ahí desde 94 / 253 / 17 (funciones / exceso / máximo), pasando por
74 / 173 / 16 cuando se escribió este fichero.

**Y ninguna se quitó partiéndola para bajar un número.** Casi todas eran una de
estas dos cosas:

* **Una tabla escrita como cascada de `if`.** Los bytes mágicos de un fichero,
  las palabras clave de un triaje, las once reglas de una retrospectiva, los
  nueve operadores de una expresión de flujo, los 19 pasos de un plan de
  pruebas, los 15 avisos de un plan de comunicación, los cinco tipos de
  aprobador, los pesos de un cálculo de riesgo de sesión. Escritas como tabla se
  leen enteras de un vistazo —que es lo que hace falta para revisarlas con quien
  las usa— y añadir una fila deja de ser añadir una rama.

* **El mismo bloque escrito dos o más veces.** El diccionario de respuesta de
  `run_query`, escrito **tres** veces. El respaldo a JSON de `resolve_comment`,
  dos. La aritmética de solapamiento de reservas, dos. El `try/except` de
  registro de `test_provider`, **cuatro**. DocuSign y Adobe, dos bloques
  idénticos de cuarenta líneas. La lista de permisos del portal, dos. Una tabla
  de impacto, dos. Una cadena de umbrales de carga, **tres veces en el mismo
  fichero**.

Y de paso salieron defectos que nadie estaba buscando:

* `useTaskComments` leía comentarios haciendo **POST** al endpoint de crearlos.
* El refinamiento con Claude de `estimate_task_hours` **nunca se ejecutó**:
  iteraba filas `(Task, horas)` como si fueran tareas.
* El chequeo SSRF de las automatizaciones distinguía sus propios errores
  **comparando el texto del mensaje**.
* `ml_predict_project_overrun_lgbm` tenía dos expresiones `... if x or True else`
  cuyo resultado se pisaba dos líneas después.
* Y el más incómodo: al partir `enforce_abac`, el guardián de cobertura ABAC se
  puso rojo sobre 65 rutas — porque **se satisfacía a sí mismo** escaneando el
  código de `enforce_abac` como si fuera otro control. Ver
  `tests/test_abac_coverage.py`.

## Las tres reglas

1. Una función que **no está** en la lista no puede superar 10. Con la lista
   vacía, eso es *todas*: el código nuevo nace por debajo del umbral.
2. Una función que **sí está** no puede subir de su valor registrado.
3. Si una **mejora** —baja o desaparece—, el test también falla, y pide que
   actualices la lista. Es a propósito: mantiene la foto honesta y convierte
   cada mejora en un cambio deliberado y visible en el diff.

Para regenerar la lista después de una mejora:

    python scripts/audit_complejidad.py --lista

"""
import pytest

from scripts.audit_complejidad import UMBRAL, medir


CONOCIDAS: dict[tuple[str, str], int] = {}



@pytest.fixture(scope="module")
def medicion():
    return medir()


def test_ninguna_funcion_nueva_por_encima_del_umbral(medicion):
    """La regla que de verdad importa: lo nuevo nace por debajo de 10."""
    nuevas = {k: v for k, v in medicion.items() if k not in CONOCIDAS}
    assert not nuevas, (
        "funciones por encima de "
        f"{UMBRAL} que no estaban registradas:\n"
        + "\n".join(f"  {v:3}  {f}  {n}" for (f, n), v in sorted(nuevas.items()))
        + "\n\nNo la añadas a CONOCIDAS para que pase: pártela, o saca lo que "
          "esconde. La lista es la deuda que ya había, no un buzón."
    )


def test_ninguna_conocida_ha_empeorado(medicion):
    peores = {
        k: (CONOCIDAS[k], medicion[k])
        for k in CONOCIDAS
        if k in medicion and medicion[k] > CONOCIDAS[k]
    }
    assert not peores, (
        "funciones registradas que han crecido:\n"
        + "\n".join(f"  {f}  {n}: {antes} -> {ahora}"
                     for (f, n), (antes, ahora) in sorted(peores.items()))
    )


def test_la_foto_sigue_siendo_la_de_la_lista(medicion):
    """Si algo ha mejorado, hay que bajar el registro. A mano y a la vista.

    Falla ante una mejora **a propósito**. Un trinquete que sólo mira hacia
    arriba deja la foto envejecer: al cabo de unos meses la lista dice 16 donde
    el código dice 11, y entonces alguien puede subir de 11 a 16 sin que salte
    nada. Mantenerla exacta cuesta un comando y evita eso.
    """
    mejoradas = {
        k: (CONOCIDAS[k], medicion.get(k))
        for k in CONOCIDAS
        if k not in medicion or medicion[k] < CONOCIDAS[k]
    }
    assert not mejoradas, (
        "la complejidad ha bajado — enhorabuena, y actualiza la lista con "
        "`python scripts/audit_complejidad.py --lista`:\n"
        + "\n".join(f"  {f}  {n}: {antes} -> {ahora or 'por debajo del umbral'}"
                     for (f, n), (antes, ahora) in sorted(mejoradas.items()))
    )


def test_los_totales_registrados_cuadran(medicion):
    """Que los números de la cabecera no se queden viejos."""
    assert len(medicion) == len(CONOCIDAS)
    assert sum(v - UMBRAL for v in medicion.values()) == EXCESO_REGISTRADO
    # `max()` de un diccionario vacío levanta, y con la lista en cero el
    # máximo registrado es cero.
    assert max(medicion.values(), default=0) == MAXIMO_REGISTRADO


EXCESO_REGISTRADO = 0
MAXIMO_REGISTRADO = 0
