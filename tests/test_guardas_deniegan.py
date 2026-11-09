"""Cada guarda de rol DENIEGA de verdad. No basta con que esté escrita.

`test_guardas_de_rol.py` comprueba que toda ruta de escritura lleva guarda o
una exención con motivo. Eso es una propiedad **sintáctica**: mira el código
fuente. No dice nada sobre si el 403 llega.

Este test lo dice. Para cada uno de los 979 pares (método, ruta) con guarda,
lanza la petición con un token de un rol que esa guarda tiene que rechazar, y
exige un 403.

## Por qué hace falta, si la guarda es una línea

Porque una guarda puede estar puesta y no correr. Ya ha pasado en este
repositorio, dos veces y de formas distintas: el middleware ABAC que nunca se
ejecutaba (hallazgo 1) y `enforce_abac`, que es fail-open y no comprueba nada
sin políticas activas (§3.octovicies). Escribir el nombre de la dependencia no
demuestra que el 403 salga; sólo demuestra que alguien lo escribió.

Y hay una forma muy concreta de romperlo sin darse cuenta: colgar la guarda de
un parámetro que FastAPI no resuelve —mal anotado, o después de `**kwargs`—
deja la firma con buena pinta y la puerta abierta.

## El rol con el que se sondea cada guarda

Se elige, para cada una, un rol que TIENE que quedar fuera:

| guarda | se sondea con | por qué |
|---|---|---|
| `require_admin`, `_or_pm`, `_or_hr`, `any_manager` | empleado | ninguno de esos conjuntos incluye a `employee` |
| `require_internal_user` | subcontratado | es el único rol que excluye |
| `require_superadmin` | admin de tenant | `admin` NO es superadmin: ver el docstring de `require_superadmin` |

## Por qué se puede mandar el cuerpo vacío

Porque en FastAPI las dependencias se resuelven **antes** de validar el cuerpo,
y una que lanza `HTTPException` corta ahí. Comprobado sobre `POST /clients`,
que tiene cuerpo obligatorio: con `{}` responde 403, no 422. Si algún día eso
cambiara, este test empezaría a ver 422 y fallaría — que es lo correcto,
porque entonces la guarda ya no sería lo primero.
"""
from __future__ import annotations

import re


from tests.test_abac_coverage import _api_routes, _source
from tests.test_guardas_de_rol import _desenvolver

ESCRITURA = {"POST", "PUT", "PATCH", "DELETE"}

#: Qué rol se usa para sondear cada guarda, y qué token lo trae.
SONDA = {
    "require_superadmin": "admin",
    "require_admin": "empleado",
    "require_admin_or_pm": "empleado",
    "require_admin_or_hr": "empleado",
    "require_any_manager": "empleado",
    "require_internal_user": "subcontratado",
}

GUARDA = re.compile(r"\b(require_(?:admin_or_pm|admin_or_hr|any_manager|internal_user"
                    r"|superadmin|admin))\b")

#: Valor con el que se rellena cualquier parámetro de ruta.
#:
#: No tiene que existir: la guarda corre antes de que nadie lo busque, así que
#: un 404 aquí significaría que el orden es el contrario al que se cree.
RELLENO = "11111111-1111-1111-1111-111111111111"


def _rutas_guardadas():
    """Las rutas de escritura con guarda, con la guarda más restrictiva de cada una."""
    salida = []
    vistas: set[tuple] = set()
    for _route, path, methods, _dep, endpoint in _api_routes():
        escritoras = methods & ESCRITURA
        if not escritoras:
            continue
        real = _desenvolver(endpoint)
        fuente = _source(endpoint) + _source(real)
        encontradas = GUARDA.findall(fuente)
        if not encontradas:
            continue
        # Una firma puede llevar varias; se sondea la primera, que es la que
        # FastAPI resuelve antes.
        guarda = encontradas[0]
        for metodo in sorted(escritoras):
            clave = (metodo, path)
            if clave in vistas:
                continue
            vistas.add(clave)
            salida.append((metodo, path, guarda))
    return sorted(salida)


