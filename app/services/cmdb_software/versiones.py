"""Comparar versiones y comprobar si caen en un rango afectado.

Comparador tolerante para las versiones que se ven en la práctica: semver
(``1.2.3-rc.1+build``), PHP/nginx (``8.1.27``, ``1.24.0``), Maven
(``2.17.1``, ``5.3.18.RELEASE``), Go (``v1.2.3``), Python (``2.31.0``,
``1.0.0rc1``, ``1.0.post1``), Debian/Ubuntu (``1:1.18.0-6ubuntu14.4``: época,
versión y revisión) y fechas (``2024.01``).

Reglas: se quita el prefijo ``v``; la época (``1:``) manda; se trocea en
segmentos numéricos y de texto; los números se comparan como números; un
marcador de pre-versión (dev, alpha, a, beta, b, pre, preview, rc, cr, m,
milestone, snapshot) va ANTES que la versión final, y post/patch/sp/release/
final/ga DESPUÉS o igual. «1.0» == «1.0.0».
"""
from __future__ import annotations

import re
from functools import total_ordering
from typing import Iterable, Optional

_PRE = {"dev": -6, "snapshot": -6, "alpha": -5, "a": -5, "beta": -4, "b": -4, "milestone": -3, "m": -3,
        "pre": -2, "preview": -2, "rc": -1, "cr": -1, "c": -1}
_FINAL = {"final": 0, "ga": 0, "release": 0, "r": 0}
_POST = {"post": 1, "p": 1, "pl": 1, "patch": 1, "sp": 1, "u": 1, "update": 1}

_TOKEN = re.compile(r"\d+|[a-z]+")


def _trocear(texto: str) -> list:
    """[(clase, valor, texto)]: clase 2 = número, 1 = post, 0 = pre o texto desconocido."""
    salida = []
    for t in _TOKEN.findall(texto.lower()):
        if t.isdigit():
            salida.append((2, int(t), ""))
        elif t in _PRE:
            salida.append((0, _PRE[t], ""))
        elif t in _FINAL:
            continue
        elif t in _POST:
            salida.append((1, _POST[t], ""))
        else:
            salida.append((0, -7, t))   # texto desconocido: como pre-versión, ordenado por texto
    return salida


@total_ordering
class Version:
    __slots__ = ("texto", "epoca", "partes", "revision")

    def __init__(self, texto: Optional[str]):
        t = (texto or "").strip()
        self.texto = t
        t = t.split("+", 1)[0]                      # metadatos de compilación: no cuentan
        if t[:1] in ("v", "V") and t[1:2].isdigit():
            t = t[1:]
        self.epoca = 0
        m = re.match(r"^(\d+):(.+)$", t)
        if m:
            self.epoca, t = int(m.group(1)), m.group(2)
        self.revision: list = []
        # Revisión de Debian/RPM (tras el último guion, si empieza por dígito o lleva «ubuntu»/«deb»/«el»)
        m = re.match(r"^(.*\d)-(\d[\w.~+]*|[\w.~+]*(?:ubuntu|deb|el|fc|alpine|r)\d[\w.~+]*)$", t)
        if m and not re.search(r"(?i)(alpha|beta|rc|snapshot|dev|pre)", m.group(2)):
            t, self.revision = m.group(1), _trocear(m.group(2))
        self.partes = _trocear(t.replace("~", "-pre"))

    def _clave(self):
        return (self.epoca, self.partes, self.revision)

    @staticmethod
    def _cmp_partes(a: list, b: list) -> int:
        """Segmento a segmento. Cuando una se acaba, lo que sigue en la otra
        decide: un 0 no cuenta («1.0» == «1.0.0»), un número o un post la hace
        mayor y una pre-versión, menor («1.0.0» > «1.0.0-rc1»)."""
        for i in range(max(len(a), len(b))):
            if i < len(a) and i < len(b):
                if a[i] != b[i]:
                    return -1 if a[i] < b[i] else 1
                continue
            tok, signo = (b[i], -1) if i >= len(a) else (a[i], 1)
            if tok[0] == 2 and tok[1] == 0:
                continue
            return signo if tok[0] >= 1 else -signo
        return 0

    def comparar(self, otra: "Version") -> int:
        if self.epoca != otra.epoca:
            return -1 if self.epoca < otra.epoca else 1
        c = self._cmp_partes(self.partes, otra.partes)
        if c:
            return c
        return self._cmp_partes(self.revision, otra.revision)

    def __eq__(self, otra):
        return isinstance(otra, Version) and self.comparar(otra) == 0

    def __lt__(self, otra):
        return self.comparar(otra) < 0

    def __hash__(self):
        return hash(str(self._clave()))

    def __repr__(self):
        return f"Version({self.texto!r})"


