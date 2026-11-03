"""El selector CSV/XLSX de la pantalla de exportaciones ya tiene contrapartida.

Auditoría 2026-09. Esa pantalla ofrecía XLSX desde siempre y el servidor **sólo
servía CSV**. En agosto se hizo lo honesto mientras tanto —que la extensión del
fichero saliera del formato real y no del botón pulsado, porque *un fichero
llamado `.xlsx` con CSV dentro es peor que uno llamado `.csv`*— y quedó anotado.

Y había una segunda mentira más silenciosa: el botón de proyectos decía
literalmente «Descargar Excel de proyectos» y devolvía un CSV.
"""
import io
import zipfile

import pytest

from app.services.exportador_tabular import FORMATOS, respuesta_tabular
from fastapi import HTTPException


CABECERA = ["Fecha", "Proyecto", "Horas"]
FILAS = [
    ["2026-09-15", "Implantación ERP", 7.5],
    ["2026-09-16", "Migración", 8],
]


def _cuerpo(respuesta) -> bytes:
    """El contenido de un `StreamingResponse`, venga como venga.

    Starlette envuelve el iterador que se le pasa, y segun la version lo deja
    sincrono o lo convierte en asincrono. Se soportan los dos en vez de
    depender de cual toca.
    """
    it = respuesta.body_iterator
    if hasattr(it, "__anext__"):
        import asyncio

        async def _leer():
            return b"".join([trozo async for trozo in it])

        # `asyncio.run` y no `get_event_loop()`: si otro test del mismo proceso
        # cerró el bucle por defecto, `get_event_loop()` revienta (medido con
        # -n 4: «There is no current event loop»). Aquí nunca hay uno corriendo.
        return asyncio.run(_leer())
    return b"".join(it)


def test_el_csv_lleva_bom_para_que_excel_no_destroce_los_acentos():
    """El BOM no es decoración: sin él, «Implantación» se ve «ImplantaciÃ³n».

    Y eso se reporta como «el export está roto», que es exactamente lo que es
    desde el punto de vista de quien abre el fichero.
    """
    r = respuesta_tabular("csv", nombre="x", cabecera=CABECERA, filas=FILAS)
    cuerpo = _cuerpo(r)
    assert cuerpo.startswith(b"\xef\xbb\xbf")
    assert "Implantación".encode("utf-8") in cuerpo


def test_el_xlsx_es_un_xlsx_de_verdad():
    """Un `.xlsx` es un ZIP con un `xl/workbook.xml` dentro.

    Se comprueba así y no por la extensión precisamente porque el defecto que
    esto viene a cerrar era un fichero con la extensión de uno y el contenido
    de otro.
    """
    r = respuesta_tabular("xlsx", nombre="x", cabecera=CABECERA, filas=FILAS)
    cuerpo = _cuerpo(r)
    with zipfile.ZipFile(io.BytesIO(cuerpo)) as z:
        nombres = z.namelist()
    assert "xl/workbook.xml" in nombres


def test_el_nombre_y_el_contenido_no_pueden_discrepar():
    """La extensión la pone el exportador, no quien llama.

    Es medio motivo de que este módulo exista: mientras el nombre del fichero lo
    escribiera cada sitio de llamada, podía decir una cosa y el contenido otra.
    """
    for formato in FORMATOS:
        r = respuesta_tabular(formato, nombre="informe", cabecera=CABECERA, filas=FILAS)
        assert r.headers["content-disposition"] == f"attachment; filename=informe.{formato}"


def test_los_numeros_van_como_numeros_en_la_hoja():
    """Es la razón de ser del XLSX frente al CSV.

    Si las horas llegan como texto no se pueden sumar, y quien pide un Excel lo
    pide para sumar.
    """
    from openpyxl import load_workbook

    r = respuesta_tabular("xlsx", nombre="x", cabecera=CABECERA, filas=FILAS)
    libro = load_workbook(io.BytesIO(_cuerpo(r)))
    hoja = libro.active
    assert hoja["C2"].value == 7.5
    assert isinstance(hoja["C2"].value, (int, float))
    assert hoja["A1"].value == "Fecha"
    assert hoja["A1"].font.bold, "la cabecera va en negrita"
    assert hoja.freeze_panes == "A2", "y congelada"


def test_un_formato_desconocido_es_400_y_no_un_csv_por_defecto():
    """Devolver otra cosa de la que se pide es el defecto que esto cierra."""
    with pytest.raises(HTTPException) as exc:
        respuesta_tabular("pdf", nombre="x", cabecera=CABECERA, filas=FILAS)
    assert exc.value.status_code == 400
    assert "pdf" in str(exc.value.detail)


def test_una_tabla_vacia_sigue_teniendo_cabecera():
    """Sin filas, el fichero no puede venir vacío: la cabecera dice qué se pidió."""
    for formato in FORMATOS:
        r = respuesta_tabular(formato, nombre="x", cabecera=CABECERA, filas=[])
        assert _cuerpo(r), f"{formato} vino vacío"


# ── Y por la puerta de la API ───────────────────────────────────────────────

@pytest.mark.parametrize("ruta", [
    "/api/v1/analytics/exports/imputations-csv",
    "/api/v1/analytics/exports/projects-csv",
])
@pytest.mark.parametrize("formato,firma", [
    ("csv", b"\xef\xbb\xbf"),
    ("xlsx", b"PK"),   # un ZIP
])
def test_los_dos_exports_sirven_los_dos_formatos(client, admin_token, ruta, formato, firma):
    from tests.conftest import auth

    res = client.get(f"{ruta}?formato={formato}", headers=auth(admin_token))
    assert res.status_code == 200, res.text
    assert res.content.startswith(firma), (
        f"{ruta} con formato={formato} no devolvió lo que dice devolver"
    )
