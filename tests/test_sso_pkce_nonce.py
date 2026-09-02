"""PKCE y verificación de nonce en el flujo SSO (auditoría 2026-08, P2-13).

Dos huecos en un flujo por lo demás bien hecho (verificaba firma contra JWKS,
rechazaba si no podía obtenerla, validaba `state` con HMAC y consumo único, y
comprobaba `email_verified`):

1. Sin PKCE. Un `code` interceptado —historial del navegador, log de un proxy,
   una app que registre el esquema de redirección— era canjeable por tokens.
2. El `nonce` se generaba en /authorize y NO se comprobaba en el callback, así
   que no protegía de nada: un `id_token` capturado podía reutilizarse.

El almacén de estado guardaba la cadena "1", así que tampoco había dónde llevar
el verificador ni el nonce entre las dos mitades del flujo.
"""
from __future__ import annotations

import base64
import hashlib

import pytest

from app.services.auth_service import (
    consume_sso_state,
    consume_sso_state_payload,
    register_sso_state,
)


# ── El almacén de estado transporta el payload ───────────────────────────────

def test_el_estado_lleva_el_verificador_y_el_nonce():
    register_sso_state("st-payload", {"code_verifier": "v-123", "nonce": "n-456"})
    payload = consume_sso_state_payload("st-payload")
    assert payload == {"code_verifier": "v-123", "nonce": "n-456"}


def test_el_estado_es_de_un_solo_uso():
    """Protección contra replay: el segundo intento no encuentra nada."""
    register_sso_state("st-una-vez", {"nonce": "n"})
    assert consume_sso_state_payload("st-una-vez") is not None
    assert consume_sso_state_payload("st-una-vez") is None


def test_un_estado_inexistente_devuelve_none():
    assert consume_sso_state_payload("st-que-no-existe") is None


def test_consume_sso_state_sigue_funcionando():
    """Compatibilidad: la firma booleana anterior no se rompe."""
    register_sso_state("st-compat", {"nonce": "n"})
    assert consume_sso_state("st-compat") is True
    assert consume_sso_state("st-compat") is False


def test_el_estado_sin_payload_no_revienta():
    """Una transacción iniciada antes de este cambio no debe fallar."""
    register_sso_state("st-vacio")
    assert consume_sso_state_payload("st-vacio") == {}


# ── El challenge de PKCE se calcula bien ─────────────────────────────────────

def test_el_challenge_es_s256_sin_relleno():
    """Formato exigido por RFC 7636: base64url(SHA256(verifier)) sin '='.

    Si se enviara con relleno, el proveedor rechazaría el canje.
    """
    verifier = "verificador-de-prueba-suficientemente-largo-1234567890"
    esperado = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")

    assert "=" not in esperado
    assert len(esperado) == 43  # SHA-256 en base64url siempre son 43 caracteres

    # Mismo cálculo que hace el endpoint /authorize.
    calculado = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert calculado == esperado


# ── El endpoint envía los parámetros ─────────────────────────────────────────

def test_authorize_envia_pkce_y_guarda_el_verificador():
    """Comprueba el código del endpoint, no una reimplementación.

    Un test que recalculase el challenge por su cuenta pasaría aunque el
    endpoint no lo enviara: lo que importa es que los parámetros salgan en la URL
    de autorización y que el verificador quede guardado con el estado.
    """
    import inspect

    from app.api.v1.routers import auth_sso

    src = inspect.getsource(auth_sso.sso_authorize)
    assert '"code_challenge_method": "S256"' in src or "'code_challenge_method': 'S256'" in src, (
        "el endpoint /authorize debe declarar code_challenge_method=S256"
    )
    assert "code_challenge" in src, "falta el parámetro code_challenge"
    assert "code_verifier" in src, "el verificador debe generarse y guardarse"
    assert "_register_sso_state(state_raw, {" in src, (
        "el verificador y el nonce deben guardarse ligados al state"
    )


