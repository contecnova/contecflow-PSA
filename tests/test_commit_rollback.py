"""Los `commit()` de la capa API que no deshacían al fallar.

Auditoría 2026-08 (P3-22). Contar accesos a base no dice si hay defecto. La
pregunta que sí lo dice —«¿hay algún `db.commit()` cuyo fallo alguien atrape y
nadie deshaga?»— destapa el mismo defecto que apareció en el motor de flujos:

> tras un `commit()` fallido la sesión queda en **transacción abortada**, y todo
> lo que venga después falla también — **incluido el registro del propio error**.

## Los cinco arreglados

| Sitio | Qué pasaba |
|---|---|
| `ai_auto_resolution.py` (síncrono) | el `except` escribía el registro de fallo y hacía `commit()` sin deshacer: el registro no se escribía nunca, el panel se quedaba en «running» y el error real quedaba tapado por un `PendingRollbackError` |
| `bookings_service.py` (cola de flujos) | igual, **dentro de un bucle**: el `commit()` del fallo reventaba, el `raise` abortaba la cola entera y el elemento se quedaba en `processing` — estado del que **no hay ningún barrido que rescate** |
| `ai_provider_service.py` ×2 | el `commit()` de *estadísticas* estaba dentro del `try` de la llamada, así que un fallo de nuestra base descartaba una respuesta de IA **ya facturada** y, en el camino primario, marcaba `status = "error"` en un proveedor que había funcionado |
| `collaboration/files.py` | `commit()` best-effort del índice de texto; al fallar, la respuesta leía atributos expirados de `att` y una subida **correcta** se convertía en un 500 |
| `scim.py` | el `AuditLog` de un borrado de usuario se perdía y la sesión quedaba sucia |

## La señal que los delató: una asimetría

En `ai_auto_resolution.py` **el camino asíncrono ya lo hacía bien** —`try`
anidado con `rollback()` y un `finally` que cierra la sesión y libera el lock— y
el síncrono, cuarenta líneas más arriba, no. De paso apareció que **el guardia
`already_running` sólo protegía el camino asíncrono**.

## Y el detector, que estaba mal

La primera versión iba **por bloque `try`** en vez de por llamada a `commit()`, y
tenía dos falsos positivos: contaba un `try`/`finally` sin `except` —que no se
traga nada— y no veía el `rollback` cuando estaba en un `try` anidado. Con eso
publiqué «19 en `app/services`»; **la cifra real es 13**. Los tests de abajo
prueban el detector en las dos direcciones, porque uno que sobrecuenta se acaba
ignorando y uno que subcuenta da luz verde.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from tests.conftest import auth

_NOMBRES_DE_SESION = {"db", "session"}


def _es_llamada(n, metodo: str) -> bool:
    """`db.commit()` / `session.rollback()` y compañía.

    Se miran los dos nombres que usa el repo —`db` en los endpoints y `session`
    en los trabajos de fondo— porque limitarlo a `db` deja fuera justo los
    sitios donde más duele.
    """
    return (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == metodo and isinstance(n.func.value, ast.Name)
            and n.func.value.id in _NOMBRES_DE_SESION)


def _commits_en_riesgo(raiz: str) -> list[str]:
    """Los `commit()` cuyo fallo alguien atrapa y nadie deshace.

    Se razona **por llamada a `commit()`**, no por bloque `try`. La regla: se
    busca el `try` **con `except`** más interno que envuelve la llamada. Si no
    hay ninguno, el fallo propaga al llamador y eso no es este defecto. Si lo hay
    y sus manejadores no deshacen, es riesgo.
    """
    riesgo = []
    for f in sorted(pathlib.Path(raiz).rglob("*.py")):
        try:
            arbol = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        padres = {}
        for n in ast.walk(arbol):
            for hijo in ast.iter_child_nodes(n):
                padres[hijo] = n
        for n in ast.walk(arbol):
            if not _es_llamada(n, "commit"):
                continue
            cur, guardian = padres.get(n), None
            while cur is not None:
                if isinstance(cur, ast.Try) and cur.handlers:
                    guardian = cur
                    break
                if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    break
                cur = padres.get(cur)
            if guardian is None:
                continue
            deshace = any(
                _es_llamada(x, "rollback")
                for h in guardian.handlers for b in h.body for x in ast.walk(b)
            )
            if not deshace:
                riesgo.append(f"{f.as_posix()}:{n.lineno}")
    return riesgo


# ── El estructural ──────────────────────────────────────────────────────────

def test_EL_ESTRUCTURAL_ningun_commit_de_la_api_deja_la_sesion_abortada():
    """El que impide que vuelva a entrar uno nuevo.

    No prueba un caso: cuenta los sitios. Si alguien añade un `commit()` cuyo
    fallo se atrapa sin deshacer, este test lo dice con fichero y línea — que es
    lo que no pasó las cinco veces anteriores.
    """
    fallos = _commits_en_riesgo("app/api")
    assert not fallos, (
        "hay %d commit() atrapados y sin rollback en app/api:\n  %s\n"
        "Tras un commit fallido la sesión queda en transacción abortada y todo "
        "lo que venga después falla, incluido el registro del error."
        % (len(fallos), "\n  ".join(fallos))
    )


def test_el_detector_encuentra_el_defecto_cuando_esta(tmp_path):
    """El detector, probado contra un caso plantado.

    Un test estructural cuyo detector está roto es peor que no tenerlo: da luz
    verde sin mirar.
    """
    (tmp_path / "malo.py").write_text(
        "def f(db):\n"
        "    try:\n"
        "        db.add(1)\n"
        "        db.commit()\n"
        "    except Exception:\n"
        "        pass\n",
        encoding="utf-8",
    )
    assert len(_commits_en_riesgo(str(tmp_path))) == 1


@pytest.mark.parametrize("nombre,fuente", [
    # try/finally SIN except: no se traga nada, el fallo propaga
    ("finally_sin_except",
     "def f(db):\n"
     "    try:\n"
     "        db.commit()\n"
     "    finally:\n"
     "        pass\n"),
    # el rollback está en un try ANIDADO que envuelve al commit
    ("rollback_anidado",
     "def f(db):\n"
     "    try:\n"
     "        try:\n"
     "            db.commit()\n"
     "        except Exception:\n"
     "            db.rollback()\n"
     "    except Exception:\n"
     "        pass\n"),
    # sin try alguno: el fallo propaga al llamador
    ("sin_try",
     "def f(db):\n"
     "    db.commit()\n"),
])
def test_el_detector_no_cuenta_falsos_positivos(tmp_path, nombre, fuente):
    """Los dos falsos positivos que tenía la primera versión, más el caso base.

    Iba por bloque `try` en vez de por llamada a `commit()`, así que contaba un
    `try`/`finally` sin `except` y no veía un `rollback` anidado. Con eso la
    cuenta que publiqué de `app/services` (19) estaba inflada: la real es 13.
    """
    (tmp_path / f"{nombre}.py").write_text(fuente, encoding="utf-8")
    assert _commits_en_riesgo(str(tmp_path)) == []


def test_los_de_app_services_estan_contados_y_no_han_crecido():
    """Los 13 de `app/services` están medidos y NO arreglados en bloque.

    Cada uno necesita criterio, y meter un `rollback()` en trece sitios sin
    leerlos sería la chapuza que este trabajo intenta no hacer. Lo que sí se
    puede hacer es fijar el número: si sube, alguien ha añadido uno nuevo.

    De los que estaban dentro de un bucle —los graves, porque envenenan las
    iteraciones siguientes— se arreglaron dos (`bookings_service` y los dos de
    `ai_provider_service`); quedan los dos de `collaboration/_scheduler.py`,
    cuyo arreglo correcto es un `try` por mensaje alrededor de un cuerpo `async`
    con `await bus.publish`, es decir tocar la entrega en tiempo real. Eso va en
    su propia tanda, no de propina.
    """
    encontrados = _commits_en_riesgo("app/services")
    assert len(encontrados) <= 13, (
        "han aparecido commit() nuevos sin rollback en app/services (%d > 13):\n  %s"
        % (len(encontrados), "\n  ".join(encontrados))
    )


# ── El guardia del trabajo de auto-resolución ───────────────────────────────

class TestGuardiaDeAutoResolucion:
    """El guardia del trabajo de auto-resolucion.

    Auditoria 2026-08: el cerrojo y el estado del trabajo pasaron a ser **por
    organizacion**. Antes eran uno para todo el proceso, asi que el trabajo de un
    cliente devolvia `already_running` al de otro, y el estado —`job_id`,
    tiempos, estadisticas y errores— lo veia cualquiera. Estos tests siguen
    comprobando lo mismo que antes; lo que cambia es que piden el cerrojo y el
    estado **de la organizacion de quien lanza**.
    """

    def _correr(self, client, token, **params):
        from urllib.parse import urlencode
        return client.post(
            "/api/v1/sd/auto-resolution/run-job?" + urlencode(params),
            headers=auth(token),
        )

    def _org(self, db):
        from app.models.user import User
        return db.query(User.organization_id).filter(
            User.username == "admin").scalar()

    def _cerrojo(self, db):
        from app.services.service_desk.ai_auto_resolution_service import (
            cerrojo_del_trabajo,
        )
        return cerrojo_del_trabajo(self._org(db))

    def _estado(self, db):
        from app.services.service_desk.ai_auto_resolution_service import (
            estado_del_trabajo,
        )
        return estado_del_trabajo(db, self._org(db))

    def test_EL_HALLAZGO_el_camino_sincrono_tambien_toma_el_guardia(
            self, client, admin_token, db, monkeypatch):
        """Antes el lock sólo se tomaba en la rama asíncrona.

        Con el lock ya cogido, una llamada síncrona **no debe** ejecutar el
        trabajo: tiene que devolver `already_running`. Solapar dos pasadas de
        resolución automática puede resolver el mismo ticket dos veces.
        """
        from app.api.v1.endpoints.service_desk import ai_auto_resolution as mod

        llamado = []

        def registrar(*a, **k):
            llamado.append(1)
            return {}

        monkeypatch.setattr(mod, "run_daily_auto_resolution_job", registrar)
        cerrojo = self._cerrojo(db)
        assert cerrojo.acquire(blocking=False)
        try:
            res = self._correr(client, admin_token, run_async=False, limit=5)
        finally:
            cerrojo.release()

        assert res.status_code == 200, res.text
        assert res.json()["data"]["status"] == "already_running"
        assert not llamado, "el trabajo se ha ejecutado con el guardia cogido"

    def test_el_guardia_se_libera_aunque_el_trabajo_reviente(
            self, client, admin_token, db, monkeypatch):
        """Un `finally`, no un `release()` al final del camino feliz.

        Sin `finally`, un fallo del trabajo deja el lock cogido para siempre y
        **el trabajo no se puede volver a lanzar nunca** — se cambia un fallo
        puntual por una averia permanente.

        El fallo sale como **500**, no como excepcion: `app/main.py` tiene un
        manejador global que lo convierte en respuesta con `request_id`. Se
        asierta sobre eso y no sobre la excepcion, que es lo que de verdad ve
        quien llama.
        """
        from app.api.v1.endpoints.service_desk import ai_auto_resolution as mod

        def revienta(*a, **k):
            raise RuntimeError("fallo del trabajo")

        monkeypatch.setattr(mod, "run_daily_auto_resolution_job", revienta)
        res = self._correr(client, admin_token, run_async=False, limit=5)
        assert res.status_code == 500, res.text

        cerrojo = self._cerrojo(db)
        assert cerrojo.acquire(blocking=False), (
            "el guardia ha quedado cogido tras un fallo: el trabajo no se puede "
            "relanzar"
        )
        cerrojo.release()

    def test_EL_HALLAZGO_el_error_real_no_queda_tapado(
            self, client, admin_token, db, monkeypatch):
        """El defecto, por su efecto observable.

        Antes el `except` escribia el registro sobre una sesion posiblemente
        abortada, asi que el `commit()` reventaba con `PendingRollbackError` y
        **el error que provoco el fallo no llegaba a ninguna parte**. Ahora se
        deshace primero, y el registro lleva el error de verdad — que es lo que
        necesita quien mira el panel, porque la respuesta HTTP es un 500 generico
        con `request_id` y no dice la causa.
        """
        from app.api.v1.endpoints.service_desk import ai_auto_resolution as mod

        def revienta(*a, **k):
            raise RuntimeError("EL-ERROR-DE-VERDAD")

        monkeypatch.setattr(mod, "run_daily_auto_resolution_job", revienta)
        res = self._correr(client, admin_token, run_async=False, limit=5)
        assert res.status_code == 500

        estado = self._estado(db)
        assert estado.get("error") == "EL-ERROR-DE-VERDAD", (
            "el registro no lleva el error real, lleva: %r" % estado.get("error")
        )

    def test_tras_un_fallo_el_panel_no_se_queda_diciendo_running(
            self, client, admin_token, db, monkeypatch):
        """`running: True` pegado no bloquea reejecuciones —el guardia es el
        lock, no el flag— pero miente en el panel indefinidamente."""
        from app.api.v1.endpoints.service_desk import ai_auto_resolution as mod

        def revienta(*a, **k):
            raise RuntimeError("x")

        monkeypatch.setattr(mod, "run_daily_auto_resolution_job", revienta)
        assert self._correr(client, admin_token, run_async=False, limit=5).status_code == 500

        estado = self._estado(db)
        assert estado.get("running") is False, (
            "el panel se ha quedado en «running» tras el fallo: %s" % estado
        )
        assert estado.get("status") == "failed"
        assert estado.get("duration_ms") is not None, (
            "sin duracion no se puede saber si el trabajo murio pronto o tarde"
        )

    def test_el_camino_feliz_sigue_devolviendo_las_estadisticas(
            self, client, admin_token, db, monkeypatch):
        """El envoltorio del lock no puede cambiar lo que devuelve el endpoint."""
        from app.api.v1.endpoints.service_desk import ai_auto_resolution as mod

        monkeypatch.setattr(
            mod, "run_daily_auto_resolution_job",
            lambda *a, **k: {"processed": 3, "auto_resolved": 1,
                             "suggested": 1, "failed": 1},
        )
        res = self._correr(client, admin_token, run_async=False, limit=5)
        assert res.status_code == 200, res.text
        datos = res.json()["data"]
        assert datos["processed"] == 3
        assert datos["status"] == "completed"
        cerrojo = self._cerrojo(db)
        assert cerrojo.acquire(blocking=False), (
            "el guardia no se ha liberado en el camino feliz"
        )
        cerrojo.release()

    def test_solo_un_administrador_puede_lanzarlo(self, client, dev_token, db):
        """Estaba antes y se fija: el trabajo resuelve tickets solo."""
        res = self._correr(client, dev_token, run_async=False, limit=5)
        assert res.status_code == 403


# ── Los proveedores de IA: la contabilidad no puede tirar la respuesta ──────

class TestContabilidadDeProveedores:
    """El defecto con consecuencia de dinero.

    El `commit()` de estadísticas estaba dentro del `try` de la llamada, así que
    un fallo de **nuestra** base descartaba una respuesta que el proveedor ya
    había atendido y facturado — y en el camino primario marcaba
    `status = "error"` en un proveedor que había funcionado, que es el valor que
    lo excluye de futuras selecciones.
    """

    def _proveedor(self):
        from unittest.mock import MagicMock
        p = MagicMock()
        p.name = "prov-1"
        p.provider = "openai"
        p.default_model = "gpt-4o"
        p.total_requests = 0
        p.total_tokens_in = 0
        p.total_tokens_out = 0
        p.total_cost_usd = 0.0
        p.status = "active"
        return p

    def _sesion_que_falla_al_commitear(self):
        from unittest.mock import MagicMock
        db = MagicMock()
        db.commit.side_effect = RuntimeError("la base ha fallado")
        return db

    def test_EL_HALLAZGO_un_fallo_de_la_base_no_tira_la_respuesta(self, monkeypatch):
        """La respuesta se devuelve igual: ya está pagada."""
        from app.services import ai_provider_service as mod

        p = self._proveedor()
        db = self._sesion_que_falla_al_commitear()
        respuesta = {"text": "hola", "tokens_in": 10, "tokens_out": 5,
                     "model": "gpt-4o"}
        monkeypatch.setattr(mod, "call_provider", lambda *a, **k: dict(respuesta))

        prov, result, error = mod._llamar_con_respaldo(
            db, p, [{"role": "user", "content": "hola"}], None, None, 100,
            False, "org-1",
        )
        assert result["text"] == "hola", "se ha tirado una respuesta ya facturada"
        assert error is None
        assert prov is p

    def test_EL_HALLAZGO_un_fallo_de_la_base_no_marca_al_proveedor_en_error(
            self, monkeypatch):
        """`status = "error"` es el valor que excluye al proveedor de futuras
        selecciones. Ponerlo por un fallo nuestro desactiva algo que funciona."""
        from app.services import ai_provider_service as mod

        p = self._proveedor()
        db = self._sesion_que_falla_al_commitear()
        monkeypatch.setattr(mod, "call_provider", lambda *a, **k: {
            "text": "ok", "tokens_in": 1, "tokens_out": 1, "model": "gpt-4o"})

        mod._llamar_con_respaldo(
            db, p, [{"role": "user", "content": "x"}], None, None, 100,
            False, "org-1",
        )
        assert p.status == "active", (
            "un fallo de nuestra base ha desactivado un proveedor que funciona"
        )

    def test_un_fallo_de_la_base_deja_la_sesion_limpia(self, monkeypatch):
        """El `rollback()` tiene que haberse llamado: sin él, todo lo que
        reutilice la sesión falla con un error que no tiene que ver."""
        from app.services import ai_provider_service as mod

        p = self._proveedor()
        db = self._sesion_que_falla_al_commitear()
        monkeypatch.setattr(mod, "call_provider", lambda *a, **k: {
            "text": "ok", "tokens_in": 1, "tokens_out": 1, "model": "gpt-4o"})

        mod._llamar_con_respaldo(
            db, p, [{"role": "user", "content": "x"}], None, None, 100,
            False, "org-1",
        )
        assert db.rollback.called, "no se ha deshecho tras el commit fallido"

    def test_si_falla_la_LLAMADA_si_se_marca_en_error_y_se_va_al_respaldo(
            self, monkeypatch):
        """La otra mitad de la separación: un fallo del proveedor **sí** lo marca
        y **sí** dispara el respaldo. Si esto se rompiera, el arreglo habría
        cambiado un defecto por otro."""
        from app.services import ai_provider_service as mod

        p = self._proveedor()
        from unittest.mock import MagicMock
        db = MagicMock()

        def revienta(*a, **k):
            raise RuntimeError("el proveedor no responde")

        monkeypatch.setattr(mod, "call_provider", revienta)
        monkeypatch.setattr(mod, "_try_fallback_providers",
                            lambda *a, **k: (None, None))

        prov, result, error = mod._llamar_con_respaldo(
            db, p, [{"role": "user", "content": "x"}], None, None, 100,
            False, "org-1",
        )
        assert p.status == "error", "un fallo real del proveedor debe marcarlo"
        assert error and "no responde" in error
        assert prov is None