def comparar(a: Optional[str], b: Optional[str]) -> int:
    """-1, 0 o 1."""
    return Version(a).comparar(Version(b))


def valida(texto: Optional[str]) -> bool:
    """¿Tiene al menos un número? (sin versión no se correlaciona)."""
    return bool(texto) and bool(re.search(r"\d", str(texto))) and str(texto).strip() not in ("*", "-")


def en_rama(version: Optional[str], rama: Optional[str]) -> bool:
    """¿`version` pertenece a la rama `rama` («8.1.27» en «8.1»)?"""
    if not version or not rama:
        return False
    v, r = Version(version), Version(rama)
    if not r.partes:
        return False
    return v.epoca == r.epoca and v.partes[:len(r.partes)] == r.partes


def en_rango(version: Optional[str], introduced: Optional[str] = None, fixed: Optional[str] = None,
             last_affected: Optional[str] = None, introduced_inclusive: bool = True,
             exactas: Optional[Iterable[str]] = None) -> bool:
    """¿La versión está afectada?

    - `exactas`: lista de versiones afectadas; si la versión está, sí.
    - `introduced` (incluido salvo `introduced_inclusive=False`; «0» = desde el
      principio), `fixed` (excluido) y `last_affected` (incluido).
    - Sin ningún límite ni exactas: no (no se afirma lo que no se sabe).
    """
    if not valida(version):
        return False
    v = Version(version)
    if exactas:
        if any(Version(e) == v for e in exactas if e):
            return True
        if not (introduced or fixed or last_affected):
            return False
    if not (introduced or fixed or last_affected):
        return False
    if introduced and introduced not in ("0", "*"):
        c = v.comparar(Version(introduced))
        if c < 0 or (c == 0 and not introduced_inclusive):
            return False
    if fixed and v.comparar(Version(fixed)) >= 0:
        return False
    if last_affected and v.comparar(Version(last_affected)) > 0:
        return False
    return True


_OP = re.compile(r"^\s*(>=|<=|==|=|>|<|!=|~>|\^|~)?\s*v?([^\s,]+)\s*$")


def rango_de_texto(texto: Optional[str]) -> list[dict]:
    """Rango de GitHub/npm/composer a límites: ``">= 1.0, < 1.2.5"`` →
    ``[{introduced: '1.0', fixed: '1.2.5'}]``. Admite ``||`` (varios rangos) y
    ``= 1.2.3`` (exacta). Lo que no entiende lo devuelve vacío."""
    salida = []
    for trozo in (texto or "").split("||"):
        r: dict = {}
        for parte in re.split(r",|\s+(?=[<>=!])", trozo.strip()):
            if not parte.strip():
                continue
            m = _OP.match(parte)
            if not m:
                return []
            op, ver = m.group(1) or "=", m.group(2)
            if op == ">=":
                r["introduced"], r["introduced_inclusive"] = ver, True
            elif op == ">":
                r["introduced"], r["introduced_inclusive"] = ver, False
            elif op == "<":
                r["fixed"] = ver
            elif op == "<=":
                r["last_affected"] = ver
            elif op in ("=", "=="):
                r.setdefault("versions", []).append(ver)
            elif op in ("^", "~", "~>"):
                partes = ver.split(".")
                r["introduced"], r["introduced_inclusive"] = ver, True
                if op == "^" and partes and partes[0] != "0":
                    r["fixed"] = f"{int(partes[0]) + 1}" if partes[0].isdigit() else None
                elif len(partes) >= 2 and partes[1].isdigit():
                    r["fixed"] = f"{partes[0]}.{int(partes[1]) + 1}"
            else:
                return []
        if r:
            salida.append(r)
    return salida


def cumple(version: Optional[str], op: str, objetivo: Optional[str]) -> bool:
    """Filtro de búsqueda: ``op`` en lt, le, eq, ge, gt, ne, prefix (rama)."""
    if not objetivo:
        return True
    if not valida(version):
        return False
    if op == "prefix":
        return en_rama(version, objetivo)
    c = comparar(version, objetivo)
    return {"lt": c < 0, "le": c <= 0, "eq": c == 0, "ge": c >= 0, "gt": c > 0, "ne": c != 0}.get(op, c == 0)
