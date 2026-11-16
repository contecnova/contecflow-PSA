"""Acta de entrega/devolución en el idioma de la persona (16-11-2026).

El PDF salía en español o inglés según el idioma de la plataforma y el chino
caía al inglés; además las fuentes base de reportlab no tienen glifos CJK. Los
operadores trabajan en es/en/zh (obligatorios), así que el acta sale en el
idioma de la persona del acta y, en chino, con la fuente CID STSong-Light.
"""
from types import SimpleNamespace

from app.services import alm_actas


def test_hay_textos_del_acta_en_los_tres_idiomas_de_operador():
    claves = set(alm_actas._TEXTOS["es"])
    for idioma in ("es", "en", "zh"):
        assert set(alm_actas._TEXTOS[idioma]) == claves, idioma


def test_el_chino_usa_una_fuente_con_glifos_cjk():
    from reportlab.pdfbase import pdfmetrics
    normal, negrita = alm_actas._fuentes("zh")
    assert normal == negrita == alm_actas._FUENTE_CJK
    assert alm_actas._FUENTE_CJK in pdfmetrics.getRegisteredFontNames()
    assert alm_actas._fuentes("es") == ("Helvetica", "Helvetica-Bold")


def test_el_idioma_es_el_de_la_persona_y_si_no_el_de_la_plataforma(db, monkeypatch):
    from app.models.user import UserPreference
    from app.core.config import settings

    class _Q:
        def __init__(self, pref): self.pref = pref
        def filter(self, *a, **k): return self
        def first(self): return self.pref

    asignacion = SimpleNamespace(holder_type="user", holder_user_id="u-1")
    falso = SimpleNamespace(query=lambda m: _Q(SimpleNamespace(language="zh-CN") if m is UserPreference else None))
    assert alm_actas._idioma_del_acta(falso, asignacion) == "zh"

    monkeypatch.setattr(settings, "DEFAULT_LANGUAGE", "es")
    sin_pref = SimpleNamespace(query=lambda m: _Q(None))
    assert alm_actas._idioma_del_acta(sin_pref, asignacion) == "es"

    a_un_proyecto = SimpleNamespace(holder_type="project", holder_user_id=None)
    assert alm_actas._idioma_del_acta(sin_pref, a_un_proyecto) == "es"

    sin_textos = SimpleNamespace(query=lambda m: _Q(SimpleNamespace(language="de")))
    assert alm_actas._idioma_del_acta(sin_textos, asignacion) == "en"