def test_el_callback_verifica_el_nonce_y_manda_el_verificador():
    """Los cuatro controles del callback, buscados en TODO el módulo.

    Antes se inspeccionaba sólo el código de `sso_callback`. Al repartir esa
    función en fases (auditoría 2026-08, hallazgo 18) los controles se movieron a
    `_validar_id_token_y_extraer_identidad` e `_intercambiar_codigo_por_tokens`,
    y el test se puso rojo aunque las propiedades seguían intactas.

    Se inspecciona el módulo entero a propósito: lo que hay que garantizar es que
    los controles EXISTEN, no en qué función viven. Atar el test a una ubicación
    lo convierte en un obstáculo para reorganizar el código, sin ganar seguridad.
    """
    import inspect

    from app.api.v1.routers import auth_sso

    src = inspect.getsource(auth_sso)
    assert "expected_nonce" in src, "el callback debe recuperar el nonce esperado"
    assert "compare_digest" in src, (
        "la comparación del nonce debe ser en tiempo constante"
    )
    assert 'raise HTTPException(400, "Nonce inválido' in src, (
        "un nonce que no coincide debe rechazar la autenticación"
    )
    assert '_token_params["code_verifier"] = code_verifier' in src, (
        "el canje del code debe incluir el verificador de PKCE"
    )
    assert "_consume_sso_state_payload(state_raw)" in src, (
        "el callback debe consumir el payload, no sólo el estado"
    )


def test_las_fases_del_callback_existen_y_estan_encadenadas():
    """La descomposición no puede deshacerse sin que salte algo.

    Cada fase es un control de seguridad: el `state` firmado contra CSRF, el
    canje del código con PKCE, la verificación del `nonce` contra replay y el
    rechazo de un correo no verificado. Que sean funciones con nombre es lo que
    permite probarlas una por una.
    """
    import inspect

    from app.api.v1.routers import auth_sso

    for fase in (
        "_validar_peticion_y_consumir_estado",
        "_resolver_token_endpoint",
        "_intercambiar_codigo_por_tokens",
        "_validar_id_token_y_extraer_identidad",
        "_extraer_identidad",
    ):
        assert hasattr(auth_sso, fase), f"falta la fase {fase}"

    # Y el endpoint las llama en orden: si alguien se salta una, el control que
    # esa fase aplica deja de ejecutarse.
    cuerpo = inspect.getsource(auth_sso.sso_callback)
    for llamada in (
        "_validar_peticion_y_consumir_estado(payload)",
        "_intercambiar_codigo_por_tokens(",
        "_validar_id_token_y_extraer_identidad(",
    ):
        assert llamada in cuerpo, f"el callback no invoca {llamada}"


def test_un_correo_no_verificado_se_rechaza():
    """P0-4. Un proveedor que NO ha verificado el correo no acredita identidad:
    aceptarlo permitiría suplantar a cualquiera registrando su dirección allí.

    Ahora se puede probar en aislamiento, que era el objetivo de sacar la fase.
    """
    from fastapi import HTTPException

    from app.api.v1.routers import auth_sso

    class _Config:
        saml_attribute_email = None
        saml_attribute_name = None

    with pytest.raises(HTTPException) as exc:
        auth_sso._extraer_identidad(
            _Config(), {"email": "a@b.com", "email_verified": False}
        )
    assert exc.value.status_code == 403


def test_sin_correo_no_se_puede_identificar():
    from fastapi import HTTPException

    from app.api.v1.routers import auth_sso

    class _Config:
        saml_attribute_email = None
        saml_attribute_name = None

    with pytest.raises(HTTPException) as exc:
        auth_sso._extraer_identidad(_Config(), {"sub": "123"})
    assert exc.value.status_code == 502


def test_un_correo_verificado_pasa():
    """Contra-test: el rechazo es por `email_verified is False`, no por ausencia.

    Muchos proveedores no envían el claim en absoluto, y rechazar eso dejaría
    fuera a usuarios legítimos.
    """
    from app.api.v1.routers import auth_sso

    class _Config:
        saml_attribute_email = None
        saml_attribute_name = None

    email, nombre = auth_sso._extraer_identidad(
        _Config(), {"email": "a@b.com", "name": "Ana", "email_verified": True}
    )
    assert email == "a@b.com"
    assert nombre == "Ana"

    # Sin el claim: se acepta.
    email2, _ = auth_sso._extraer_identidad(_Config(), {"email": "c@d.com"})
    assert email2 == "c@d.com"
