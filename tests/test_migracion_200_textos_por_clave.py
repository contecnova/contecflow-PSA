"""Migracion 200: textos del sistema guardados por clave y pintados al leer."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _fuente(ruta: str) -> str:
    return (RAIZ / ruta).read_text(encoding="utf-8")


def test_hitos_usan_sus_tipos_de_aviso():
    s = _fuente("app/services/milestone_service.py")
    assert '"milestone_approved"' in s and '"milestone_rejected"' in s
    assert 'notes_key="milestone.nota_factura"' in s
    from app.services.notifications import NOTIFICATION_ICONS
    assert "milestone_approved" in NOTIFICATION_ICONS and "milestone_rejected" in NOTIFICATION_ICONS


def test_nota_de_sla_por_clave_y_pintada_al_leer():
    s = _fuente("app/services/service_desk/sla_event_service.py")
    assert "note_key=clave" in s and "pintar(e.note_key" in s


def test_regla_sod_borra_la_clave_al_editar_la_descripcion():
    s = _fuente("app/services/grc_service.py")
    assert "rule.texto_clave = None" in s and "texto_clave=_clave_de_regla(r)" in s


def test_pintar_campo_con_params_dict():
    from app.services.textos_guardados import pintar, por_clave_json
    clave, datos = por_clave_json("sla.nota_reanudado", minutos=5)
    assert isinstance(datos, dict)
    assert "5" in pintar(clave, datos, "respaldo", "es")
    assert pintar(clave, datos, "respaldo", "en") != pintar(clave, datos, "respaldo", "es")
    assert pintar(None, None, "respaldo", "es") == "respaldo"
