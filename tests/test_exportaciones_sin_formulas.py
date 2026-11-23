"""Ningún generador de CSV/XLSX escribe texto del usuario sin neutralizar fórmulas.

Auditoría 02 A39 (segunda ronda). Estático y barato: recorre `app/` y falla si
un fichero escribe CSV/XLSX sin usar `app.core.celdas_seguras` (o el exportador
común, que ya lo usa). Si añades un generador nuevo, pásalo por
`fila_segura`/`dict_seguro`/`neutralizar_formula` o por `exportador_tabular`;
solo si de verdad no escribe datos del usuario, añádelo a LISTA_BLANCA con motivo.
"""
from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

ESCRITURA = re.compile(
    r"csv\.writer\(|csv\.DictWriter\(|\.writerows?\(|\bWorkbook\(|xlsxwriter|\.to_csv\(|\.to_excel\("
    r"|\bws\w*\.append\(|\.cell\([^)]*value\s*="
)
SEGURO = re.compile(r"celdas_seguras|exportador_tabular")

# fichero (relativo a app/) -> motivo por el que no necesita neutralizar
LISTA_BLANCA: dict[str, str] = {
    "core/celdas_seguras.py": "es la propia defensa",
}


def _generadores() -> list[str]:
    salida = []
    for p in APP.rglob("*.py"):
        texto = p.read_text(encoding="utf-8", errors="ignore")
        if ESCRITURA.search(texto):
            salida.append(p.relative_to(APP).as_posix())
    return sorted(salida)


def test_todo_generador_de_csv_xlsx_neutraliza_formulas():
    sin = []
    for rel in _generadores():
        if rel in LISTA_BLANCA:
            continue
        texto = (APP / rel).read_text(encoding="utf-8", errors="ignore")
        if not SEGURO.search(texto):
            sin.append(rel)
    assert not sin, f"Generadores de CSV/XLSX sin celdas_seguras (A39): {sin}"


def test_la_lista_blanca_no_tiene_ficheros_muertos():
    existentes = set(_generadores())
    muertos = [r for r in LISTA_BLANCA if not (APP / r).exists()]
    assert not muertos, muertos
    assert existentes, "el detector no encuentra ningún generador: la regex está rota"


def test_el_detector_ve_los_generadores_conocidos():
    g = set(_generadores())
    for esperado in ("services/exportador_tabular.py", "services/bi_export_service.py",
                     "services/presupuestos_seguir.py", "services/clientes_internos/cargos.py"):
        assert esperado in g, esperado


def test_las_exportaciones_propias_neutralizan_en_la_salida():
    from app.services.bi_report_delivery_service import _export_to_excel
    from app.services.presupuestos_seguir import neutralizar_formula  # importado = usado

    assert neutralizar_formula("=1+1") == "'=1+1"
    from io import BytesIO

    from openpyxl import load_workbook
    datos = _export_to_excel(["a", "b"], [{"a": "=HYPERLINK(1)", "b": -3}], sheet_name="t")
    hoja = load_workbook(BytesIO(datos)).active
    assert hoja["A2"].value == "'=HYPERLINK(1)" and hoja["B2"].value == -3
