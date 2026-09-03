"""El recifrado de secretos de integración, y el defecto que corrompía material
criptográfico.

Auditoría 2026-08 (P3-18 + defecto encontrado de paso).
`_rotate_integration_secrets` era complejidad 21 en cinco bloques que hacen lo
mismo sobre cinco modelos. Al ponerlos uno al lado del otro apareció una
asimetría que no era intencionada.

## El defecto

Tres de los cinco bloques llevaban una rama de respaldo «esto es plaintext
heredado, cifrémoslo»:

    if plain:                            -> recifrar
    elif not valor.startswith("v2:"):    -> tratar como plaintext y cifrar

El respaldo de SSO y de webhooks comprobaba sólo `v2:`; el de `AppSetting`
comprobaba `v2:` **y** `kmsv1:`.

Y la rama es **inalcanzable para su propósito declarado**: `decrypt_value()` ya
devuelve el texto plano cuando el valor es plaintext heredado —lo hace su propio
respaldo interno—, así que un plaintext entra siempre por `if plain:`. Lo único
que llega al `elif` es un valor cuyo descifrado falló de verdad:

    valor = "kmsv1:..." y KMS no responde  ->  decrypt_value() = None
                                          ->  no empieza por "v2:"
                                          ->  se cifra el CRIPTOGRAMA

El secreto de cliente OIDC y los secretos de webhook quedaban cifrados dos veces
e irrecuperables sin descifrar dos niveles. Se ejecuta desde la rotación
programada, así que pasaría sin que nadie lo pidiera, y el síntoma sería que el
SSO deja de funcionar.

Es el patrón que atraviesa toda la auditoría: un respaldo tolerante que
convierte un fallo en la acción equivocada.

## El arreglo

Se recifra sólo cuando el descifrado ha funcionado. Un valor ilegible se deja
intacto y se avisa con el modelo, el identificador y el campo —nunca el valor—.
"""
from __future__ import annotations

import uuid


from app.core.encryption import decrypt_value, encrypt_value
from app.services.key_management import _rotate_integration_secrets



# `_rotate_integration_secrets` asigna en la sesión pero NO commitea: eso lo hace
# su llamador `rotate_due_materials`. Por eso aquí hay que commitear antes de
# refrescar — sin commit, `db.refresh()` descarta el cambio pendiente y recarga
# el valor viejo. Es la razón por la que dos de estos tests fallaban al escribirse.
def _rotar_y_recargar(db, fila) -> int:
    from app.services.key_management import _rotate_integration_secrets

    cambiados = _rotate_integration_secrets(db)
    db.commit()
    db.refresh(fila)
    return cambiados


# ── El caso que corrompía ─────────────────────────────────────────────────────

def test_un_secreto_de_sso_ilegible_se_deja_intacto(db, caplog):
    """El defecto, aislado. Antes del arreglo este valor salía cifrado dos veces.

    `kmsv1:` es el prefijo que pone `encrypt_value` cuando el cifrado va por AWS
    KMS. Si KMS no responde, `decrypt_value` devuelve None — y la comprobación
    antigua, que sólo miraba `v2:`, lo tomaba por plaintext.
    """
    from app.models.enterprise import SSOConfig

    ilegible = "kmsv1:AAAAilegible"
    cfg = SSOConfig(
        id=str(uuid.uuid4()),
        organization_id="1",
        provider="oidc",
        oidc_client_secret=ilegible,
    )
    db.add(cfg)
    db.commit()

    with caplog.at_level("WARNING"):
        _rotate_integration_secrets(db)

    db.refresh(cfg)
    assert cfg.oidc_client_secret == ilegible, (
        "el secreto ilegible se ha modificado; volver a cifrarlo lo destruye"
    )
    assert any("no se puede descifrar" in r.getMessage() for r in caplog.records), (
        "un secreto ilegible tiene que avisar, no desaparecer en silencio"
    )


def test_el_aviso_no_contiene_el_secreto(db, caplog):
    """Un secreto ilegible sigue siendo un secreto: el aviso lleva el modelo, el
    identificador y el campo, nunca el valor."""
    from app.models.enterprise import Webhook

    secreto = "kmsv1:NOAPARECEENELLOG"
    hook = Webhook(
        id=str(uuid.uuid4()),
        organization_id="1",
        name="hook de prueba",
        url="https://example.com/hook",
        events="[]",
        secret=secreto,
    )
    db.add(hook)
    db.commit()

    with caplog.at_level("WARNING"):
        _rotate_integration_secrets(db)

    for registro in caplog.records:
        assert "NOAPARECEENELLOG" not in registro.getMessage()


