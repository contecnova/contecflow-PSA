"""Parser de operadores de búsqueda al estilo Slack/Teams.

Soporta:
  from:<user_id|email|@handle>     filtra por autor
  in:<channel_slug|conversation_id> filtra conversación
  before:<YYYY-MM-DD>              fecha máxima
  after:<YYYY-MM-DD>               fecha mínima
  has:attachment                   sólo mensajes con adjuntos
  has:link                         sólo mensajes con enlaces
  has:mention                      sólo mensajes con menciones
  is:pinned                        sólo mensajes anclados
  is:saved                         sólo mensajes guardados (per-user)
  type:<text|file|call|bot|poll>   filtra por tipo

El resto del texto es el query libre.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from app.core.timeutil import utcnow
from typing import Optional


_OP_RE = re.compile(r"\b(from|in|before|after|has|is|type):([^\s]+)", re.IGNORECASE)


@dataclass
class ParsedQuery:
    text: str = ""
    from_author: Optional[str] = None
    in_target: Optional[str] = None
    before: Optional[datetime] = None
    after: Optional[datetime] = None
    has_attachment: bool = False
    has_link: bool = False
    has_mention: bool = False
    is_pinned: bool = False
    is_saved: bool = False
    type_filter: Optional[str] = None
    raw: str = ""

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "from": self.from_author,
            "in": self.in_target,
            "before": self.before.isoformat() if self.before else None,
            "after": self.after.isoformat() if self.after else None,
            "has_attachment": self.has_attachment,
            "has_link": self.has_link,
            "has_mention": self.has_mention,
            "is_pinned": self.is_pinned,
            "is_saved": self.is_saved,
            "type": self.type_filter,
        }


# ── El repertorio de operadores ──────────────────────────────────────────────
#
# Auditoría 2026-08 (hallazgo 18). Esto estaba escrito como una cascada de
# `if op == ... elif op == ...` dentro de `parse`, con dos cascadas anidadas más
# para los sinónimos de `has:` y de `is:`. Complejidad 15 para lo que es, en
# realidad, una tabla: un operador, dónde se guarda, y cómo se convierte el
# valor. Escrita como tabla, añadir un operador es una línea y no una rama, y
# los sinónimos dejan de ser conjuntos literales enterrados en el código.
#
# La cabecera del módulo documenta los operadores para quien los escribe; estas
# dos tablas son la misma lista para quien los lee, y ahora es una sola.

# Operadores con valor: campo del resultado y conversión del texto.
_OPERADORES_CON_VALOR = {
    "from":   ("from_author", lambda v: v.lstrip("@")),
    "in":     ("in_target",   lambda v: v),
    "before": ("before",      lambda v: _parse_date(v)),
    "after":  ("after",       lambda v: _parse_date(v)),
    "type":   ("type_filter", lambda v: v.lower()),
}

# Operadores que encienden una bandera: cada sinónimo apunta a su campo.
# `file`/`files` son sinónimos de `attachment` porque en la interfaz el usuario
# habla de ficheros, no de adjuntos.
_BANDERAS_POR_OPERADOR = {
    "has": {
        "attachment": "has_attachment", "attachments": "has_attachment",
        "file": "has_attachment", "files": "has_attachment",
        "link": "has_link", "links": "has_link", "url": "has_link",
        "mention": "has_mention", "mentions": "has_mention",
        "ping": "has_mention",
    },
    "is": {
        "pinned": "is_pinned",
        "saved": "is_saved", "bookmark": "is_saved", "bookmarked": "is_saved",
    },
}


def parse(query: str) -> ParsedQuery:
    if not query:
        return ParsedQuery(raw=query or "")
    out = ParsedQuery(raw=query)
    rest = query
    for m in _OP_RE.finditer(query):
        op, val = m.group(1).lower(), m.group(2)
        rest = rest.replace(m.group(0), "")
        if op in _OPERADORES_CON_VALOR:
            campo, convertir = _OPERADORES_CON_VALOR[op]
            setattr(out, campo, convertir(val))
        elif op in _BANDERAS_POR_OPERADOR:
            # Un sinónimo desconocido —`has:loquesea`— se ignora en silencio, y
            # así estaba antes: el operador ya se ha quitado del texto libre, de
            # modo que buscar `has:loquesea hola` busca «hola». Convertirlo en
            # error cambiaría el contrato de una caja de búsqueda.
            campo = _BANDERAS_POR_OPERADOR[op].get(val.lower())
            if campo:
                setattr(out, campo, True)
    out.text = re.sub(r"\s+", " ", rest).strip()
    return out


def _parse_date(s: str) -> Optional[datetime]:
    """Acepta YYYY-MM-DD o YYYY-MM-DDTHH:MM o relativa (today, yesterday, -7d)."""
    if not s:
        return None
    s = s.lower()
    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    if s == "today":
        return today
    if s == "yesterday":
        from datetime import timedelta
        return today - timedelta(days=1)
    m = re.match(r"^-(\d+)([dhwm])$", s)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        from datetime import timedelta
        delta = {
            "d": timedelta(days=n),
            "h": timedelta(hours=n),
            "w": timedelta(weeks=n),
            "m": timedelta(days=30 * n),
        }[unit]
        return utcnow() - delta
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None
