"""Una tabla, dos formatos: el sitio donde se decide CSV o XLSX.

Auditoría 2026-09. La pantalla de exportaciones tiene un selector CSV/XLSX
desde siempre y **el servidor sólo servía CSV**. La auditoría de agosto lo dejó
anotado como «el selector sigue en pantalla y no tiene contrapartida: queda
anotado, no arreglado, porque generar XLSX es trabajo de producto», y de
momento hizo lo honesto — que la extensión del fichero saliera del formato real
y no del botón pulsado, porque *un fichero llamado `.xlsx` con CSV dentro es
peor que uno llamado `.csv`*.

Esto es esa contrapartida. `openpyxl` ya era dependencia del proyecto, así que
el trabajo no era generar la hoja: era **no escribir dos veces cada export**.

## Por qué un módulo y no un `if` en cada endpoint

Porque son dos exports hoy y serán más, y la parte que cambia entre ellos es la
consulta y las columnas — no el formato. Con esto, añadir un export nuevo es
escribir su cabecera y sus filas; el formato ya está resuelto, y resuelto en un
solo sitio significa que arreglar un fallo de codificación o de tipos se hace
una vez.

## Decisiones de la hoja XLSX, para que no haya que adivinarlas

* **La cabecera va en negrita y congelada.** Una tabla de mil filas sin cabecera
  fija se lee mal, y es gratis.
* **Los anchos se calculan sobre el contenido**, con un tope: sin eso, una
  descripción larga deja una columna de trescientos caracteres y la hoja no se
  puede mirar.
* **Los números van como números**, no como texto. Es la razón de ser del XLSX
  frente al CSV: si las horas llegan como cadena, no se pueden sumar, y quien
  pide un Excel lo pide para sumar.
* **Las fechas van como fecha**, con formato ISO. Igual argumento.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Sequence

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

#: Los dos formatos que entiende. Un tercero se añade aquí y en `_ESCRITORES`.
FORMATOS = ("csv", "xlsx")

_TIPO_MIME = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

#: Tope de ancho de columna en la hoja, en caracteres.
_ANCHO_MAXIMO = 60


def _csv(cabecera: Sequence[str], filas: Iterable[Sequence[Any]]) -> bytes:
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(cabecera)
    for fila in filas:
        escritor.writerow(fila)
    # `utf-8-sig`: el BOM es lo que hace que Excel abra un CSV con acentos sin
    # destrozarlos. Sin el, «Imputación» se ve como «ImputaciÃ³n», y eso se
    # reporta como «el export esta roto».
    return salida.getvalue().encode("utf-8-sig")


def _xlsx(cabecera: Sequence[str], filas: Iterable[Sequence[Any]], titulo: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    libro = Workbook()
    hoja = libro.active
    # El nombre de una hoja no admite mas de 31 caracteres ni ciertos signos.
    hoja.title = "".join(c for c in titulo if c not in "[]:*?/\\")[:31] or "Datos"

    hoja.append(list(cabecera))
    for celda in hoja[1]:
        celda.font = Font(bold=True)
        celda.alignment = Alignment(vertical="center")
    hoja.freeze_panes = "A2"

    anchos = [len(str(c)) for c in cabecera]
    for fila in filas:
        valores = [_valor_para_hoja(v) for v in fila]
        hoja.append(valores)
        for i, v in enumerate(valores):
            if i < len(anchos):
                anchos[i] = max(anchos[i], len(str(v if v is not None else "")))

    for i, ancho in enumerate(anchos, start=1):
        hoja.column_dimensions[get_column_letter(i)].width = min(ancho + 2, _ANCHO_MAXIMO)

    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def _valor_para_hoja(valor: Any) -> Any:
    """Deja pasar lo que Excel entiende y convierte el resto a texto.

    `Decimal` se pasa a `float` porque openpyxl no lo escribe; y un `Enum` o un
    modelo se pasan a texto, que es lo unico sensato que se puede hacer con
    ellos en una celda.
    """
    if valor is None or isinstance(valor, (str, int, float, bool, datetime, date)):
        return valor
    if isinstance(valor, Decimal):
        return float(valor)
    return str(getattr(valor, "value", valor))


def respuesta_tabular(
    formato: str,
    *,
    nombre: str,
    cabecera: Sequence[str],
    filas: Iterable[Sequence[Any]],
) -> StreamingResponse:
    """La descarga, en el formato pedido.

    `nombre` va sin extension: la pone esta funcion, y ese es medio motivo de
    que exista — que el nombre del fichero y su contenido no puedan discrepar,
    que es justo el defecto que la auditoria de agosto tuvo que parchear en el
    cliente.

    Un formato desconocido es **400 y no un CSV por defecto**: devolver otra
    cosa de la que se pide es como llamar `.xlsx` a un CSV.
    """
    formato = (formato or "csv").lower()
    if formato not in FORMATOS:
        raise HTTPException(
            400, f"Formato no soportado: {formato!r}. Admitidos: {', '.join(FORMATOS)}")

    filas = list(filas)
    contenido = _csv(cabecera, filas) if formato == "csv" else _xlsx(cabecera, filas, nombre)

    return StreamingResponse(
        iter([contenido]),
        media_type=_TIPO_MIME[formato],
        headers={"Content-Disposition": f"attachment; filename={nombre}.{formato}"},
    )
