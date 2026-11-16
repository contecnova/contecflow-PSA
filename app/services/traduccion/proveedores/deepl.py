"""Proveedor de traduccion: DeepL API (v2, `POST /v2/translate`).

Credenciales de la empresa (`deepl`): `api_key` y, opcional, `base_url`. Sin
`base_url`, la URL del plan de la clave: una clave que termina en `:fx` es del
plan Free (`api-free.deepl.com`), las demas del Pro (`api.deepl.com`), segun la
documentacion de DeepL.

Glosario: con terminos en el texto se envia con `tag_handling=xml` y cada
termino, ya con su salida, dentro de `<x>`, que se declara en `ignore_tags`.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.services.traduccion import glosario as _glosario
from app.services.traduccion.idiomas import normalizar
from app.services.traduccion.proveedores.base import (ErrorDeTraduccion, ProveedorDeTraduccion, Traducido,
                                                      credenciales_de_la_empresa, publicar_json)

URL_FREE = "https://api-free.deepl.com"
URL_PRO = "https://api.deepl.com"
SUFIJO_FREE = ":fx"
RUTA = "/v2/translate"
_ETIQUETA = "x"
_APERTURA, _CIERRE = f"<{_ETIQUETA}>", f"</{_ETIQUETA}>"

#: Idiomas destino de DeepL (codigo propio -> codigo de DeepL).
DESTINOS = {
    "ar": "AR", "bg": "BG", "cs": "CS", "da": "DA", "de": "DE", "el": "EL", "en": "EN-US", "es": "ES",
    "et": "ET", "fi": "FI", "fr": "FR", "hu": "HU", "id": "ID", "it": "IT", "ja": "JA", "ko": "KO",
    "lt": "LT", "lv": "LV", "nb": "NB", "nl": "NL", "pl": "PL", "pt": "PT-PT", "ro": "RO", "ru": "RU",
    "sk": "SK", "sl": "SL", "sv": "SV", "tr": "TR", "uk": "UK", "zh": "ZH-HANS", "zh-hant": "ZH-HANT",
}


def _origen(codigo: Optional[str]) -> Optional[str]:
    if not codigo:
        return None
    destino = DESTINOS.get(codigo)
    return destino.split("-")[0] if destino else None


class ProveedorDeepL(ProveedorDeTraduccion):
    nombre = "deepl"

    def __init__(self, db: Session, org_id: Optional[str], credenciales: Optional[dict] = None, http=None):
        self.db, self.org_id = db, org_id
        self.cred = credenciales if credenciales is not None else credenciales_de_la_empresa(db, "deepl", org_id)
        # Los tests sustituyen la salida HTTP por un doble con la misma firma.
        self.http = http or publicar_json

    def configurado(self) -> bool:
        return bool((self.cred.get("api_key") or "").strip())

    def admite(self, destino: str) -> bool:
        return destino in DESTINOS

    def _url(self) -> str:
        base = (self.cred.get("base_url") or "").strip().rstrip("/")
        if not base:
            base = URL_FREE if (self.cred.get("api_key") or "").strip().endswith(SUFIJO_FREE) else URL_PRO
        return base + RUTA

    def traducir(self, textos, destino, origen, glosarios):
        if not self.configurado():
            raise ErrorDeTraduccion("provider_not_configured")
        if not self.admite(destino):
            raise ErrorDeTraduccion("unsupported_language")
        con_marcas = any(glosarios)
        cuerpo = {"text": [(_glosario.proteger(t, g, _APERTURA, _CIERRE) if con_marcas else t)
                           for t, g in zip(textos, glosarios)],
                  "target_lang": DESTINOS[destino]}
        if _origen(origen):
            cuerpo["source_lang"] = _origen(origen)
        if con_marcas:
            cuerpo.update({"tag_handling": "xml", "ignore_tags": [_ETIQUETA]})
        datos = self.http(self.db, self._url(), metrica="translation_deepl",
                          headers={"Authorization": f"DeepL-Auth-Key {self.cred['api_key'].strip()}"}, json=cuerpo)
        filas = (datos or {}).get("translations") if isinstance(datos, dict) else None
        if not isinstance(filas, list) or len(filas) != len(textos):
            raise ErrorDeTraduccion("incomplete_response")
        salida = []
        for f in filas:
            texto = str((f or {}).get("text") or "")
            if con_marcas:
                texto = _glosario.desproteger(texto, _APERTURA, _CIERRE)
            salida.append(Traducido(texto, normalizar((f or {}).get("detected_source_language"))))
        return salida