RUTAS = _rutas_guardadas()

#: Pares (método, ruta) con guarda. **Exacto**, no un mínimo.
#:
#: Son 993 y no las 929 de `test_guardas_de_rol.py` porque ahí se cuentan
#: FUNCIONES —`main.py` monta los routers en v1 y en v2, así que la misma
#: función aparece con dos paths— y aquí se sondea cada par, que es lo que un
#: cliente puede llamar de verdad.
#:
#: El número va clavado a propósito. Con un `>=` holgado, comentar una guarda
#: hace que su ruta **desaparezca** de la lista en vez de fallar: el bucle pasa
#: en verde porque ya no la mira. Es el modo de fallo silencioso de este
#: fichero, y se cierra exigiendo el número exacto.
# 985 desde 2026-11-03: salen las 13 de la CMDB y los activos duplicados
# (/cmdb/items|relations|categories y /sd/assets, migraciones 110 y 111) y
# entran 5 con guarda (/sd/cmdb borrar CI y relacion, clases de CI, y
# /alm/assets/{aid}/refresh-ticket). Medido con el diff de RUTAS.
# 984 desde 2026-11-03 (tarde): sale POST /cmdb/agent-dashboard/{id}/snapshot;
# el panel de agente se calcula sobre los tickets y la «foto» ya no se usa.
# 986: entran POST y DELETE /reports/templates (admin o PM, como la pantalla).
# 989 desde 2026-11-04: entran las escrituras del motor BPMN —arrancar
# (/bpmn-processes/{id}/instances) y cancelar (admin o PM), y completar un paso
# (usuario interno)—.
# 983 desde 2026-11-04 (tarde): salen 6 duplicados con guarda de
# /portal/conversations/conversations/team/... (un segundo montaje del router de
# conversaciones con el prefijo repetido); las 6 de /portal/conversations/team
# siguen.
# 989 desde 2026-11-05: entran la baja, la exportacion y «entrar como» de
# empresas (superadmin) y, en el Hub de IA, probar/descubrir sin guardar y las
# rutas por funcion (admin).
RUTAS_ESPERADAS = 1030  # -1: fuera las notas internas aparte (/sd/tickets/{id}/internal-comments; las de verdad son comentarios con is_public=False); -2: fuera POST /ai/chat/stream (get_current_user y require_internal_user), que llamaba a Anthropic directo y no usaba nadie; -5: conectores de BI en una sola lista (fuera /bi/intelligence/connectors/* y el catálogo y los personalizados de /bi/platform; entran PATCH, test y fuentes de /bi/etl); -2: fuera la incrustación duplicada de BI (PATCH /bi/platform/embed/settings y POST /bi/platform/embed/token); +6: presupuestos (salen PATCH entry y POST approve; entran editar cabecera, añadir, editar y quitar partida, enviar, decidir, versión nueva y vincular proyecto); +6: gastos (crear, editar y borrar política —admin—; adjuntar y quitar justificante; repartir entre proyectos); +8: lecciones aprendidas (crear, editar, estado, borrar —admin—, valorar, acción, editar acción, recomendaciones para un proyecto que se crea); +2: editar y borrar un borrador de factura (PATCH y DELETE /invoices/{id}, responsables; faltó subirlo en 5d9ab97b); +12: conectores contecmind y contecintelligence (11 de usuario interno, probar de admin); +2: valorar una respuesta del asistente (el router de ai_chat está montado dos veces); +2: guardar y quitar una pregunta validada de Ask-the-Data (admin o PM); +4: retención (guardar política, aplicar) y bloqueo legal (crear, levantar), admin; +1: recargar el almacén analítico (admin); -1: fuera el stub PATCH /documents/{id}/edit