def test_un_v2_malformado_tampoco_se_toca(db):
    """El otro camino por el que `decrypt_value` devuelve None."""
    from app.models.enterprise import SSOConfig

    malformado = "v2:sin-el-punto-separador"
    cfg = SSOConfig(id=str(uuid.uuid4()), organization_id="1",
                    provider="oidc", oidc_client_secret=malformado)
    db.add(cfg)
    db.commit()

    _rotate_integration_secrets(db)
    db.refresh(cfg)
    assert cfg.oidc_client_secret == malformado


# ── Lo que sí tiene que seguir pasando ────────────────────────────────────────

def test_un_secreto_en_claro_se_cifra(db):
    """El propósito declarado de la rama que se ha quitado, y sigue cubierto:
    `decrypt_value` devuelve el plaintext tal cual, así que entra por el camino
    principal y se cifra."""
    from app.models.enterprise import SSOConfig

    cfg = SSOConfig(id=str(uuid.uuid4()), organization_id="1",
                    provider="oidc", oidc_client_secret="secreto-en-claro")
    db.add(cfg)
    db.commit()

    cambiados = _rotar_y_recargar(db, cfg)

    assert cambiados >= 1
    assert cfg.oidc_client_secret != "secreto-en-claro"
    assert cfg.oidc_client_secret.startswith(("v2:", "kmsv1:"))
    assert decrypt_value(cfg.oidc_client_secret) == "secreto-en-claro"


def test_un_secreto_ya_cifrado_se_recifra_y_sigue_descifrando(db):
    """El caso normal de la rotación: mismo texto plano, criptograma nuevo."""
    from app.models.enterprise import SSOConfig

    original = encrypt_value("secreto-original")
    cfg = SSOConfig(id=str(uuid.uuid4()), organization_id="1",
                    provider="oidc", oidc_client_secret=original)
    db.add(cfg)
    db.commit()

    _rotar_y_recargar(db, cfg)

    assert cfg.oidc_client_secret != original, "no se ha recifrado"
    assert decrypt_value(cfg.oidc_client_secret) == "secreto-original"


def test_un_campo_vacio_no_cuenta_como_cambio(db):
    from app.models.enterprise import SSOConfig

    cfg = SSOConfig(id=str(uuid.uuid4()), organization_id="1",
                    provider="oidc", oidc_client_secret=None)
    db.add(cfg)
    db.commit()
    assert _rotate_integration_secrets(db) == 0


def test_los_cinco_modelos_estan_en_la_tabla():
    """Un modelo que guarde secretos y no esté aquí no se rotaría nunca — y no
    fallaría nada. Es la misma clase de comprobación que cruza catálogo y código
    en las métricas."""
    from app.services.key_management import _secretos_a_recifrar

    nombres = {spec.modelo.__name__ for spec in _secretos_a_recifrar()}
    assert nombres == {
        "AIProvider", "IntegrationConfig", "SSOConfig", "Webhook", "AppSetting",
    }, nombres


def test_los_campos_de_la_tabla_existen_en_sus_modelos():
    """Un nombre de campo mal escrito haría que ese secreto no se rotara nunca,
    en silencio, porque el acceso es por `getattr` con respaldo."""
    from app.services.key_management import _secretos_a_recifrar

    for spec in _secretos_a_recifrar():
        columnas = set(spec.modelo.__table__.columns.keys())
        faltan = set(spec.campos) - columnas
        assert not faltan, f"{spec.modelo.__name__} no tiene {faltan}"


def test_se_recifran_los_dos_tokens_de_una_integracion(db):
    """`IntegrationConfig` tiene dos campos y los dos cuentan por separado."""
    from app.models.cab import IntegrationConfig

    cfg = IntegrationConfig(
        id=str(uuid.uuid4()),
        organization_id="1",
        integration_type="slack",
        name="integración de prueba",
        access_token=encrypt_value("token-de-acceso"),
        refresh_token=encrypt_value("token-de-refresco"),
    )
    db.add(cfg)
    db.commit()

    cambiados = _rotar_y_recargar(db, cfg)

    assert cambiados >= 2
    assert decrypt_value(cfg.access_token) == "token-de-acceso"
    assert decrypt_value(cfg.refresh_token) == "token-de-refresco"
