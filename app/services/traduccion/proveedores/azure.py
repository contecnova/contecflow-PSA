"""Proveedor de traduccion: Azure AI Translator (Text Translation v3.0, `POST /translate`).

Credenciales de la empresa (`azure_translator`): `api_key`, `region` (si el
recurso es regional) y, opcional, `endpoint` (sin el, el endpoint global de
Translator).

Glosario: con terminos en el texto se envia como HTML (`textType=html`) y cada
termino, ya con su salida, dentro de `<span class="notranslate">`, que
Translator deja intacto.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.services.traduccion import glosario as _glosario
from app.services.traduccion.idiomas import IDIOMAS, normalizar
from app.services.traduccion.proveedores.base import (ErrorDeTraduccion, ProveedorDeTraduccion, Traducido,
                                                      credenciales_de_la_empresa, publicar_json)

ENDPOINT_GLOBAL = "https://api.cognitive.microsofttranslator.com"
RUTA = "/translate"
VERSION_DE_API = "3.0"
_APERTURA, _CIERRE = '<span class="notranslate">', "</span>"

#: Codigos propios que en Translator se escriben distinto.
CODIGOS = {"zh": "zh-Hans", "zh-hant": "zh-Hant"}


def _codigo(c: str) -> str:
    return CODIGOS.get(c, c)


class ProveedorAzure(ProveedorDeTraduccion):
    nombre = "azure"

    def __init__(self, db: Session, org_id: Optional[str], credenciales: Optional[dict] = None, http=None):
        self.db, self.org_id = db, org_id
        self.cred = (credenciales if credenciales is not None
                     else credenciales_de_la_empresa(db, "azure_translator", org_id))
        self.http = http or publicar_json

    def configurado(self) -> bool:
        return bool((self.cred.get("api_key") or "").strip())

    def admite(self, destino: str) -> bool:
        return destino in IDIOMAS

    def traducir(self, textos, destino, origen, glosarios):
        if not self.configurado():
            raise ErrorDeTraduccion("provider_not_configured")
        con_marcas = any(glosarios)
        params = {"api-version": VERSION_DE_API, "to": _codigo(destino)}
        if origen:
            params["from"] = _codigo(origen)
        if con_marcas:
            params["textType"] = "html"
        cabeceras = {"Ocp-Apim-Subscription-Key": self.cred["api_key"].strip(), "Content-Type": "application/json"}
        region = (self.cred.get("region") or "").strip()
        if region:
            cabeceras["Ocp-Apim-Subscription-Region"] = region
        base = (self.cred.get("endpoint") or "").strip().rstrip("/") or ENDPOINT_GLOBAL
        cuerpo = [{"Text": (_glosario.proteger(t, g, _APERTURA, _CIERRE) if con_marcas else t)}
                  for t, g in zip(textos, glosarios)]
        datos = self.http(self.db, base + RUTA, metrica="translation_azure", headers=cabeceras, json=cuerpo,
                          params=params)
        if not isinstance(datos, list) or len(datos) != len(textos):
            raise ErrorDeTraduccion("incomplete_response")
        salida = []
        for fila in datos:
            traducciones = (fila or {}).get("translations") or []
            if not traducciones:
                raise ErrorDeTraduccion("bad_response")
            texto = str(traducciones[0].get("text") or "")
            if con_marcas:
                texto = _glosario.desproteger(texto, _APERTURA, _CIERRE)
            detectado = ((fila or {}).get("detectedLanguage") or {}).get("language")
            salida.append(Traducido(texto, normalizar(detectado) or origen))
        return salida
