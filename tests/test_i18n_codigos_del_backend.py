r"""Códigos que manda el backend y la pantalla traduce con `t(\`prefijo_${código}\`)`.

Verificación 16-11-2026: la consola mostraba `[i18n-missing]` en GRC para
`retencion_tipo_{connector_calls,webhook_deliveries,email_logs,activity_events}`
e `informe_control_{sso_policy,session_revocation}`, y en el menú para
`nav.epic_gantt`. Se añadieron tipos de retención, controles y una entrada de
menú sin su texto, y ningún test lo cruzaba: la clave se construye en tiempo de
ejecución y el análisis estático de claves no la ve.

Aquí se leen las listas de la fuente de verdad (registro del backend, código del
informe, menú del armazón) y se exige su texto en cada idioma ofrecido.
"""
from __future__ import annotations

import re

from ._i18n_langs import RAIZ, fichero_de, idiomas_ofrecidos


def _bloque(texto: str, modulo: str) -> str:
    """Cuerpo del módulo `  modulo: { … }` de un diccionario."""
    m = re.search(r"\n  " + re.escape(modulo) + r": \{(.*?)\n  \},", texto, re.S)
    assert m, f"no está el módulo {modulo}"
    return m.group(1)


def _faltan(modulo: str, claves: list[str]) -> dict[str, list[str]]:
    faltan = {}
    for lang in idiomas_ofrecidos():
        cuerpo = _bloque(fichero_de(lang).read_text(encoding="utf-8"), modulo)
        sin = [k for k in claves if not re.search(r"\n    " + re.escape(k) + r":", cuerpo)]
        if sin:
            faltan[lang] = sin
    return faltan


def test_tipos_de_retencion_tienen_texto():
    from app.db.bloqueo_legal import TIPOS
    assert TIPOS
    assert not _faltan("grc", [f"retencion_tipo_{t}" for t in TIPOS])


def test_controles_del_informe_de_cumplimiento_tienen_texto():
    fuente = (RAIZ / "app" / "services" / "informe_de_cumplimiento.py").read_text(encoding="utf-8")
    ids = re.findall(r"_control\(\s*\"([a-z_]+)\"", fuente)
    assert len(ids) >= 15
    assert not _faltan("grc", [f"informe_control_{i}" for i in ids])


def test_rutas_del_menu_tienen_texto():
    fuente = (RAIZ / "frontend" / "src" / "components" / "layout" / "Layout.tsx").read_text(encoding="utf-8")
    m = re.search(r"const PATH_NAV_KEY[^{]*\{(.*?)\n\}", fuente, re.S)
    assert m
    alias = dict(re.findall(r"'([^']+)':\s*'([^']+)'", m.group(1)))
    rutas = set(re.findall(r"(?:path|to):\s*'(/[^']*)'", fuente))
    claves = sorted({alias.get(r) or r.lstrip("/").replace("-", "_") for r in rutas} - {""})
    assert len(claves) > 50
    assert not _faltan("nav", claves)


# ── Revisión GRC 16-11-2026: el resto de códigos de GRC que la pantalla traduce ──

def _literales(fuente: str, patron: str) -> set[str]:
    return set(re.findall(patron, fuente))


def test_campos_de_bloqueo_legal_tienen_texto():
    from app.db.bloqueo_legal import TIPOS
    campos = sorted({c for t in TIPOS.values() for c in t.campos})
    assert not _faltan("grc", [f"bloqueo_campo_{c}" for c in campos])


def test_riesgos_y_severidades_tienen_texto():
    from typing import get_args
    from app.schemas.grc import NivelDeRiesgo
    fuente = (RAIZ / "app" / "api" / "v1" / "endpoints" / "grc.py").read_text(encoding="utf-8")
    m = re.search(r"severity: Optional\[Literal\[([^\]]+)\]\]", fuente)
    assert m
    severidades = re.findall(r'"([a-z]+)"', m.group(1))
    assert not _faltan("grc", [f"riesgo_{r}" for r in get_args(NivelDeRiesgo)]
                       + [f"severidad_{s}" for s in severidades])


def test_eventos_de_la_auditoria_grc_tienen_texto():
    grc = (RAIZ / "app" / "api" / "v1" / "endpoints" / "grc.py").read_text(encoding="utf-8")
    sod = (RAIZ / "app" / "services" / "grc_sod.py").read_text(encoding="utf-8")
    eventos = _literales(grc, r'_log_grc\(\s*db,\s*[^,]+,\s*"([a-z_]+)"') | _literales(sod, r'action_type="([a-z_]+)"')
    assert len(eventos) >= 7
    assert not _faltan("grc", [f"evento_{e}" for e in sorted(eventos)])


def test_controles_y_tipos_de_evidencia_de_los_marcos_tienen_texto():
    from app.core import marcos_de_cumplimiento as m
    claves = [f"marco_control_{m.clave_de_texto(c)}" for ids in m.CONTROLES.values() for c in ids]
    claves += [f"evidencia_tipo_{t}" for t in m.TIPOS_DE_EVIDENCIA]
    assert not _faltan("grc", claves)


def test_detalles_del_explicador_de_accesos_tienen_texto():
    from app.core import permisos_de_proyecto
    fuente = (RAIZ / "app" / "services" / "explicar_acceso.py").read_text(encoding="utf-8")
    enforce = (RAIZ / "app" / "core" / "grc_enforce.py").read_text(encoding="utf-8")
    detalles = _literales(fuente, r'_capa\("[a-z]+",\s*\w+,\s*"([a-z_]+)"')
    detalles |= {x for par in re.findall(r'"([a-z_]+)" if [^\n]* else "([a-z_]+)"', fuente) for x in par}
    detalles |= _literales(fuente, r'\(_[a-z_]+,\s*"([a-z_]+)"\)')                    # _REGLAS_DE_SERVICIO
    detalles |= _literales(enforce, r'"reason":\s*"([a-z_]+)"')                         # grc_enforce.decidir
    detalles |= set(permisos_de_proyecto.MOTIVOS)                                       # capa «project»
    assert len(detalles) >= 35
    capas = _literales(fuente, r'_capa\("([a-z]+)"')
    assert not _faltan("grc", [f"acceso_detalle_{d}" for d in sorted(detalles)]
                       + [f"acceso_capa_{c}" for c in sorted(capas)])


def test_estados_de_las_solicitudes_rgpd_tienen_texto():
    from app.models.cab import GDPRRequestStatus
    assert not _faltan("pagina_ent", [f"rgpd_estado_{s.value}" for s in GDPRRequestStatus])


def test_estados_del_informe_tienen_texto():
    fuente = (RAIZ / "app" / "services" / "informe_de_cumplimiento.py").read_text(encoding="utf-8")
    m = re.search(r"for e in \(([^)]+)\)", fuente)
    assert m
    assert not _faltan("grc", [f"informe_estado_{e}" for e in re.findall(r'"([a-z_]+)"', m.group(1))])
