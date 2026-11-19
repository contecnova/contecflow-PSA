"""Comprobación de arranque: sin respaldos de desarrollo en producción (19-11-2026).

Auditoría de hardcodeados: varios ajustes caían en silencio a valores de
desarrollo (`localhost`, remitentes `@contecflow.local`, DocuSign en modo demo)
que en producción no fallan al arrancar sino al usarse: el correo sale con un
remitente que rebota, la búsqueda apunta a un OpenSearch que no existe, el bus
de eventos a un Redis local, los enlaces del resumen de chat a localhost:3000…

`problemas(settings)` devuelve la lista de lo que no vale en staging/producción
(vacía en desarrollo y pruebas) y `exigir()` no deja arrancar si hay alguno
(lo llama `app/main.py` junto a `_enforce_security_switches_safety`). Mismo
criterio que los validadores de `FRONTEND_URL`/`ALLOWED_ORIGINS` de `Settings`.

Resolución de valores con respaldo (un solo sitio):
- `url_publica_de_la_app()`: `APP_PUBLIC_URL` o, vacío, `FRONTEND_URL`.
- `docusign_es_demo(valor_guardado)`: el ajuste de la empresa si lo hay; si no,
  `DOCUSIGN_DEMO`; si tampoco, demo solo fuera de staging/producción.
- `adobe_sign_base_url(valor_guardado)`: el de la empresa, el del entorno o, solo
  fuera de producción, na1.
- `github_api_base(config)`, `github_web_base(config)`, `gitlab_base(config)`:
  la de la integración (`config["api_base"]`/`["web_base"]`/`["base_url"]`) o
  la de la instalación (GitHub Enterprise Server, GitLab propio).
"""
from __future__ import annotations

from typing import Any, Optional

from app.core.config import settings

ENTORNOS_REALES = {"production", "staging"}


def _es_local(url: Optional[str]) -> bool:
    u = (url or "").lower()
    return any(x in u for x in ("localhost", "127.0.0.1", "0.0.0.0", "[::1]"))  # noqa: S104


def _dominio_de_ejemplo(direccion: Optional[str]) -> bool:
    d = (direccion or "").lower().strip()
    return d.endswith(".local") or d.endswith("@example.com") or "contecflow.local" in d


def es_entorno_real(s: Any = None) -> bool:
    return str(getattr(s or settings, "ENVIRONMENT", "") or "").lower() in ENTORNOS_REALES


# ── Valores resueltos ────────────────────────────────────────────────────────

def url_publica_de_la_app(s: Any = None) -> str:
    s = s or settings
    return (getattr(s, "APP_PUBLIC_URL", "") or s.FRONTEND_URL or "").rstrip("/")


def docusign_es_demo(valor_guardado: Optional[str] = None, s: Any = None) -> bool:
    s = s or settings
    if valor_guardado not in (None, ""):
        return str(valor_guardado).strip().lower() == "true"
    if s.DOCUSIGN_DEMO is not None:
        return bool(s.DOCUSIGN_DEMO)
    return not es_entorno_real(s)


def docusign_api_base(es_demo: bool, s: Any = None) -> str:
    s = s or settings
    return s.DOCUSIGN_API_BASE_DEMO if es_demo else s.DOCUSIGN_API_BASE_PROD


def docusign_auth_base(es_demo: bool, s: Any = None) -> str:
    s = s or settings
    return s.DOCUSIGN_AUTH_BASE_DEMO if es_demo else s.DOCUSIGN_AUTH_BASE_PROD


def adobe_sign_base_url(valor_guardado: Optional[str] = None, s: Any = None) -> str:
    s = s or settings
    if valor_guardado:
        return valor_guardado
    if s.ADOBE_SIGN_BASE_URL:
        return s.ADOBE_SIGN_BASE_URL
    if es_entorno_real(s):
        raise RuntimeError("ADOBE_SIGN_BASE_URL sin configurar: es la URL de la región de la cuenta de Adobe Sign")
    return s.ADOBE_SIGN_DEV_BASE_URL


def _de_config(config: Any, clave: str) -> Optional[str]:
    if isinstance(config, dict):
        v = config.get(clave)
        return str(v).rstrip("/") if v else None
    return None


def github_api_base(config: Any = None) -> str:
    return _de_config(config, "api_base") or settings.GITHUB_API_BASE.rstrip("/")


def github_web_base(config: Any = None) -> str:
    return _de_config(config, "web_base") or settings.GITHUB_WEB_BASE.rstrip("/")


def gitlab_base(config: Any = None) -> str:
    return _de_config(config, "base_url") or settings.GITLAB_BASE_URL.rstrip("/")


# ── Comprobación de arranque ─────────────────────────────────────────────────

def problemas(s: Any = None) -> list[str]:
    """Lo que no vale en staging/producción (vacío en desarrollo y pruebas)."""
    s = s or settings
    if not es_entorno_real(s):
        return []
    entorno = s.ENVIRONMENT
    fallos: list[str] = []
    if s.APP_PUBLIC_URL and _es_local(s.APP_PUBLIC_URL):
        fallos.append(f"APP_PUBLIC_URL apunta a localhost en {entorno} ({s.APP_PUBLIC_URL}); déjalo vacío (usa FRONTEND_URL) o pon la URL pública")
    if str(s.COLLAB_SEARCH_BACKEND).lower() == "opensearch" and _es_local(s.OPENSEARCH_URL):
        fallos.append(f"COLLAB_SEARCH_BACKEND=opensearch con OPENSEARCH_URL en localhost ({s.OPENSEARCH_URL})")
    bus = str(s.COLLAB_BUS_BACKEND).lower()
    if bus == "redis" and (not getattr(s, "REDIS_URL", None) or _es_local(s.REDIS_URL)):
        fallos.append("COLLAB_BUS_BACKEND=redis sin REDIS_URL real (el bus caería a redis://localhost)")
    if bus == "nats" and _es_local(s.NATS_URL):
        fallos.append(f"COLLAB_BUS_BACKEND=nats con NATS_URL en localhost ({s.NATS_URL})")
    if not getattr(s, "SMTP_FROM", None) and _dominio_de_ejemplo(s.NOTIFICATION_EMAIL_FROM):
        fallos.append(f"Remitente de correo de ejemplo ({s.NOTIFICATION_EMAIL_FROM}): configura SMTP_FROM o NOTIFICATION_EMAIL_FROM con un dominio real")
    if getattr(s, "VAPID_PRIVATE_KEY", None) and _dominio_de_ejemplo(s.VAPID_CONTACT.replace("mailto:", "")):
        fallos.append(f"VAPID_CONTACT de ejemplo ({s.VAPID_CONTACT}) con notificaciones push activas")
    if entorno == "production" and s.DOCUSIGN_DEMO is True:
        fallos.append("DOCUSIGN_DEMO=true en producción: las firmas no tendrían validez legal")
    if (s.ADOBE_SIGN_CLIENT_ID or "").strip() and not (s.ADOBE_SIGN_BASE_URL or "").strip():
        fallos.append("ADOBE_SIGN_CLIENT_ID configurado sin ADOBE_SIGN_BASE_URL (la región de la cuenta)")
    return fallos


def exigir(s: Any = None) -> None:
    """No arranca en staging/producción con respaldos de desarrollo."""
    fallos = problemas(s)
    if fallos:
        raise RuntimeError("Configuración de desarrollo en un entorno real; no arranca:\n- " + "\n- ".join(fallos))
