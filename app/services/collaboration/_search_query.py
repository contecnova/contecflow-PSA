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
from dataclasses import dataclass, field
from datetime import datetime
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


def parse(query: str) -> ParsedQuery:
    if not query:
        return ParsedQuery(raw=query or "")
    out = ParsedQuery(raw=query)
    rest = query
    for m in _OP_RE.finditer(query):
        op, val = m.group(1).lower(), m.group(2)
        rest = rest.replace(m.group(0), "")
        if op == "from":
            out.from_author = val.lstrip("@")
        elif op == "in":
            out.in_target = val
        elif op == "before":
            out.before = _parse_date(val)
        elif op == "after":
            out.after = _parse_date(val)
        elif op == "has":
            v = val.lower()
            if v in {"attachment", "attachments", "file", "files"}:
                out.has_attachment = True
            elif v in {"link", "links", "url"}:
                out.has_link = True
            elif v in {"mention", "mentions", "ping"}:
                out.has_mention = True
        elif op == "is":
            v = val.lower()
            if v == "pinned":
                out.is_pinned = True
            elif v in {"saved", "bookmark", "bookmarked"}:
                out.is_saved = True
        elif op == "type":
            out.type_filter = val.lower()
    out.text = re.sub(r"\s+", " ", rest).strip()
    return out


def _parse_date(s: str) -> Optional[datetime]:
    """Acepta YYYY-MM-DD o YYYY-MM-DDTHH:MM o relativa (today, yesterday, -7d)."""
    if not s:
        return None
    s = s.lower()
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
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
        return datetime.utcnow() - delta
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None
