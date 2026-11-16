"""Glosario de la empresa: terminos que no se traducen o que se traducen siempre igual.

Un termino sin traducciones (`translations` vacio) se deja tal cual en
cualquier idioma (nombres de producto, siglas). Con traducciones
(`{"en": "...", "zh": "..."}`), en esos idiomas sale siempre ese texto; en los
demas, el termino tal cual.

Como se aplica:

- `relevantes(terminos, texto, destino)`: solo los terminos que aparecen en el
  texto, con lo que debe salir en el destino. Es tambien la **huella** de la
  cache: cambiar un termino que no esta en el texto no invalida su traduccion.
- Proveedores con marcado (DeepL y Azure): `proteger` cambia cada aparicion
  por su texto final envuelto en una etiqueta que el proveedor no traduce, y
  `desproteger` la quita. El modelo de IA recibe la lista en las instrucciones.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.traduccion import TranslationGlossaryTerm
from app.services.traduccion.idiomas import normalizar

#: Largo maximo de un termino y de cada traduccion.
MAX_TERMINO = 200


@dataclass(frozen=True)
class Termino:
    termino: str
    traducciones: dict
    distingue_mayusculas: bool

    def salida(self, destino: str) -> str:
        return self.traducciones.get(destino) or self.termino

    def patron(self) -> re.Pattern:
        # Limites de palabra que valen tambien para terminos con signos (C++, .NET).
        cuerpo = re.escape(self.termino)
        flags = 0 if self.distingue_mayusculas else re.IGNORECASE
        return re.compile(rf"(?<![\w]){cuerpo}(?![\w])", flags | re.UNICODE)


def _traducciones(crudo: Optional[str]) -> dict:
    try:
        datos = json.loads(crudo) if crudo else {}
    except ValueError:
        return {}
    return {normalizar(k): str(v) for k, v in (datos or {}).items() if normalizar(k) and str(v or "").strip()}


def activos(db: Session, org_id: Optional[str]) -> list[Termino]:
    if not org_id:
        return []
    filas = db.query(TranslationGlossaryTerm).filter(
        TranslationGlossaryTerm.organization_id == org_id, TranslationGlossaryTerm.is_active.is_(True)).all()
    # Los largos primero: «Contecflow PSA» antes que «Contecflow».
    return sorted((Termino(f.term, _traducciones(f.translations), bool(f.case_sensitive)) for f in filas),
                  key=lambda t: len(t.termino), reverse=True)


def relevantes(terminos: list[Termino], texto: str, destino: str) -> list[tuple[Termino, str]]:
    return [(t, t.salida(destino)) for t in terminos if t.patron().search(texto or "")]


def huella(pares: list[tuple[Termino, str]]) -> str:
    """Lo que del glosario cambia esta traduccion (vacio si nada)."""
    if not pares:
        return ""
    crudo = json.dumps(sorted([t.termino, s, t.distingue_mayusculas] for t, s in pares), ensure_ascii=False)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:16]


def proteger(texto: str, pares: list[tuple[Termino, str]], apertura: str, cierre: str) -> str:
    """Escapa el texto (XML/HTML) y envuelve cada termino del glosario, ya con su salida."""
    if not pares:
        return html.escape(texto, quote=False)
    marcas: list[str] = []

    def _marca(salida: str) -> str:
        marcas.append(salida)
        return f"\x00{len(marcas) - 1}\x00"

    trabajo = texto
    for termino, salida in pares:
        trabajo = termino.patron().sub(lambda _m, s=salida: _marca(s), trabajo)
    escapado = html.escape(trabajo, quote=False)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"{apertura}{html.escape(marcas[int(m.group(1))], quote=False)}{cierre}",
                  escapado)


def desproteger(texto: str, apertura: str, cierre: str) -> str:
    return html.unescape(texto.replace(apertura, "").replace(cierre, ""))


# ── Administracion ───────────────────────────────────────────────────────────

def _limpiar_traducciones(datos: Optional[dict]) -> dict:
    limpias = {}
    for k, v in (datos or {}).items():
        codigo = normalizar(k)
        if not codigo:
            raise ErrorDeDominio(422, "trad_idioma_no_soportado")
        valor = (v or "").strip()
        if len(valor) > MAX_TERMINO:
            raise ErrorDeDominio(422, "trad_termino_largo")
        if valor:
            limpias[codigo] = valor
    return limpias


def serializar(f: TranslationGlossaryTerm) -> dict:
    return {"id": f.id, "term": f.term, "translations": _traducciones(f.translations),
            "case_sensitive": bool(f.case_sensitive), "notes": f.notes, "is_active": bool(f.is_active),
            "updated_at": (f.updated_at or f.created_at).isoformat() if (f.updated_at or f.created_at) else None}


def listar(db: Session, org_id: str) -> list[dict]:
    filas = db.query(TranslationGlossaryTerm).filter(TranslationGlossaryTerm.organization_id == org_id) \
        .order_by(TranslationGlossaryTerm.term).all()
    return [serializar(f) for f in filas]


def _de_la_empresa(db: Session, org_id: str, termino_id: str) -> TranslationGlossaryTerm:
    f = db.query(TranslationGlossaryTerm).filter(TranslationGlossaryTerm.id == termino_id,
                                                 TranslationGlossaryTerm.organization_id == org_id).first()
    if f is None:
        raise ErrorDeDominio(404, "trad_termino_no_encontrado")
    return f


def _exigir_unico(db: Session, org_id: str, termino: str, excepto: Optional[str] = None) -> None:
    q = db.query(TranslationGlossaryTerm.id).filter(TranslationGlossaryTerm.organization_id == org_id,
                                                    TranslationGlossaryTerm.term == termino)
    if excepto:
        q = q.filter(TranslationGlossaryTerm.id != excepto)
    if q.first():
        raise ErrorDeDominio(409, "trad_termino_duplicado")


def crear(db: Session, actor, datos: dict) -> dict:
    from app.services.audit import audit_log
    org_id = actor.organization_id
    if not org_id:
        raise ErrorDeDominio(422, "trad_sin_empresa")
    termino = (datos.get("term") or "").strip()
    if not termino or len(termino) > MAX_TERMINO:
        raise ErrorDeDominio(422, "trad_termino_invalido")
    _exigir_unico(db, org_id, termino)
    f = TranslationGlossaryTerm(
        organization_id=org_id, term=termino,
        translations=json.dumps(_limpiar_traducciones(datos.get("translations")), ensure_ascii=False),
        case_sensitive=bool(datos.get("case_sensitive")), notes=(datos.get("notes") or "").strip()[:500] or None,
        is_active=datos.get("is_active", True) is not False, created_by_user_id=actor.id)
    db.add(f)
    db.flush()
    audit_log(db, actor, "CREATE", "translation_glossary", f.id, termino, new_values=serializar(f))
    db.commit()
    return serializar(f)


def actualizar(db: Session, actor, termino_id: str, datos: dict) -> dict:
    from app.services.audit import audit_log
    f = _de_la_empresa(db, actor.organization_id, termino_id)
    antes = serializar(f)
    if "term" in datos and datos["term"] is not None:
        termino = datos["term"].strip()
        if not termino or len(termino) > MAX_TERMINO:
            raise ErrorDeDominio(422, "trad_termino_invalido")
        _exigir_unico(db, actor.organization_id, termino, excepto=f.id)
        f.term = termino
    if "translations" in datos and datos["translations"] is not None:
        f.translations = json.dumps(_limpiar_traducciones(datos["translations"]), ensure_ascii=False)
    if datos.get("case_sensitive") is not None:
        f.case_sensitive = bool(datos["case_sensitive"])
    if "notes" in datos:
        f.notes = (datos.get("notes") or "").strip()[:500] or None
    if datos.get("is_active") is not None:
        f.is_active = bool(datos["is_active"])
    db.flush()
    audit_log(db, actor, "UPDATE", "translation_glossary", f.id, f.term, old_values=antes, new_values=serializar(f))
    db.commit()
    return serializar(f)


def borrar(db: Session, actor, termino_id: str) -> None:
    from app.services.audit import audit_log
    f = _de_la_empresa(db, actor.organization_id, termino_id)
    audit_log(db, actor, "DELETE", "translation_glossary", f.id, f.term, old_values=serializar(f))
    db.delete(f)
    db.commit()
