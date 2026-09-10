"""Las credenciales de e-firma de un cliente eran el valor global del despliegue.

Auditoría 2026-08 (P3-22). `endpoints/esign.py` tenía dos ayudantes locales que
buscaban `AppSetting` así:

    db.query(AppSetting).filter(AppSetting.key == key).first()

**Sin organización.** Y lo que guardan son las credenciales de DocuSign y de
Adobe Sign de cada cliente: su `integration_key`, su `secret_key`, su
`account_id` y —lo más grave— los **tokens de acceso y de refresco** que
devuelve el OAuth.

Tres consecuencias, en orden de gravedad:

1. La escritura creaba la fila con `organization_id` a NULL, que en
   `AppSetting` significa «valor global del despliegue». El primer cliente que
   configurara su DocuSign lo dejaba como valor de **todos**.
2. La lectura devolvía la primera fila con esa clave, sin mirar de quién es. Un
   cliente firmaba con la cuenta de DocuSign de otro.
3. Al completar el OAuth, el token de acceso de un cliente quedaba guardado
   como global: cualquier otro enviaba sobres con su token.

## La señal que explica por qué la comprobación nunca se escribió

Las **nueve** funciones que usaban esos ayudantes recibían el sujeto y lo
descartaban con `_: User = Depends(...)`. Nueve de nueve. No había a quién
preguntarle la organización porque el parámetro no tenía nombre — es el mismo
descarte que dejó sin comprobar el coste activo de un usuario.

## La regla

La que ya usa el resto del repositorio para `AppSetting`: **lo propio si
existe, y si no el global**, que es el valor que trae el despliegue. La
escritura, siempre en lo propio. Así las filas globales que ya existen siguen
sirviendo de respaldo y no se rompe ningún despliegue en marcha.
"""
from __future__ import annotations

import ast
import io

import pytest

ORG = "org-firma-mia"
OTRA = "org-firma-ajena"

CLAVE = "esign.docusign_integration_key"
CLAVE_TOKEN = "esign.docusign_access_token"


class _Usuario:
    def __init__(self, organization_id, uid="u-firma"):
        self.id = uid
        self.organization_id = organization_id
        self.is_superadmin = False


# -- La lectura --------------------------------------------------------------

def test_EL_HALLAZGO_no_se_lee_la_credencial_de_otro_cliente(db):
    from app.models.settings import AppSetting
    from app.services import esign_service as svc

    db.add(AppSetting(key=CLAVE, value="LA-DE-OTRO", organization_id=OTRA))
    db.commit()

    assert svc.ajuste_de_firma(db, _Usuario(ORG), CLAVE) is None, (
        "se está leyendo la credencial de DocuSign de otro cliente")

    svc.guardar_ajuste_de_firma(db, _Usuario(ORG), CLAVE, "LA-MIA")
    db.commit()
    assert svc.ajuste_de_firma(db, _Usuario(ORG), CLAVE) == "LA-MIA"
    # Y la del otro sigue intacta.
    assert svc.ajuste_de_firma(db, _Usuario(OTRA), CLAVE) == "LA-DE-OTRO"


def test_EL_ESCENARIO_la_consulta_de_antes_devolvia_la_primera_que_hubiera(db):
    """Que el escenario es real, medido y no contado."""
    from app.models.settings import AppSetting

    db.add(AppSetting(key=CLAVE, value="LA-DE-OTRO", organization_id=OTRA))
    db.commit()

    fila = db.query(AppSetting).filter(AppSetting.key == CLAVE).first()
    assert fila is not None and fila.organization_id == OTRA, (
        "la consulta sin ámbito ya no alcanza la fila de otro cliente; "
        "revisar si estos tests siguen midiendo lo que dicen")


def test_el_valor_global_sirve_de_respaldo(db):
    """Es la semántica declarada de `AppSetting`: NULL es el valor del despliegue.

    Importa porque las filas que ya existen en un despliegue en marcha son
    globales, y tienen que seguir funcionando.
    """
    from app.models.settings import AppSetting
    from app.services import esign_service as svc

    db.add(AppSetting(key=CLAVE, value="LA-DEL-DESPLIEGUE", organization_id=None))
    db.commit()

    assert svc.ajuste_de_firma(db, _Usuario(ORG), CLAVE) == "LA-DEL-DESPLIEGUE"

    # Y lo propio manda sobre el global.
    svc.guardar_ajuste_de_firma(db, _Usuario(ORG), CLAVE, "LA-MIA")
    db.commit()
    assert svc.ajuste_de_firma(db, _Usuario(ORG), CLAVE) == "LA-MIA"
    # Sin tocar el global, que sigue sirviendo a los demás.
    assert svc.ajuste_de_firma(db, _Usuario(OTRA), CLAVE) == "LA-DEL-DESPLIEGUE"


def test_un_valor_vacio_no_cuenta_como_configurado(db):
    """Se conserva del original: `row.value if row and row.value else None`."""
    from app.models.settings import AppSetting
    from app.services import esign_service as svc

    db.add(AppSetting(key=CLAVE, value="", organization_id=ORG))
    db.add(AppSetting(key=CLAVE, value="LA-DEL-DESPLIEGUE", organization_id=None))
    db.commit()

    # La propia está vacía, así que cae al global.
    assert svc.ajuste_de_firma(db, _Usuario(ORG), CLAVE) == "LA-DEL-DESPLIEGUE"


