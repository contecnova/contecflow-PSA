"""Contenido de una página: el JSON del editor (ProseMirror/TipTap) y lo que se saca de él.

El servidor nunca guarda HTML del navegador: guarda el JSON, lo valida (tipos
de nodo y marca conocidos, profundidad, tamaño, enlaces http/https/mailto o
rutas propias, imágenes solo de adjuntos del cuaderno) y de él saca:

- el texto plano (búsqueda en el cuaderno y en la búsqueda global);
- las casillas de tarea (`taskItem`: hecha, fecha, aviso) y las etiquetas
  (`noteTag`, con el texto del párrafo que etiquetan) → `notebook_items`;
- los enlaces vivos (`objectRef` con `#`, `mention` con `@`) → `notebook_links`;
- el Markdown y el PDF de las exportaciones.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

from app.core.codigos_de_error import error

NODOS = {
    "doc", "paragraph", "text", "heading", "bulletList", "orderedList", "listItem", "blockquote", "codeBlock",
    "horizontalRule", "hardBreak", "taskList", "taskItem", "table", "tableRow", "tableHeader", "tableCell",
    "image", "mention", "objectRef", "noteTag",
}
MARCAS = {"bold", "italic", "strike", "code", "underline", "link", "highlight"}
TIPOS_DE_OBJETO = ("task", "ticket", "project", "client", "demand", "proposal", "event", "user")
PROFUNDIDAD_MAXIMA = 40
_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_UUID = re.compile(r"^[A-Za-z0-9-]{1,36}$")
_HREF = re.compile(r"^(https?://|mailto:|/)", re.I)
_SRC = re.compile(r"^/api/v1/notebook/attachments/[A-Za-z0-9-]{1,36}/file$")
_COLOR = re.compile(r"^(yellow|green|blue|pink|purple|orange|red)$")

DOC_VACIO = {"type": "doc", "content": [{"type": "paragraph"}]}


def _max_bytes() -> int:
    from app.core.config import settings
    return int(getattr(settings, "CUADERNO_PAGE_MAX_BYTES", 2 * 1024 * 1024) or 2 * 1024 * 1024)


def _fecha(valor) -> Optional[date]:
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _instante(valor) -> Optional[datetime]:
    if not valor:
        return None
    try:
        v = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _limpiar_marcas(marcas) -> list:
    salida = []
    for m in marcas or []:
        if not isinstance(m, dict) or m.get("type") not in MARCAS:
            continue
        attrs = m.get("attrs") if isinstance(m.get("attrs"), dict) else {}
        if m["type"] == "link":
            href = str(attrs.get("href") or "")
            if not _HREF.match(href) or len(href) > 2000:
                continue
            salida.append({"type": "link", "attrs": {"href": href, "target": "_blank",
                                                    "rel": "noopener noreferrer nofollow"}})
        elif m["type"] == "highlight":
            color = attrs.get("color")
            salida.append({"type": "highlight", "attrs": {"color": color}} if color and _COLOR.match(str(color))
                          else {"type": "highlight"})
        else:
            salida.append({"type": m["type"]})
    return salida


def _attrs(tipo: str, attrs: dict) -> Optional[dict]:
    """Atributos permitidos de cada nodo (lo demás se descarta)."""
    a = attrs if isinstance(attrs, dict) else {}
    if tipo == "heading":
        nivel = a.get("level")
        return {"level": nivel if nivel in (1, 2, 3, 4) else 2}
    if tipo == "orderedList":
        inicio = a.get("start")
        return {"start": inicio if isinstance(inicio, int) and 0 < inicio < 100000 else 1}
    if tipo == "codeBlock":
        lengua = a.get("language")
        return {"language": str(lengua)[:30] if lengua else None}
    if tipo == "taskItem":
        return {"checked": bool(a.get("checked")),
                "bid": a.get("bid") if isinstance(a.get("bid"), str) and _ID.match(a["bid"]) else None,
                "due": str(_fecha(a.get("due"))) if _fecha(a.get("due")) else None,
                "remind": _instante(a.get("remind")).isoformat() if _instante(a.get("remind")) else None}
    if tipo in ("tableCell", "tableHeader"):
        cs, rs = a.get("colspan"), a.get("rowspan")
        return {"colspan": cs if isinstance(cs, int) and 0 < cs < 50 else 1,
                "rowspan": rs if isinstance(rs, int) and 0 < rs < 500 else 1, "colwidth": None}
    if tipo == "image":
        src = str(a.get("src") or "")
        if not _SRC.match(src):
            return None
        return {"src": src, "alt": str(a.get("alt") or "")[:300] or None, "title": None}
    if tipo == "mention":
        if not (isinstance(a.get("id"), str) and _UUID.match(a["id"])):
            return None
        return {"id": a["id"], "label": str(a.get("label") or "")[:200]}
    if tipo == "objectRef":
        if a.get("type") not in TIPOS_DE_OBJETO or not (isinstance(a.get("id"), str) and _UUID.match(a["id"])):
            return None
        return {"type": a["type"], "id": a["id"], "label": str(a.get("label") or "")[:200]}
    if tipo == "noteTag":
        clave = str(a.get("key") or "")
        if not re.match(r"^[a-z][a-z0-9_]{0,39}$", clave):
            return None
        return {"key": clave}
    return None


def _limpiar(nodo: Any, profundidad: int) -> Optional[dict]:
    if profundidad > PROFUNDIDAD_MAXIMA:
        raise error(422, "cuaderno_contenido_no_valido", motivo="profundidad")
    if not isinstance(nodo, dict) or nodo.get("type") not in NODOS:
        return None
    tipo = nodo["type"]
    if tipo == "text":
        texto = nodo.get("text")
        if not isinstance(texto, str) or not texto:
            return None
        salida = {"type": "text", "text": texto}
        marcas = _limpiar_marcas(nodo.get("marks"))
        if marcas:
            salida["marks"] = marcas
        return salida
    salida: dict = {"type": tipo}
    attrs = _attrs(tipo, nodo.get("attrs") or {})
    if tipo in ("image", "mention", "objectRef", "noteTag") and attrs is None:
        return None
    if attrs is not None:
        salida["attrs"] = attrs
    hijos = [h for h in (_limpiar(x, profundidad + 1) for x in (nodo.get("content") or [])
                         if isinstance(nodo.get("content"), list)) if h is not None]
    if hijos:
        salida["content"] = hijos
    return salida


def validar(contenido: Any) -> dict:
    """El documento limpio (o 422). Acepta el JSON como dict o como texto."""
    if contenido is None or contenido == "":
        return json.loads(json.dumps(DOC_VACIO))
    if isinstance(contenido, str):
        if len(contenido.encode("utf-8")) > _max_bytes():
            raise error(413, "cuaderno_pagina_demasiado_grande", max=_max_bytes() // 1024)
        try:
            contenido = json.loads(contenido)
        except ValueError:
            raise error(422, "cuaderno_contenido_no_valido", motivo="json")
    if not isinstance(contenido, dict) or contenido.get("type") != "doc":
        raise error(422, "cuaderno_contenido_no_valido", motivo="doc")
    limpio = _limpiar(contenido, 0) or json.loads(json.dumps(DOC_VACIO))
    if len(json.dumps(limpio, ensure_ascii=False).encode("utf-8")) > _max_bytes():
        raise error(413, "cuaderno_pagina_demasiado_grande", max=_max_bytes() // 1024)
    return limpio


def cargar(texto: Optional[str]) -> dict:
    if not texto:
        return json.loads(json.dumps(DOC_VACIO))
    try:
        v = json.loads(texto)
    except ValueError:
        return json.loads(json.dumps(DOC_VACIO))
    return v if isinstance(v, dict) else json.loads(json.dumps(DOC_VACIO))


# ── Texto, casillas, etiquetas y enlaces ─────────────────────────────────────

_BLOQUES = {"paragraph", "heading", "codeBlock", "blockquote", "listItem", "taskItem", "tableRow", "doc",
            "bulletList", "orderedList", "taskList", "table"}


def texto_en_linea(nodo: dict) -> str:
    """El texto de un nodo en una línea (los chips por su etiqueta)."""
    tipo = nodo.get("type")
    if tipo == "text":
        return nodo.get("text") or ""
    if tipo == "mention":
        return "@" + ((nodo.get("attrs") or {}).get("label") or "")
    if tipo == "objectRef":
        return "#" + ((nodo.get("attrs") or {}).get("label") or "")
    if tipo == "hardBreak":
        return " "
    return "".join(texto_en_linea(h) for h in nodo.get("content") or [] if h.get("type") not in
                   ("bulletList", "orderedList", "taskList"))


def texto_plano(doc: dict) -> str:
    """Texto de la página, un bloque por línea (para buscar)."""
    lineas: list[str] = []

    def ir(n: dict):
        tipo = n.get("type")
        if tipo in ("paragraph", "heading", "codeBlock"):
            t = texto_en_linea(n).strip()
            if t:
                lineas.append(t)
            return
        for h in n.get("content") or []:
            ir(h)

    ir(doc)
    return "\n".join(lineas)


def elementos(doc: dict) -> list[dict]:
    """Casillas y etiquetas de la página, en orden.

    `{"kind": "todo", "text", "checked", "due_date", "remind_at", "block_id"}` y
    `{"kind": "tag", "tag_key", "text"}` (el texto del párrafo etiquetado).
    """
    salida: list[dict] = []

    def ir(n: dict, bloque_texto: Optional[str]):
        tipo = n.get("type")
        if tipo == "taskItem":
            a = n.get("attrs") or {}
            propio = " ".join(texto_en_linea(h) for h in n.get("content") or []
                              if h.get("type") in ("paragraph", "heading")).strip()
            salida.append({"kind": "todo", "text": propio[:1000], "checked": bool(a.get("checked")),
                           "due_date": _fecha(a.get("due")), "remind_at": _instante(a.get("remind")),
                           "block_id": a.get("bid")})
        if tipo in ("paragraph", "heading"):
            bloque_texto = texto_en_linea(n).strip()
        if tipo == "noteTag":
            salida.append({"kind": "tag", "tag_key": (n.get("attrs") or {}).get("key"),
                           "text": (bloque_texto or "")[:1000]})
            return
        for h in n.get("content") or []:
            ir(h, bloque_texto)

    ir(doc, None)
    return salida


def enlaces(doc: dict) -> set[tuple[str, str]]:
    """{(tipo, id)} de los chips de la página (`#` objetos y `@` personas)."""
    salida: set = set()

    def ir(n: dict):
        tipo = n.get("type")
        a = n.get("attrs") or {}
        if tipo == "mention" and a.get("id"):
            salida.add(("user", a["id"]))
        elif tipo == "objectRef" and a.get("id") and a.get("type"):
            salida.add((a["type"], a["id"]))
        for h in n.get("content") or []:
            ir(h)

    ir(doc)
    return salida


def imagenes(doc: dict) -> set[str]:
    """Ids de adjunto de las imágenes de la página."""
    salida: set = set()

    def ir(n: dict):
        if n.get("type") == "image":
            src = (n.get("attrs") or {}).get("src") or ""
            salida.add(src.rstrip("/").split("/")[-2] if src.count("/") >= 2 else src)
        for h in n.get("content") or []:
            ir(h)

    ir(doc)
    return salida


# ── Markdown ─────────────────────────────────────────────────────────────────

def _md_en_linea(nodos: Iterable[dict]) -> str:
    partes = []
    for n in nodos or []:
        tipo = n.get("type")
        if tipo == "text":
            t = n.get("text") or ""
            marcas = {m.get("type"): m for m in n.get("marks") or []}
            if "code" in marcas:
                t = f"`{t}`"
            if "bold" in marcas:
                t = f"**{t}**"
            if "italic" in marcas:
                t = f"*{t}*"
            if "strike" in marcas:
                t = f"~~{t}~~"
            if "highlight" in marcas:
                t = f"=={t}=="
            if "link" in marcas:
                t = f"[{t}]({(marcas['link'].get('attrs') or {}).get('href', '')})"
            partes.append(t)
        elif tipo == "hardBreak":
            partes.append("  \n")
        elif tipo in ("mention", "objectRef", "noteTag"):
            a = n.get("attrs") or {}
            if tipo == "noteTag":
                partes.append(f"[{a.get('key')}] ")
            else:
                partes.append(("@" if tipo == "mention" else "#") + (a.get("label") or a.get("id") or ""))
        elif tipo == "image":
            partes.append(f"![{(n.get('attrs') or {}).get('alt') or 'imagen'}]")
    return "".join(partes)


def a_markdown(doc: dict, etiquetas: Optional[dict] = None) -> str:
    """Markdown de la página (`etiquetas`: {clave: nombre} para pintar las etiquetas)."""
    etiquetas = etiquetas or {}
    lineas: list[str] = []

    def lista(n: dict, nivel: int, ordenada: bool, tareas: bool):
        for i, item in enumerate(n.get("content") or [], start=1):
            sangria = "  " * nivel
            a = item.get("attrs") or {}
            vineta = f"{i}." if ordenada else "-"
            if tareas:
                vineta = "- [x]" if a.get("checked") else "- [ ]"
            primero = True
            for h in item.get("content") or []:
                if h.get("type") in ("bulletList", "orderedList", "taskList"):
                    lista(h, nivel + 1, h["type"] == "orderedList", h["type"] == "taskList")
                else:
                    texto = _md_en_linea(h.get("content"))
                    for clave, nombre in etiquetas.items():
                        texto = texto.replace(f"[{clave}] ", f"[{nombre}] ")
                    extra = ""
                    if tareas and primero and a.get("due"):
                        extra = f" ({a['due']})"
                    lineas.append(f"{sangria}{vineta if primero else ' ' * len(vineta)} {texto}{extra}")
                    primero = False

    def bloque(n: dict):
        tipo = n.get("type")
        if tipo == "heading":
            lineas.append("#" * int((n.get("attrs") or {}).get("level") or 2) + " " + _md_en_linea(n.get("content")))
            lineas.append("")
        elif tipo == "paragraph":
            texto = _md_en_linea(n.get("content"))
            for clave, nombre in etiquetas.items():
                texto = texto.replace(f"[{clave}] ", f"[{nombre}] ")
            lineas.append(texto)
            lineas.append("")
        elif tipo in ("bulletList", "orderedList", "taskList"):
            lista(n, 0, tipo == "orderedList", tipo == "taskList")
            lineas.append("")
        elif tipo == "blockquote":
            inicio = len(lineas)
            for h in n.get("content") or []:
                bloque(h)
            for i in range(inicio, len(lineas)):
                lineas[i] = "> " + lineas[i] if lineas[i] else ">"
        elif tipo == "codeBlock":
            lineas.append("```" + ((n.get("attrs") or {}).get("language") or ""))
            lineas.append(texto_en_linea(n))
            lineas.append("```")
            lineas.append("")
        elif tipo == "horizontalRule":
            lineas.append("---")
            lineas.append("")
        elif tipo == "table":
            filas = n.get("content") or []
            for i, fila in enumerate(filas):
                celdas = [texto_en_linea(c).replace("|", "\\|").strip() for c in fila.get("content") or []]
                lineas.append("| " + " | ".join(celdas) + " |")
                if i == 0:
                    lineas.append("|" + "---|" * max(1, len(celdas)))
            lineas.append("")
        elif tipo == "image":
            lineas.append(_md_en_linea([n]))
            lineas.append("")
        else:
            for h in n.get("content") or []:
                bloque(h)

    for h in doc.get("content") or []:
        bloque(h)
    while lineas and not lineas[-1]:
        lineas.pop()
    return "\n".join(lineas) + "\n"


# ── PDF ──────────────────────────────────────────────────────────────────────

def a_pdf(paginas: list[tuple[str, dict]], titulo: str, idioma: Optional[str] = None,
          etiquetas: Optional[dict] = None) -> bytes:
    """PDF de una o varias páginas: [(título, doc)]. Fuentes del idioma (DejaVu / STSong para chino)."""
    import io
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from app.services.invoice_pdf import _esc, _fuentes

    etiquetas = etiquetas or {}
    fn, fb = _fuentes(idioma)
    hoja = getSampleStyleSheet()
    normal = ParagraphStyle("cn", parent=hoja["Normal"], fontName=fn, fontSize=10, leading=14)
    tit = {nivel: ParagraphStyle(f"ch{nivel}", parent=hoja["Normal"], fontName=fb, fontSize=size, leading=size + 4,
                                 spaceBefore=6, spaceAfter=4)
           for nivel, size in ((0, 18), (1, 15), (2, 13), (3, 11.5), (4, 10.5))}
    cita = ParagraphStyle("cq", parent=normal, leftIndent=10 * mm, textColor=colors.grey)
    codigo = ParagraphStyle("cc", parent=normal, fontName="Courier", fontSize=8.5, leading=11)

    def en_linea(nodos) -> str:
        partes = []
        for n in nodos or []:
            tipo = n.get("type")
            if tipo == "text":
                t = _esc(n.get("text") or "")
                marcas = {m.get("type") for m in n.get("marks") or []}
                if "bold" in marcas:
                    t = f"<b>{t}</b>"
                if "italic" in marcas:
                    t = f"<i>{t}</i>"
                if "underline" in marcas:
                    t = f"<u>{t}</u>"
                if "strike" in marcas:
                    t = f"<strike>{t}</strike>"
                if "highlight" in marcas:
                    t = f'<font backColor="#fff3a3">{t}</font>'
                partes.append(t)
            elif tipo == "hardBreak":
                partes.append("<br/>")
            elif tipo == "mention":
                partes.append(_esc("@" + ((n.get("attrs") or {}).get("label") or "")))
            elif tipo == "objectRef":
                partes.append(_esc("#" + ((n.get("attrs") or {}).get("label") or "")))
            elif tipo == "noteTag":
                clave = (n.get("attrs") or {}).get("key") or ""
                partes.append(f"<b>[{_esc(etiquetas.get(clave, clave))}]</b> ")
            elif tipo == "image":
                partes.append(_esc(f"[{(n.get('attrs') or {}).get('alt') or 'imagen'}]"))
        return "".join(partes)

    historia: list = []

    def lista(n, nivel: int, ordenada: bool, tareas: bool):
        for i, item in enumerate(n.get("content") or [], start=1):
            a = item.get("attrs") or {}
            marca = f"{i}." if ordenada else "•"
            if tareas:
                marca = "[x]" if a.get("checked") else "[ ]"
            estilo = ParagraphStyle(f"cl{nivel}", parent=normal, leftIndent=(6 + nivel * 6) * mm,
                                    bulletIndent=(2 + nivel * 6) * mm)
            for j, h in enumerate(item.get("content") or []):
                if h.get("type") in ("bulletList", "orderedList", "taskList"):
                    lista(h, nivel + 1, h["type"] == "orderedList", h["type"] == "taskList")
                else:
                    extra = f" ({_esc(a['due'])})" if tareas and j == 0 and a.get("due") else ""
                    historia.append(Paragraph(en_linea(h.get("content")) + extra, estilo,
                                              bulletText=marca if j == 0 else None))

    def bloque(n):
        tipo = n.get("type")
        if tipo == "heading":
            historia.append(Paragraph(en_linea(n.get("content")), tit[int((n.get("attrs") or {}).get("level") or 2)]))
        elif tipo == "paragraph":
            historia.append(Paragraph(en_linea(n.get("content")) or "&nbsp;", normal))
        elif tipo in ("bulletList", "orderedList", "taskList"):
            lista(n, 0, tipo == "orderedList", tipo == "taskList")
        elif tipo == "blockquote":
            for h in n.get("content") or []:
                historia.append(Paragraph(en_linea(h.get("content")), cita))
        elif tipo == "codeBlock":
            historia.append(Paragraph(_esc(texto_en_linea(n)), codigo))
        elif tipo == "horizontalRule":
            historia.append(Spacer(1, 4 * mm))
        elif tipo == "table":
            datos = [[Paragraph(_esc(texto_en_linea(c)), normal) for c in fila.get("content") or []]
                     for fila in n.get("content") or []]
            if datos:
                ancho = max(len(f) for f in datos)
                datos = [f + [""] * (ancho - len(f)) for f in datos]
                t = Table(datos, repeatRows=1)
                t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                                       ("FONTNAME", (0, 0), (-1, -1), fn),
                                       ("VALIGN", (0, 0), (-1, -1), "TOP")]))
                historia.append(t)
        elif tipo == "image":
            historia.append(Paragraph(en_linea([n]), normal))
        else:
            for h in n.get("content") or []:
                bloque(h)

    for i, (titulo_pagina, doc) in enumerate(paginas):
        if i:
            historia.append(PageBreak())
        historia.append(Paragraph(_esc(titulo_pagina or "—"), tit[0]))
        for h in doc.get("content") or []:
            bloque(h)
    salida = io.BytesIO()
    SimpleDocTemplate(salida, pagesize=A4, title=titulo, leftMargin=18 * mm, rightMargin=18 * mm,
                      topMargin=16 * mm, bottomMargin=16 * mm).build(historia or [Spacer(1, 1)])
    return salida.getvalue()
