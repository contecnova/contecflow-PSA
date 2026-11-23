"""Adaptador Recall.ai (https://docs.recall.ai) para el bot de reuniones.

- Alta: `POST /api/v1/bot/` con `meeting_url`, `bot_name`, `join_at`,
  transcripción por subtítulos de la propia reunión (sin otro tercero) y un
  mensaje al chat al entrar (aviso de grabación).
- Avisos: firmados al estilo Svix (`webhook-id`, `webhook-timestamp`,
  `webhook-signature: v1,<base64 HMAC-SHA256(id.timestamp.cuerpo)>`; el
  secreto `whsec_<base64>`). Ventana de 5 minutos.
- Transcripción: `GET /api/v1/bot/{id}/` → descarga del `media_shortcuts`;
  si no, `GET /api/v1/bot/{id}/transcript/` (formato anterior).
"""
from __future__ import annotations
import logging

import base64
import hashlib
import hmac
import time
from typing import Optional

import httpx

from app.services.reuniones.bots.base import ErrorDeBot, EventoDeBot, ProveedorDeBots

VENTANA_S = 300

#: Códigos de estado de Recall → estado normalizado.
ESTADOS = {
    "ready": "programada", "joining_call": "programada",
    "in_waiting_room": "bot_unido", "in_call_not_recording": "bot_unido",
    "recording_permission_allowed": "bot_unido", "recording_permission_denied": "error",
    "in_call_recording": "grabando",
    "call_ended": "terminada", "done": "terminada", "analysis_done": "terminada",
    "fatal": "error", "media_expired": "terminada",
}


def _plazo() -> float:
    try:
        from app.services.settings_service import outbound_http_timeout
        return outbound_http_timeout(default=20)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).debug("_plazo: excepcion ignorada", exc_info=True)
        return 20.0


def _ms(marca) -> Optional[int]:
    if isinstance(marca, dict):
        marca = marca.get("relative", marca.get("absolute"))
    if isinstance(marca, (int, float)):
        return int(float(marca) * 1000)
    return None


def segmentos_de(datos) -> list[dict]:
    """Los dos formatos de Recall a `{speaker, start_ms, end_ms, text}`."""
    salida = []
    for entrada in datos or []:
        palabras = entrada.get("words") or []
        texto = " ".join((w.get("text") or "").strip() for w in palabras).strip()
        if not texto:
            continue
        participante = entrada.get("participant") or {}
        quien = participante.get("name") or entrada.get("speaker")
        primero, ultimo = palabras[0], palabras[-1]
        inicio = _ms(primero.get("start_timestamp")) if "start_timestamp" in primero else _ms(primero.get("start_time"))
        fin = _ms(ultimo.get("end_timestamp")) if "end_timestamp" in ultimo else _ms(ultimo.get("end_time"))
        salida.append({"speaker": quien, "start_ms": inicio, "end_ms": fin, "text": texto,
                       "email": participante.get("email")})
    return salida


