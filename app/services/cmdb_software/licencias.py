"""Licencias de los componentes: clasificación SPDX y compatibilidad.

Familias:

- ``permissive``: MIT, BSD, Apache, ISC, Zlib, Unlicense, 0BSD, PSF, BSL-1.0…
- ``weak_copyleft``: LGPL, MPL, EPL, CDDL, EUPL (a nivel de fichero o de librería)
- ``strong_copyleft``: GPL
- ``network_copyleft``: AGPL, SSPL, OSL (obliga también al usarlo por red)
- ``proprietary``: propietaria / comercial
- ``unknown``: vacía, NOASSERTION o desconocida

Conflictos con el software que lo lleva (según cómo se entrega,
`SoftwareProduct.distribution`, y su origen):

- copyleft de red en software ofrecido como servicio (``saas``) o distribuido;
- copyleft fuerte en software distribuido, comprado o con licencia propietaria;
- licencia prohibida por la empresa (``licenses_denied``) o fuera de la lista
  permitida (``licenses_allowed``, si la hay);
- licencia desconocida (aviso, no conflicto).

Expresiones SPDX: ``A OR B`` vale si vale cualquiera (se toma la más
permisiva); ``A AND B`` exige las dos (se toma la más restrictiva).
"""
from __future__ import annotations

import re
from typing import Optional

FAMILIAS = ("permissive", "weak_copyleft", "strong_copyleft", "network_copyleft", "proprietary", "unknown")
_RANGO = {"permissive": 0, "weak_copyleft": 1, "unknown": 2, "strong_copyleft": 3, "network_copyleft": 4,
          "proprietary": 3}


def familia_de(licencia: Optional[str]) -> str:
    l = (licencia or "").strip().upper()
    if not l or l in ("NOASSERTION", "NONE", "UNKNOWN"):
        return "unknown"
    if re.search(r"\bAGPL|SSPL|OSL-|RPL-|EUPL-1\.0", l):
        return "network_copyleft"
    if re.search(r"\bLGPL|MPL-|EPL-|CDDL|EUPL|CPL-|MS-RL|CECILL-C|LGPLLR", l):
        return "weak_copyleft"
    if re.search(r"\bGPL|CECILL-2|CC-BY-SA|ODBL", l):
        return "strong_copyleft"
    if re.search(r"PROPRIETARY|COMMERCIAL|LICENSEREF-|ALL RIGHTS RESERVED|EULA|ELASTIC-2|BUSL", l):
        return "proprietary"
    if re.search(r"\bMIT|BSD|APACHE|ISC|ZLIB|UNLICENSE|0BSD|PSF|PYTHON-2|BSL-1|WTFPL|CC0|X11|POSTGRESQL|"
                 r"OPENSSL|CURL|ARTISTIC|RUBY|BLUEOAK|UPL|NCSA|W3C|PHP-3|JSON", l):
        return "permissive"
    return "unknown"


def familia_de_expresion(expr: Optional[str]) -> str:
    if not expr:
        return "unknown"
    texto = expr.replace("(", " ").replace(")", " ")
    alternativas = re.split(r"\s+OR\s+", texto, flags=re.I)
    mejores = []
    for alt in alternativas:
        partes = re.split(r"\s+AND\s+|\s+WITH\s+", alt, flags=re.I)
        familias = [familia_de(p) for p in partes if p.strip() and not p.strip().lower().endswith("exception")]
        mejores.append(max(familias, key=lambda f: _RANGO[f]) if familias else "unknown")
    return min(mejores, key=lambda f: _RANGO[f])


def _lista(texto: Optional[str]) -> set[str]:
    return {x.strip().upper() for x in (texto or "").split(",") if x.strip()}


def evaluar(licencia: Optional[str], distribucion: Optional[str], origen: Optional[str],
            permitidas: Optional[str] = None, prohibidas: Optional[str] = None,
            licencia_del_producto: Optional[str] = None) -> Optional[dict]:
    """None si no hay nada que decir; si no, {level: conflict|warning, reason, family}."""
    familia = familia_de_expresion(licencia)
    ids = {p.strip().upper() for p in re.split(r"\s+(?:AND|OR|WITH)\s+|[()]", licencia or "", flags=re.I) if p.strip()}
    if ids & _lista(prohibidas):
        return {"level": "conflict", "reason": "denied", "family": familia}
    if _lista(permitidas) and ids and not (ids & _lista(permitidas)) and familia != "permissive":
        return {"level": "conflict", "reason": "not_allowed", "family": familia}
    distribuido = distribucion == "distributed" or origen == "purchased"
    servicio = distribucion == "saas" or origen == "saas"
    propietario = familia_de_expresion(licencia_del_producto) == "proprietary" or origen in ("purchased", "in_house")
    if familia == "network_copyleft" and (servicio or distribuido):
        return {"level": "conflict", "reason": "network_copyleft_service", "family": familia}
    if familia == "strong_copyleft" and distribuido and propietario:
        return {"level": "conflict", "reason": "copyleft_distributed", "family": familia}
    if familia == "unknown":
        return {"level": "warning", "reason": "unknown_license", "family": familia}
    if familia in ("strong_copyleft", "network_copyleft") and propietario:
        return {"level": "warning", "reason": "copyleft_review", "family": familia}
    return None
