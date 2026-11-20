"""Zoom: aviso `recording.completed` firmado + Server-to-Server OAuth.

- Firma: `x-zm-signature = v0=<hex HMAC-SHA256(secreto, "v0:{x-zm-request-timestamp}:{cuerpo}")>`,
  con la marca dentro de 5 minutos.
- Validación de la URL (`endpoint.url_validation`): se responde
  `{plainToken, encryptedToken = hex HMAC-SHA256(secreto, plainToken)}`.
- Transcripción: el fichero `TRANSCRIPT` (VTT) de `recording_files`, con el
  `download_token` del aviso o con el token OAuth de la cuenta.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Optional
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.core.codigos_de_error import ErrorConCodigo
from app.services.reuniones import config
from app.services.reuniones.conectores import Importable, exigir_activo, http
from app.services.reuniones.transcripcion import de_vtt

PLATAFORMA = "Zoom"
API = "https://api.zoom.us/v2"
VENTANA_S = 300


def firma_valida(secreto: str, marca: str, firma: str, cuerpo: bytes) -> bool:
    if not (secreto and marca and firma):
        return False
    try:
        if abs(time.time() - int(marca)) > VENTANA_S:
            return False
    except ValueError:
        return False
    esperado = "v0=" + hmac.new(secreto.encode(), f"v0:{marca}:".encode() + cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, firma)


def respuesta_de_validacion(secreto: str, plano: str) -> dict:
    return {"plainToken": plano,
            "encryptedToken": hmac.new(secreto.encode(), plano.encode(), hashlib.sha256).hexdigest()}


def token(db: Session, org: Optional[str]) -> str:
    cfg = config.leer(db, org)
    exigir_activo(cfg, "zoom", PLATAFORMA)
    z = cfg["zoom"]
    secreto = config.secreto(db, org, "zoom", "client_secret")
    if not (z.get("account_id") and z.get("client_id") and secreto):
        raise ErrorConCodigo("reuniones_conector_sin_credenciales", plataforma=PLATAFORMA)
    basica = base64.b64encode(f"{z['client_id']}:{secreto}".encode()).decode()
    r = http("POST", f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={z['account_id']}",
             plataforma=PLATAFORMA, headers={"Authorization": f"Basic {basica}"})
    return r.json()["access_token"]


def de_grabacion(db: Session, org: Optional[str], objeto: dict, download_token: Optional[str] = None
                 ) -> Optional[Importable]:
    """El objeto `recording` de Zoom (aviso o API) a reunión importable (None sin transcripción)."""
    fichero = next((f for f in objeto.get("recording_files") or []
                    if (f.get("file_type") or "").upper() == "TRANSCRIPT" and f.get("download_url")), None)
    if fichero is None:
        return None
    if download_token:
        cabeceras = {"Authorization": f"Bearer {download_token}"}
    else:
        cabeceras = {"Authorization": f"Bearer {token(db, org)}"}
    vtt = http("GET", fichero["download_url"], plataforma=PLATAFORMA, headers=cabeceras).text
    fin = None
    if objeto.get("start_time") and objeto.get("duration"):
        from datetime import datetime, timedelta
        try:
            inicio = datetime.fromisoformat(str(objeto["start_time"]).replace("Z", "+00:00"))
            fin = (inicio + timedelta(minutes=int(objeto["duration"]))).isoformat()
        except (ValueError, TypeError):
            fin = None
    return Importable(origin="zoom", external_id=str(objeto.get("uuid") or objeto.get("id")),
                      title=objeto.get("topic"), meeting_date=objeto.get("start_time"), ends_at=fin,
                      join_url=objeto.get("share_url"), organizer_email=objeto.get("host_email"),
                      participants=([{"name": None, "email": objeto["host_email"], "role": "organizador"}]
                                    if objeto.get("host_email") else []),
                      segments=de_vtt(vtt))


def por_referencia(db: Session, org: Optional[str], referencia: str) -> Importable:
    tk = token(db, org)
    ref = referencia.strip()
    # Un UUID de Zoom que empieza por «/» o contiene «//» va doblemente codificado;
    # una URL de unión (`.../j/123456789?pwd=`) se queda con el número.
    if ref.startswith("http"):
        ident = ref.rstrip("/").split("/")[-1].split("?")[0]
    elif ref.startswith("/") or "//" in ref:
        ident = quote(quote(ref, safe=""), safe="")
    else:
        ident = quote(ref, safe="")
    objeto = http("GET", f"{API}/meetings/{ident}/recordings", plataforma=PLATAFORMA,
                  headers={"Authorization": f"Bearer {tk}"}).json()
    imp = de_grabacion(db, org, objeto)
    if imp is None:
        raise ErrorConCodigo("reuniones_plataforma_no_encontrada", plataforma=PLATAFORMA)
    return imp


def probar(db: Session, org: Optional[str]) -> dict:
    token(db, org)
    return {"ok": True, "detail": "token de Zoom obtenido"}