# -- La escritura ------------------------------------------------------------

def test_EL_HALLAZGO_guardar_no_deja_la_credencial_como_global(db):
    """Era el defecto de raíz: la fila nueva salía con la organización a NULL."""
    from app.models.settings import AppSetting
    from app.services import esign_service as svc

    svc.guardar_ajuste_de_firma(db, _Usuario(ORG), CLAVE, "LA-MIA")
    db.commit()

    fila = db.query(AppSetting).filter(AppSetting.key == CLAVE).first()
    assert fila.organization_id == ORG, (
        "la credencial se ha guardado como valor global del despliegue")

    # Y otro cliente no la ve.
    assert svc.ajuste_de_firma(db, _Usuario(OTRA), CLAVE) is None


def test_EL_HALLAZGO_el_token_de_oauth_tampoco_es_global(db):
    """El peor de los tres: enviar sobres con el token de otro cliente."""
    from app.services import esign_service as svc

    svc.guardar_ajuste_de_firma(db, _Usuario(ORG), CLAVE_TOKEN, "tok-mio")
    svc.guardar_ajuste_de_firma(db, _Usuario(OTRA), CLAVE_TOKEN, "tok-suyo")
    db.commit()

    assert svc.ajuste_de_firma(db, _Usuario(ORG), CLAVE_TOKEN) == "tok-mio"
    assert svc.ajuste_de_firma(db, _Usuario(OTRA), CLAVE_TOKEN) == "tok-suyo"


def test_guardar_dos_veces_actualiza_y_no_duplica(db):
    from app.models.settings import AppSetting
    from app.services import esign_service as svc

    svc.guardar_ajuste_de_firma(db, _Usuario(ORG), CLAVE, "primera")
    db.commit()
    svc.guardar_ajuste_de_firma(db, _Usuario(ORG), CLAVE, "segunda")
    db.commit()

    filas = db.query(AppSetting).filter(AppSetting.key == CLAVE).all()
    assert len(filas) == 1
    assert filas[0].value == "segunda"


def test_guardar_no_confirma(db):
    """La frontera de transacción se queda en el endpoint, con las demás."""
    from app.models.settings import AppSetting
    from app.services import esign_service as svc

    svc.guardar_ajuste_de_firma(db, _Usuario(ORG), CLAVE, "sin-confirmar")
    db.rollback()

    assert db.query(AppSetting).filter(AppSetting.key == CLAVE).first() is None


def test_un_sujeto_sin_organizacion_escribe_el_global(db):
    """El único sitio donde puede escribir, y coincide con lo de antes."""
    from app.models.settings import AppSetting
    from app.services import esign_service as svc

    svc.guardar_ajuste_de_firma(db, _Usuario(None), CLAVE, "sin-org")
    db.commit()

    fila = db.query(AppSetting).filter(AppSetting.key == CLAVE).first()
    assert fila.organization_id is None
    assert svc.ajuste_de_firma(db, _Usuario(None), CLAVE) == "sin-org"


# -- El estructural: ninguna de las nueve descarta ya el sujeto -------------

def test_EL_ESTRUCTURAL_ninguna_funcion_de_ajustes_descarta_el_sujeto():
    """Nueve de nueve lo recibían y lo tiraban con `_: User = Depends(...)`.

    Si alguien escribe una décima con el sujeto sin nombre, esto se pone en
    rojo — y esa es la forma exacta en la que se perdió la comprobación.
    """
    ruta = "app/api/v1/endpoints/esign.py"
    arbol = ast.parse(io.open(ruta, encoding="utf-8").read())

    AYUDANTES = {"_get_esign_setting", "_set_esign_setting"}
    culpables = []
    for f in arbol.body:
        if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if f.name in AYUDANTES:
            continue
        usa = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id in AYUDANTES
            for n in ast.walk(f)
        )
        if not usa:
            continue
        nombres = {a.arg for a in f.args.args}
        if "current_user" not in nombres:
            culpables.append(f"{f.name} (linea {f.lineno}): {sorted(nombres)}")

    assert not culpables, (
        "estas funciones leen o escriben ajustes de e-firma sin recibir el "
        "sujeto con nombre, así que no pueden acotar por organización:\n  "
        + "\n  ".join(culpables))


def test_las_claves_viven_en_un_solo_sitio():
    """Estaban duplicadas como literales en el endpoint."""
    from app.api.v1.endpoints import esign
    from app.services import esign_service as svc

    assert esign._ESIGN_KEYS is svc.CLAVES_DE_FIRMA
    assert esign._SECRET_KEYS is svc.CLAVES_SECRETAS
    # Las dos secretas están entre las siete que se exponen.
    assert svc.CLAVES_SECRETAS <= set(svc.CLAVES_DE_FIRMA)


@pytest.mark.parametrize("clave", [
    "esign.docusign_secret_key",
    "esign.adobe_sign_client_secret",
])
def test_las_secretas_son_las_dos_que_no_se_devuelven_en_claro(clave):
    from app.services import esign_service as svc

    assert clave in svc.CLAVES_SECRETAS