class RecallBots(ProveedorDeBots):
    nombre = "recall"

    def __init__(self, api_key: str, region: str = "eu-central-1", cliente: Optional[httpx.Client] = None):
        # 23-11-2026 (SSRF): la región entra en el HOST; con `x/#` o `169.254.169.254/?`
        # la clave salía a otro sitio. Solo una etiqueta DNS (p. ej. `eu-central-1`).
        import re
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", (region or "").strip().lower()):
            raise ErrorDeBot("credencial_rechazada", "región de Recall no válida")
        self.api_key, self.base = api_key, f"https://{region.strip().lower()}.recall.ai/api/v1"
        self._cliente = cliente

    def _http(self, metodo: str, ruta: str, **kw):
        cabeceras = {"Authorization": f"Token {self.api_key}", "Accept": "application/json"}
        try:
            if self._cliente is not None:
                r = self._cliente.request(metodo, f"{self.base}{ruta}", headers=cabeceras, **kw)
            else:
                with httpx.Client(timeout=_plazo()) as c:
                    r = c.request(metodo, f"{self.base}{ruta}", headers=cabeceras, **kw)
        except httpx.HTTPError as exc:
            raise ErrorDeBot("conector_no_responde", str(exc)) from exc
        if r.status_code in (401, 403):
            raise ErrorDeBot("credencial_rechazada", r.text[:200])
        if r.status_code == 404:
            raise ErrorDeBot("reuniones_plataforma_no_encontrada", r.text[:200])
        if r.status_code >= 400:
            raise ErrorDeBot("conector_rechazado", r.text[:300])
        return r.json() if r.content and "json" in r.headers.get("content-type", "json") else {}

    def crear_bot(self, url_reunion, *, nombre_bot, mensaje_al_entrar, unirse_en=None, metadatos=None):
        cuerpo = {
            "meeting_url": url_reunion,
            "bot_name": nombre_bot,
            "recording_config": {"transcript": {"provider": {"meeting_captions": {}}}},
            "chat": {"on_bot_join": {"send_to": "everyone", "message": mensaje_al_entrar[:4000]}},
            "metadata": metadatos or {},
        }
        if unirse_en:
            cuerpo["join_at"] = unirse_en
        datos = self._http("POST", "/bot/", json=cuerpo)
        cambios = datos.get("status_changes") or []
        crudo = (cambios[-1].get("code") if cambios else None) or "ready"
        return {"id": datos.get("id"), "estado": ESTADOS.get(crudo, "programada")}

    def estado(self, bot_id):
        datos = self._http("GET", f"/bot/{bot_id}/")
        cambios = datos.get("status_changes") or []
        return ESTADOS.get(cambios[-1].get("code") if cambios else "ready", "programada")

    def salir(self, bot_id):
        self._http("POST", f"/bot/{bot_id}/leave_call/")

    def transcripcion(self, bot_id):
        datos = self._http("GET", f"/bot/{bot_id}/")
        for grabacion in datos.get("recordings") or []:
            trans = ((grabacion.get("media_shortcuts") or {}).get("transcript") or {}).get("data") or {}
            url = trans.get("download_url")
            if url:
                try:
                    with httpx.Client(timeout=_plazo()) as c:
                        r = c.get(url)
                    r.raise_for_status()
                    return segmentos_de(r.json())
                except httpx.HTTPError as exc:
                    raise ErrorDeBot("conector_no_responde", str(exc)) from exc
        return segmentos_de(self._http("GET", f"/bot/{bot_id}/transcript/"))

    def borrar_medios(self, bot_id):
        self._http("POST", f"/bot/{bot_id}/delete_media/")

    def verificar_firma(self, cabeceras, cuerpo, secreto):
        h = {k.lower(): v for k, v in (cabeceras or {}).items()}
        ident = h.get("webhook-id") or h.get("svix-id")
        marca = h.get("webhook-timestamp") or h.get("svix-timestamp")
        firmas = h.get("webhook-signature") or h.get("svix-signature") or ""
        if not (secreto and ident and marca and firmas):
            return False
        try:
            if abs(time.time() - int(marca)) > VENTANA_S:
                return False
        except ValueError:
            return False
        clave_txt = secreto.split("_", 1)[1] if secreto.startswith("whsec_") else secreto
        try:
            clave = base64.b64decode(clave_txt)
        except (ValueError, TypeError):
            clave = clave_txt.encode()
        firmado = f"{ident}.{marca}.".encode() + cuerpo
        esperada = base64.b64encode(hmac.new(clave, firmado, hashlib.sha256).digest()).decode()
        for parte in firmas.split():
            version, _, valor = parte.partition(",")
            if version == "v1" and hmac.compare_digest(valor, esperada):
                return True
        return False

    def interpretar_evento(self, carga):
        datos = carga.get("data") or {}
        bot = datos.get("bot") or {}
        bot_id = bot.get("id") or datos.get("bot_id")
        if not bot_id:
            return None
        interno = datos.get("data") or datos.get("status") or {}
        crudo = interno.get("code") or (carga.get("event") or "").split(".")[-1]
        return EventoDeBot(bot_id=bot_id, estado=ESTADOS.get(crudo), estado_crudo=crudo or "",
                           datos={"event": carga.get("event"), "sub_code": interno.get("sub_code")})
