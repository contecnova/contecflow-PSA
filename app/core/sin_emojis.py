"""Quita emojis de los textos que genera el sistema (títulos de avisos).

16-11-2026 (campana de notificaciones): los avisos llegaban con el emoji en el
título («🎉 Contecflow v11 Enterprise activo»). La interfaz no pinta emojis —el
icono lo pone cada pantalla, con lucide y según el tipo— y un emoji en el texto
sale con la fuente del sistema operativo, sin seguir el tema. Se quitan en
origen: los modelos de aviso validan el título con `sin_emojis`.
"""
from __future__ import annotations

import re
from typing import Optional

_RE_EMOJI = re.compile(
    "["
    "\U0001F000-\U0001FAFF"   # pictogramas, caras, transporte, banderas, símbolos suplementarios
    "☀-➿"           # símbolos varios y dingbats (✓ ✅ ✗ ⚠ ⚡ …)
    "⬀-⯿"           # flechas y símbolos (⬆ ⭐ …)
    "⌚⌛⏩-⏺"  # relojes (⌚ ⏰ ⏳ …)
    "️‍⃣"      # selector de variante, unión de anchura cero, tecla
    "]+"
)


def sin_emojis(texto: Optional[str]) -> Optional[str]:
    """`texto` sin emojis y sin los espacios que dejan; `None` sigue siendo `None`."""
    if not texto:
        return texto
    return re.sub(r"\s{2,}", " ", _RE_EMOJI.sub("", texto)).strip()
