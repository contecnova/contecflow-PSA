"""Firma de Twilio detrás de nginx (segunda auditoría 2026-11, #23).

Twilio firma `https://<dominio>/…`; nginx (que no termina TLS) llamaba a la API
por http desde otra IP de la red de compose, y la API comprobaba la firma contra
`http://…`: toda petición daba 403. Se simula esa petición reenviada.
"""
from __future__ import annotations

import base64
import hashlib
import hmac

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

import app.core.network as red
from app.core.network import EsquemaDelProxyMiddleware, extract_client_ip
from app.services.service_desk.sms_service import firma_de_twilio_valida, urls_de_firma_de_twilio

TOKEN = "token-de-twilio-de-prueba"
RUTA = "/api/v1/sd/multichannel/inbound/sms"
FORM = {"From": "+34600000001", "To": "+34600000002", "Body": "hola"}
NGINX = ("172.20.0.5", 40000)  # IP de nginx en la red de compose


def _firma_de_twilio(url: str) -> str:
    datos = url + "".join(f"{k}{FORM[k]}" for k in sorted(FORM))
    return base64.b64encode(hmac.new(TOKEN.encode(), datos.encode(), hashlib.sha1).digest()).decode()


async def _webhook(request: Request):
    form = dict(await request.form())
    return JSONResponse({
        "url": str(request.url),
        "ip": extract_client_ip(request),
        "valida": firma_de_twilio_valida(urls_de_firma_de_twilio(request), form,
                                         request.headers.get("X-Twilio-Signature"), TOKEN),
    })


def _llamar(cabeceras: dict, *, cliente=NGINX) -> dict:
    app = EsquemaDelProxyMiddleware(Starlette(routes=[Route(RUTA, _webhook, methods=["POST"])]))
    transporte = httpx.ASGITransport(app=app, client=cliente)

    async def _post():
        async with httpx.AsyncClient(transport=transporte, base_url="http://app.ejemplo.com") as c:
            return (await c.post(RUTA, data=FORM, headers=cabeceras)).json()

    import asyncio
    return asyncio.run(_post())


@pytest.fixture
def proxy(monkeypatch):
    """Lo que fija docker-compose.yml para el servicio `api`."""
    monkeypatch.setattr(red.settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(red.settings, "TRUSTED_PROXY_CIDRS", "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16")
    # La configuración efectiva se cachea 5 min; sin BD de por medio en este test.
    monkeypatch.setattr(red, "_effective_proxy_config",
                        lambda: (red.settings.TRUST_PROXY_HEADERS, red.settings.TRUSTED_PROXY_CIDRS))


def test_peticion_reenviada_por_nginx_valida_la_firma_https(proxy, monkeypatch):
    # BACKEND_URL sin configurar (localhost): solo vale el esquema que trae nginx.
    monkeypatch.setattr(red.settings, "BACKEND_URL", "http://localhost:8000")
    publica = f"https://app.ejemplo.com{RUTA}"
    r = _llamar({"X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.9, 172.20.0.1",
                 "X-Twilio-Signature": _firma_de_twilio(publica)})
    assert r["url"] == publica
    assert r["valida"] is True
    # Y la IP es la del cliente, no la de nginx ni la del gateway de Docker.
    assert r["ip"] == "203.0.113.9"


def test_la_ip_falsificada_a_la_izquierda_no_se_cree(proxy):
    r = _llamar({"X-Forwarded-For": "1.2.3.4, 203.0.113.9, 172.20.0.1"})
    assert r["ip"] == "203.0.113.9"


def test_la_url_publica_de_backend_url_valida_aunque_el_proxy_no_diga_el_esquema(monkeypatch):
    """Sin confianza en el proxy, `request.url` sale en http; BACKEND_URL basta."""
    monkeypatch.setattr(red.settings, "TRUST_PROXY_HEADERS", False)
    monkeypatch.setattr(red, "_effective_proxy_config", lambda: (False, ""))
    monkeypatch.setattr(red.settings, "BACKEND_URL", "https://app.ejemplo.com")
    r = _llamar({"X-Twilio-Signature": _firma_de_twilio(f"https://app.ejemplo.com{RUTA}")})
    assert r["url"].startswith("http://")
    assert r["valida"] is True


def test_un_cliente_que_no_es_proxy_no_cambia_el_esquema(proxy, monkeypatch):
    monkeypatch.setattr(red.settings, "BACKEND_URL", "http://localhost:8000")
    r = _llamar({"X-Forwarded-Proto": "https",
                 "X-Twilio-Signature": _firma_de_twilio(f"https://app.ejemplo.com{RUTA}")},
                cliente=("203.0.113.50", 5555))
    assert r["url"].startswith("http://")
    assert r["valida"] is False


def test_firma_de_otra_ruta_no_vale(proxy, monkeypatch):
    monkeypatch.setattr(red.settings, "BACKEND_URL", "https://app.ejemplo.com")
    r = _llamar({"X-Forwarded-Proto": "https",
                 "X-Twilio-Signature": _firma_de_twilio("https://app.ejemplo.com/api/v1/otra")})
    assert r["valida"] is False
