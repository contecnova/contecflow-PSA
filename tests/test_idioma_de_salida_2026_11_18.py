"""Idioma de salida, textos por clave y factura en otro idioma (18-11-2026).

Auditoria de textos fijos: los prompts de IA decian «Responde siempre en
español», la factura salia en castellano con «IVA» fijo, los avisos se
guardaban en castellano y las fechas iban en `%d/%m/%Y` con «UTC» al lado de
la hora del servidor. Estas pruebas fijan los casos clave.
"""
from __future__ import annotations

import io
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.services import formato_regional as fr
from app.services.textos_de_salida import TEXTOS, texto


# ── Helper de idioma de salida ───────────────────────────────────────────────

def test_el_idioma_explicito_gana():
    assert fr.idioma_de_salida(None, preferido="en-GB") == "en"
    assert fr.idioma_de_salida(None, preferido="zh_CN") == "zh"


def test_sin_nada_cae_al_idioma_por_defecto():
    assert fr.idioma_de_salida(None, preferido="xx") == fr.idioma(None)


def test_la_preferencia_del_usuario_manda(db):
    from app.models.user import UserPreference
    db.add(UserPreference(user_id="admin-test-id", language="zh"))
    db.commit()
    assert fr.idioma_de_salida(db, user_id="admin-test-id") == "zh"
    # Lo que se pide explicitamente (el idioma del cliente) gana a la del usuario.
    assert fr.idioma_de_salida(db, user_id="admin-test-id", preferido="en") == "en"


def test_instruccion_de_idioma_dice_el_idioma_y_no_castellano_fijo():
    en = fr.instruccion_de_idioma("en")
    assert "English" in en and "«en»" in en
    assert "español" not in en
    zh = fr.instruccion_de_idioma("zh")
    assert "Chinese" in zh
    chat = fr.instruccion_de_idioma("en", conversacional=True)
    assert "idioma en que te escriba el usuario" in chat and "English" in chat


def test_ningun_prompt_fija_el_castellano():
    """Los sitios de la auditoria ya no dicen «Responde siempre en español»."""
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1]
    for rel in ("app/api/v1/endpoints/ai_chat.py", "app/services/ai_chat/tool_execution/prompt.py",
                "app/services/service_desk/ai_suggest_service.py", "app/services/expense_service.py",
                "app/services/collaboration/_transcription.py", "app/services/ai_planning_service.py",
                "app/api/v1/endpoints/documents.py"):
        fuente = (raiz / rel).read_text(encoding="utf-8").lower()
        for fijo in ("responde siempre en español", "responde siempre en espanol", "en español,",
                     "breve en español", "reuniones en español"):
            assert fijo not in fuente, f"{rel}: {fijo}"


# ── Textos por clave ─────────────────────────────────────────────────────────

def test_texto_en_cada_idioma_y_respaldo_en_castellano():
    assert texto("aviso.aprobacion_aprobada.titulo", "en") == "Request approved"
    assert texto("aviso.aprobacion_aprobada.titulo", "zh") == "申请已批准"
    # Un idioma sin traduccion cae al castellano (el texto de siempre).
    assert texto("aviso.aprobacion_aprobada.titulo", "fr") == "Solicitud aprobada"
    assert texto("copilot.retraso", "en", dias=3) == "The task is 3 day(s) overdue."
    assert texto("no.existe", "en") == "no.existe"


def test_los_textos_de_operador_estan_en_es_en_zh():
    faltan = [k for k, v in TEXTOS.items() if not {"es", "en", "zh"} <= set(v)]
    assert not faltan, faltan


def test_el_aviso_sale_en_el_idioma_de_quien_lo_recibe(db):
    from app.models.enterprise import Notification
    from app.models.user import UserPreference
    from app.services.notifications import notify_user
    db.add(UserPreference(user_id="admin-test-id", language="en"))
    db.commit()
    n = notify_user(db, "admin-test-id", "system", "Solicitud aprobada", "X ha sido aprobada",
                    aviso={"titulo": "aviso.aprobacion_aprobada.titulo", "cuerpo": "aviso.aprobacion_aprobada.cuerpo",
                           "params": {"resumen": "X"}})
    db.commit()
    fila = db.get(Notification, n.id)
    assert fila.title == "Request approved"
    assert fila.body == "X has been approved"


# ── Fechas y zona horaria ────────────────────────────────────────────────────

def test_formato_de_fecha_por_idioma():
    d = date(2026, 1, 15)
    assert fr.formatear_fecha(d, "es") == "15/01/2026"
    assert fr.formatear_fecha(d, "en") == "2026-01-15"
    assert fr.formatear_fecha(d, "de") == "15.01.2026"
    assert fr.formatear_fecha(None, "es") == "—"


def test_la_hora_lleva_la_etiqueta_de_su_zona_y_no_utc_fijo():
    momento = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    texto_madrid = fr.formatear_fecha(momento, "es", con_hora=True, con_zona=True, zona=ZoneInfo("Europe/Madrid"))
    assert texto_madrid == "15/01/2026 13:00 CET"


# ── Factura en ingles con el impuesto configurado ────────────────────────────

def _texto_del_pdf(pdf: bytes) -> str:
    from pypdf import PdfReader
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)


def _factura(**cambios):
    from app.services.invoice_pdf import generate_invoice_pdf
    base = dict(invoice_number="INV-1", issue_date=date(2026, 1, 15), due_date=date(2026, 2, 15),
                client_name="ACME Ltd", client_address=None, client_vat="GB123", client_email=None,
                lines=[{"description": "Consulting", "unit": "h", "quantity": 2, "unit_price": 50.0,
                        "amount": 100.0}],
                subtotal=100.0, tax_rate=20.0, tax_amount=20.0, total=120.0, currency="GBP", simbolo="£")
    base.update(cambios)
    return generate_invoice_pdf(**base)


def test_factura_en_ingles_con_el_nombre_de_impuesto_configurado():
    texto_pdf = _texto_del_pdf(_factura(idioma="en", nombre_de_impuesto="GST"))
    # Las etiquetas de metadatos van en mayusculas (estilo `etiqueta`).
    assert "INVOICE" in texto_pdf and "ISSUE DATE" in texto_pdf and "BILL TO" in texto_pdf
    assert "GST" in texto_pdf and "(20%)" in texto_pdf
    assert "2026-01-15" in texto_pdf
    for castellano in ("FACTURA", "FECHA EMISIÓN", "IVA", "DATOS DEL CLIENTE"):
        assert castellano not in texto_pdf


def test_factura_sin_idioma_sigue_en_castellano_con_iva():
    texto_pdf = _texto_del_pdf(_factura())
    assert "FACTURA" in texto_pdf and "IVA (20%)" in texto_pdf and "15/01/2026" in texto_pdf


def test_el_impuesto_sale_del_ajuste_de_la_empresa_o_del_idioma(db, monkeypatch):
    from app.services import invoice_pdf
    from app.services import settings_service
    assert invoice_pdf.nombre_del_impuesto(db, None, "en") == "VAT"
    assert invoice_pdf.nombre_del_impuesto(db, None, "de") == "MwSt."
    monkeypatch.setattr(settings_service, "get_runtime_str",
                        lambda _db, clave, _org=None, *a, **k: "GST" if clave == "TAX_NAME" else None)
    assert invoice_pdf.nombre_del_impuesto(db, "org-1", "en") == "GST"
