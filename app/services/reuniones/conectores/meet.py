"""Google Meet (API REST de Meet v2) con cuenta de servicio y delegación de dominio.

La empresa da de alta una cuenta de servicio con delegación en todo el dominio
y el ámbito `https://www.googleapis.com/auth/meetings.space.readonly`. Se firma
un JWT RS256 (PyJWT) en nombre de cada persona que activó «recoger mis
reuniones de Meet» (`sub` = su correo), y se leen sus `conferenceRecords`
terminados, sus transcripciones (`transcripts/*/entries`) y participantes.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.core.codigos_de_error import ErrorConCodigo
from app.core.config import settings
from app.services.reuniones import config
from app.services.reuniones.conectores import Importable, exigir_activo, http

PLATAFORMA = "Google Meet"
API = "https://meet.googleapis.com/v2"
AMBITO = "https://www.googleapis.com/auth/meetings.space.readonly"


def _clave(db: Session, org: Optional[str]) -> dict:
    texto = config.secreto(db, org, "meet", "service_account_key")
    if not texto:
        raise ErrorConCodigo("reuniones_conector_sin_credenciales", plataforma=PLATAFORMA)
    try:
        return json.loads(texto)
    except ValueError:
        raise ErrorConCodigo("reuniones_formato_no_valido", detail="La clave de la cuenta de servicio no es JSON")


def token(db: Session, org: Optional[str], correo: str) -> str:
    import jwt
    cfg = config.leer(db, org)
    exigir_activo(cfg, "meet", PLATAFORMA)
    clave = _clave(db, org)
    ahora = int(time.time())
    afirmacion = jwt.encode({"iss": clave.get("client_email") or cfg["meet"].get("service_account_email"),
                             "sub": correo, "scope": AMBITO, "aud": settings.GOOGLE_TOKEN_URL, "iat": ahora, "exp": ahora + 3600},
                            clave.get("private_key", ""), algorithm="RS256")
    r = http("POST", settings.GOOGLE_TOKEN_URL, plataforma=PLATAFORMA,
             data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": afirmacion})
    return r.json()["access_token"]


def _get(tk: str, ruta: str):
    return http("GET", f"{API}/{ruta}", plataforma=PLATAFORMA, headers={"Authorization": f"Bearer {tk}"}).json()


def _importable(tk: str, registro: dict) -> Optional[Importable]:
    nombre = registro["name"]   # conferenceRecords/abc
    transcripciones = _get(tk, f"{nombre}/transcripts").get("transcripts") or []
    if not transcripciones:
        return None
    nombres: dict[str, str] = {}
    participantes = []
    for p in _get(tk, f"{nombre}/participants").get("participants") or []:
        quien = ((p.get("signedinUser") or {}).get("displayName") or (p.get("anonymousUser") or {}).get("displayName")
                 or (p.get("phoneUser") or {}).get("displayName"))
        nombres[p.get("name", "")] = quien
        participantes.append({"name": quien, "email": None, "role": "asistente"})
    segmentos, inicio_ref = [], None
    for t in transcripciones:
        siguiente = ""
        while True:
            pagina = _get(tk, f"{t['name']}/entries?pageSize=100" + (f"&pageToken={siguiente}" if siguiente else ""))
            for e in pagina.get("transcriptEntries") or []:
                inicio = e.get("startTime")
                if inicio and inicio_ref is None:
                    inicio_ref = inicio
                segmentos.append({"speaker": nombres.get(e.get("participant", "")), "text": e.get("text", ""),
                                  "start_iso": inicio, "end_iso": e.get("endTime"),
                                  "language": (e.get("languageCode") or "")[:2] or None})
            siguiente = pagina.get("nextPageToken") or ""
            if not siguiente:
                break
    base = _iso(registro.get("startTime"))
    for s in segmentos:
        a, b = _iso(s.pop("start_iso")), _iso(s.pop("end_iso"))
        s["start_ms"] = int((a - base).total_seconds() * 1000) if a and base else None
        s["end_ms"] = int((b - base).total_seconds() * 1000) if b and base else None
    idioma = next((s.get("language") for s in segmentos if s.get("language")), None)
    return Importable(origin="meet", external_id=nombre.split("/")[-1], title=None,
                      meeting_date=registro.get("startTime"), ends_at=registro.get("endTime"),
                      participants=participantes, segments=segmentos, language=idioma)


def _iso(v) -> Optional[datetime]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")[:32])
    except ValueError:
        return None


def terminadas_de(db: Session, org: Optional[str], correo: str, horas: int = 24) -> list[Importable]:
    tk = token(db, org, correo)
    desde = (datetime.now(timezone.utc) - timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%SZ")
    filtro = quote(f'end_time>="{desde}"', safe="")
    salida = []
    for r in _get(tk, f"conferenceRecords?filter={filtro}").get("conferenceRecords") or []:
        if not r.get("endTime"):
            continue
        imp = _importable(tk, r)
        if imp is not None:
            imp.organizer_email = correo
            salida.append(imp)
    return salida


def por_referencia(db: Session, org: Optional[str], correo: str, referencia: str) -> Importable:
    """`referencia`: id del registro, o código / URL de la reunión (`abc-defg-hij`)."""
    tk = token(db, org, correo)
    ref = referencia.strip().rstrip("/").split("/")[-1].split("?")[0]
    if "-" in ref and len(ref) <= 14:
        filtro = quote(f'space.meeting_code="{ref}"', safe="")
        registros = _get(tk, f"conferenceRecords?filter={filtro}").get("conferenceRecords") or []
        registro = registros[0] if registros else None
    else:
        registro = _get(tk, f"conferenceRecords/{ref}")
    imp = _importable(tk, registro) if registro else None
    if imp is None:
        raise ErrorConCodigo("reuniones_plataforma_no_encontrada", plataforma=PLATAFORMA)
    imp.organizer_email = correo
    return imp


def probar(db: Session, org: Optional[str], correo: str) -> dict:
    token(db, org, correo)
    return {"ok": True, "detail": "token de Google obtenido"}


__all__ = ["terminadas_de", "por_referencia", "probar", "token"]