def test_se_sondean_todas_las_rutas_con_guarda():
    """La lista no encoge sin que nadie se entere.

    Este test NO sustituye a `test_guardas_de_rol.py`: aquel comprueba que la
    guarda **está**, y éste que **deniega**. Quitar una guarda lo caza aquel —y
    se ha comprobado rompiéndolo—; lo que caza éste es que la lista a sondear
    se quede coja por el camino.
    """
    assert len(RUTAS) == RUTAS_ESPERADAS, (
        f"Se esperaban {RUTAS_ESPERADAS} pares (método, ruta) con guarda y hay "
        f"{len(RUTAS)}. Si han entrado rutas nuevas con guarda, sube el número; si "
        "han bajado, alguien ha quitado o comentado una guarda."
    )


def test_todas_las_guardas_deniegan(client, admin_token, dev_token, sub_token):
    """Un rol que la guarda excluye recibe 403, no 2xx. Los 979, en una pasada.

    Es **un** test y no 979 parametrizados a propósito. La fixture `db` es
    `autouse` y de ámbito de función: parametrizar reconstruye el escenario una
    vez por ruta y el fichero solo tardaba más de diez minutos, con lo que
    habría duplicado la suite entera por sí mismo (§3.novovicies explica lo que
    cuesta cada preparación). Recorriéndolas en un bucle se paga una vez.

    Se pierde el detalle de «qué caso ha fallado» del informe de pytest, y se
    recupera con creces en el mensaje: si fallan varias, salen todas juntas, que
    es lo que hace falta para ver el patrón.
    """
    tokens = {"admin": admin_token, "empleado": dev_token, "subcontratado": sub_token}
    fallos: list[str] = []

    for metodo, path, guarda in RUTAS:
        url = re.sub(r"\{[^}]+\}", RELLENO, path)
        respuesta = client.request(
            metodo, url, json={},
            headers={"Authorization": f"Bearer {tokens[SONDA[guarda]]}"})
        if respuesta.status_code != 403:
            fallos.append(
                f"{metodo} {path}  [{guarda}, rol {SONDA[guarda]}]  -> "
                f"{respuesta.status_code}")

    assert not fallos, (
        f"{len(fallos)} de {len(RUTAS)} rutas con guarda NO devolvieron 403 al rol "
        "que esa guarda tiene que rechazar.\n\n"
        "  2xx  = la guarda está escrita pero no corre. Mira que el parámetro esté "
        "bien anotado y que FastAPI lo resuelva.\n"
        "  422  = la validación del cuerpo se ha adelantado a las dependencias, así "
        "que la guarda ha dejado de ser lo primero.\n"
        "  401  = la ruta pide otra autenticación antes que el rol.\n\n  "
        + "\n  ".join(fallos)
    )


def test_las_sondas_cubren_todas_las_guardas():
    """Ninguna guarda se queda sin rol con el que probarla.

    Si alguien añade una `require_algo` nueva y no dice con qué rol se sondea,
    este test lo dice en vez de dejar esa guarda sin comprobar en silencio.
    """
    usadas = {g for _m, _p, g in RUTAS}
    sin_sonda = sorted(usadas - set(SONDA))
    assert not sin_sonda, (
        "Estas guardas no tienen rol de sondeo en SONDA, así que nadie comprueba "
        f"que denieguen: {sin_sonda}"
    )


def test_el_403_llega_antes_que_la_validacion_del_cuerpo(client, dev_token):
    """El supuesto sobre el que descansa todo lo demás, comprobado.

    `POST /clients` lleva `require_any_manager` y un cuerpo obligatorio. Si las
    dependencias dejaran de correr antes que la validación, esto daría 422 y
    los 929 sondeos de arriba estarían midiendo otra cosa.
    """
    r = client.post("/api/v1/clients", json={},
                    headers={"Authorization": f"Bearer {dev_token}"})
    assert r.status_code == 403, (
        f"Se esperaba 403 con el cuerpo vacío y salió {r.status_code}. Si es 422, "
        "la validación se adelanta a las dependencias y este fichero necesita "
        "cuerpos válidos por ruta."
    )
