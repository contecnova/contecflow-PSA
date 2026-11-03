"""La aplicación no depende de un proveedor de IA concreto.

Auditoría 2026-09. La única credencial de IA que admitía `.env` era
`ANTHROPIC_API_KEY`. La aplicación soporta ocho proveedores, así que quien
trabajase con Gemini, OpenAI o un Ollama local no podía configurar el
despliegue por fichero: o pasaba por la interfaz, o no había IA.

El arreglo es una resolución de tres escalones, que es la que ya usaba el motor
de voz en `app/services/stt/__init__.py`:

    proveedor de la organización (BD) → proveedor global (BD) → .env

La base de datos no sobra: un despliegue multi-empresa necesita un proveedor por
organización, y eso un fichero de entorno no lo puede expresar. Lo que resuelve
`.env` es el despliegue de un solo cliente, que debe poder configurarse entero
sin abrir la aplicación.
"""
from __future__ import annotations

import importlib

import pytest

import app.core.config as config_mod


def _recargar(monkeypatch, **variables):
    """Recarga la configuración con estas variables de entorno y nada más."""
    for nombre in ("AI_PROVIDER", "AI_API_KEY", "AI_MODEL", "AI_BASE_URL",
                   "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(nombre, raising=False)
    for nombre, valor in variables.items():
        monkeypatch.setenv(nombre, valor)
    importlib.reload(config_mod)
    import app.services.ai_provider_service as servicio
    importlib.reload(servicio)
    return servicio


@pytest.fixture(autouse=True)
def _restaurar_configuracion():
    """Deja el módulo como estaba: otros tests leen `settings`.

    Auditoría 2026-11: volvía a recargar el módulo, y eso deja en
    `app.core.config.settings` un objeto NUEVO, mientras los servicios que ya
    hicieron `from app.core.config import settings` siguen con el viejo.
    Cualquier test posterior del mismo proceso que cambiara la configuración
    cambiaba el objeto equivocado: medido con -n 4, el de Redis (límite de
    login 0 en vez de 120) y los de correo entrante («Firma inválida»). Ahora
    se restaura el contenido exacto del módulo, con el mismo objeto.
    """
    import app.services.ai_provider_service as servicio
    antes_config, antes_servicio = dict(config_mod.__dict__), dict(servicio.__dict__)
    yield
    for modulo, antes in ((config_mod, antes_config), (servicio, antes_servicio)):
        modulo.__dict__.clear()
        modulo.__dict__.update(antes)


@pytest.mark.parametrize("proveedor", [
    "anthropic", "openai", "gemini", "deepseek", "groq", "mistral", "azure",
])
def test_cualquier_proveedor_se_puede_configurar_por_entorno(monkeypatch, proveedor):
    """Los siete que necesitan clave, configurables sólo con `.env`."""
    servicio = _recargar(monkeypatch, AI_PROVIDER=proveedor, AI_API_KEY="clave-de-prueba")
    p = servicio.proveedor_desde_entorno()
    assert p is not None, f"'{proveedor}' no se resuelve desde .env"
    assert p.provider == proveedor


def test_ollama_no_necesita_clave(monkeypatch):
    """Corre en la propia máquina: exigirle una clave lo dejaría inservible."""
    servicio = _recargar(monkeypatch, AI_PROVIDER="ollama")
    p = servicio.proveedor_desde_entorno()
    assert p is not None and p.provider == "ollama"


def test_la_clave_del_entorno_queda_cifrada(monkeypatch):
    """`call_provider` descifra siempre: un solo camino, no dos ramas."""
    from app.core.encryption import decrypt_value
    servicio = _recargar(monkeypatch, AI_PROVIDER="gemini", AI_API_KEY="secreta-123")
    p = servicio.proveedor_desde_entorno()
    assert p.api_key != "secreta-123", "la clave no debería viajar en claro"
    assert decrypt_value(p.api_key) == "secreta-123"


def test_anthropic_api_key_sigue_funcionando_como_alias(monkeypatch):
    """Ningún `.env` existente deja de funcionar por el cambio."""
    servicio = _recargar(monkeypatch, ANTHROPIC_API_KEY="clave-heredada")
    p = servicio.proveedor_desde_entorno()
    assert p is not None and p.provider == "anthropic"


def test_un_proveedor_desconocido_no_se_usa(monkeypatch):
    """Mejor sin IA que llamando a un sitio que no se sabe cuál es."""
    servicio = _recargar(monkeypatch, AI_PROVIDER="inventado", AI_API_KEY="x")
    assert servicio.proveedor_desde_entorno() is None


def test_un_proveedor_sin_clave_no_se_usa(monkeypatch):
    """Salvo los que corren en local, sin clave no hay llamada posible."""
    servicio = _recargar(monkeypatch, AI_PROVIDER="gemini")
    assert servicio.proveedor_desde_entorno() is None


def test_sin_configuracion_no_hay_proveedor(monkeypatch):
    """Y no pasa nada: la IA queda desactivada, no rota."""
    servicio = _recargar(monkeypatch)
    assert servicio.proveedor_desde_entorno() is None


def test_el_proveedor_de_la_base_gana_al_del_entorno(monkeypatch, db):
    """La organización manda sobre el despliegue. Es el orden del patrón.

    Si `.env` ganara, un despliegue multi-empresa no podría dar a cada
    organización su propio proveedor — que es justo lo que la base de datos
    aporta y el fichero de entorno no puede expresar.
    """
    from app.models.ai_providers import AIProvider
    from app.core.encryption import encrypt_value

    servicio = _recargar(monkeypatch, AI_PROVIDER="gemini", AI_API_KEY="del-entorno")
    db.add(AIProvider(
        name="OpenAI de la organización", provider="openai", status="active",
        api_key=encrypt_value("de-la-base"), is_default=True, is_active=True,
        organization_id=None,
    ))
    db.commit()

    elegido = servicio.get_default_provider(db, is_superadmin=True)
    assert elegido.provider == "openai", (
        "el proveedor de la base de datos debe ganar al del entorno")


def test_el_entorno_actua_cuando_la_base_no_tiene_ninguno(monkeypatch, db):
    """El último escalón: sin proveedor en la base, manda `.env`."""
    servicio = _recargar(monkeypatch, AI_PROVIDER="gemini", AI_API_KEY="del-entorno")
    elegido = servicio.get_default_provider(db, is_superadmin=True)
    assert elegido is not None and elegido.provider == "gemini"
    assert elegido.id is None, "el proveedor del entorno no se persiste"


def test_el_proveedor_del_entorno_no_acaba_en_la_sesion(monkeypatch, db):
    """No es una fila. Que no herede de `AIProvider` es deliberado."""
    from app.models.ai_providers import AIProvider
    servicio = _recargar(monkeypatch, AI_PROVIDER="gemini", AI_API_KEY="x")
    p = servicio.proveedor_desde_entorno()
    assert not isinstance(p, AIProvider)
    assert db.query(AIProvider).count() == 0
