"""Proveedor de traduccion: el proveedor de IA que ya tiene configurado la empresa.

Va por `call_ai` (modulo `translation`), asi que hereda todo lo de la IA de la
aplicacion: proveedor y modelo por funcion (Hub de IA), respaldo, gobernanza,
registro de uso y **tope diario de gasto** de la empresa
(`PresupuestoDeIAAgotado` -> `budget_exhausted`).

Las instrucciones al modelo van en ingles y se construyen con el idioma
destino: no hay un texto fijo por idioma. Se pide JSON con un elemento por
texto, en el mismo orden; si la respuesta no trae exactamente los mismos
elementos, es un error (nunca una traduccion a medias).
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.services.traduccion.idiomas import IDIOMAS, normalizar
from app.services.traduccion.proveedores.base import ErrorDeTraduccion, ProveedorDeTraduccion, Traducido

MODULO_DE_IA = "translation"


def instrucciones(destino: str, origen: Optional[str], glosarios: list[list]) -> str:
    nombre = IDIOMAS.get(destino, destino)
    lineas = [
        "You are a professional translator for a customer service team.",
        f"Translate the text of every item of the JSON array into {nombre} (language code {destino}).",
        (f"The source language is {IDIOMAS.get(origen, origen)} ({origen})." if origen
         else "Detect the source language of each item."),
        "Keep the meaning, tone and formatting: line breaks, lists, markdown, URLs, e-mail addresses, "
        "numbers, code, ticket numbers and placeholders stay exactly as they are.",
        "Do not answer, summarise, explain or add anything: only translate.",
        "If an item is already in the target language, return it unchanged.",
    ]
    terminos = {}
    for pares in glosarios:
        for termino, salida in pares:
            terminos[termino.termino] = salida
    if terminos:
        lineas.append("Mandatory glossary (source term -> exact output, never translate it otherwise):")
        lineas.extend(f'- "{t}" -> "{s}"' for t, s in terminos.items())
    lineas.append('Reply ONLY with JSON: {"items": [{"lang": "<ISO 639-1 code of the source>", "text": "<translation>"}]} '
                  "with exactly one element per input item, in the same order.")
    return "\n".join(lineas)


def _leer(respuesta: str, esperados: int) -> list[Traducido]:
    texto = (respuesta or "").strip()
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio < 0 or fin <= inicio:
        raise ErrorDeTraduccion("bad_response")
    try:
        datos = json.loads(texto[inicio:fin + 1])
    except ValueError as exc:
        raise ErrorDeTraduccion("bad_response") from exc
    items = datos.get("items") if isinstance(datos, dict) else None
    if not isinstance(items, list) or len(items) != esperados:
        raise ErrorDeTraduccion("incomplete_response")
    salida = []
    for it in items:
        if not isinstance(it, dict) or not isinstance(it.get("text"), str):
            raise ErrorDeTraduccion("bad_response")
        salida.append(Traducido(it["text"], normalizar(it.get("lang"))))
    return salida


class ProveedorIA(ProveedorDeTraduccion):
    nombre = "ai"

    def __init__(self, db: Session, org_id: Optional[str], user_id: Optional[str] = None,
                 max_tokens: Optional[int] = None):
        self.db, self.org_id, self.user_id, self.max_tokens = db, org_id, user_id, max_tokens

    def admite(self, destino: str) -> bool:
        return destino in IDIOMAS

    def traducir(self, textos, destino, origen, glosarios):
        from app.services import ai_provider_service as ia

        mensajes = [{"role": "user", "content": json.dumps({"items": textos}, ensure_ascii=False)}]
        try:
            respuesta = ia.call_ai(self.db, mensajes, system=instrucciones(destino, origen, glosarios),
                                   module=MODULO_DE_IA, user_id=self.user_id, organization_id=self.org_id,
                                   max_tokens=self.max_tokens)
        except ia.PresupuestoDeIAAgotado as exc:
            raise ErrorDeTraduccion("budget_exhausted") from exc
        if ia.es_aviso_de_ia(respuesta):
            sin = respuesta == ia.AVISO_SIN_PROVEEDOR
            raise ErrorDeTraduccion("provider_not_configured" if sin else "provider_error")
        return _leer(respuesta, len(textos))
