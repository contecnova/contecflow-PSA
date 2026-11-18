"""Resumen IA de documentos: texto de Word, Excel, PowerPoint y OpenDocument (18-11-2026)."""
import io
import zipfile

from app.services.documents_service import _texto_de_ofimatica

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _zip(partes: dict[str, str]) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for nombre, xml in partes.items():
            z.writestr(nombre, xml)
    return b.getvalue()


def test_docx_saca_los_parrafos():
    xml = f'<w:document {W}><w:body><w:p><w:r><w:t>Política de seguridad</w:t></w:r></w:p>' \
          f'<w:p><w:r><w:t>Alcance</w:t></w:r></w:p></w:body></w:document>'
    texto = _texto_de_ofimatica(_zip({"word/document.xml": xml}))
    assert "Política de seguridad" in texto and "Alcance" in texto


def test_xlsx_y_pptx():
    xlsx = _zip({"xl/sharedStrings.xml": '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                                         '<si><t>Presupuesto</t></si></sst>'})
    pptx = _zip({"ppt/slides/slide1.xml": '<p:sld xmlns:p="p" xmlns:a="a"><a:p><a:r><a:t>Hoja de ruta</a:t></a:r></a:p></p:sld>'})
    assert "Presupuesto" in _texto_de_ofimatica(xlsx)
    assert "Hoja de ruta" in _texto_de_ofimatica(pptx)


def test_fichero_roto_no_levanta():
    assert _texto_de_ofimatica(b"no es un zip") is None
