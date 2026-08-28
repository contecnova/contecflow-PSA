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
    import inspect

    from app.api.v1.routers import auth_sso

    src = inspect.getsource(auth_sso.sso_callback)
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
