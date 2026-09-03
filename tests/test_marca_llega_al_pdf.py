"""Que la marca del cliente LLEGUE al documento, no sólo que se calcule bien.

Auditoría 2026-08 (hallazgo 32). Este fichero existe por una razón concreta:
**un resolutor de marca que no esté cableado pasa todos los tests unitarios.**
`tests/test_marca_en_documentos.py` comprueba que la paleta se calcula bien, y
eso no dice nada de que el generador la use ni de que el endpoint se la pase. El
hallazgo original era exactamente eso —un modelo con pantalla, correcto, y
conectado a nada— así que la prueba tiene que cerrar el circuito entero.

Se cierra por los dos lados, porque ninguno basta solo:

1. **el generador la usa**, y se ve *qué campos pide*;
2. **el endpoint se la pasa**, resolviendo la marca de la organización.

## Cómo se comprueba, y qué se descartó

Lo primero que intenté fue buscar el color en los bytes del PDF. **No sirve:**
ReportLab comprime el flujo de contenido, así que en crudo no hay ningún
operador de color, y al descomprimirlo con `pypdf` el acceso al contenido de las
páginas resultó poco fiable —una lectura daba dos colores y la siguiente cero—.
Un test cuya medición es inestable no verifica: da verde o rojo por motivos que
no son el código.

Lo que sí es estable y además dice más: **espiar la paleta**. Un envoltorio
registra cada `color(campo)` que pide el generador, así que el test afirma
directamente «este generador lee el color de la cabecera de la paleta que se le
pasa» — que es la afirmación que interesa, y no una consecuencia indirecta de
ella. Medido antes de cablear, la factura pedía nueve campos y
`texto_sobre_cabecera` **no estaba entre ellos**: la cabecera iba fija en
`colors.white`.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.services._pdf_marca import PALETA_DE_FACTURA, PALETA_POR_DEFECTO
from app.services.invoice_pdf import generate_invoice_pdf
from app.services.report_pdf import generate_report_pdf
from tests.conftest import auth


class _PaletaEspia:
    """Envuelve una paleta y registra qué campos le piden.

    Duck typing a propósito: `PaletaDeDocumento` es `frozen` con `slots`, así
    que no admite estado extra. El generador sólo llama a `color(campo)` y lee
    atributos, y las dos cosas se delegan.
    """

    def __init__(self, real):
        self._real = real
        self.pedidos: list[str] = []

    def color(self, nombre: str):
        self.pedidos.append(nombre)
        return self._real.color(nombre)

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)


def _factura(paleta=None, **kw):
    argumentos = dict(
        invoice_number="F-2026-0184",
        issue_date="2026-01-15",
        due_date="2026-02-15",
        client_name="Talleres Ruiz",
        client_address="Calle Mayor 1",
        client_vat="B12345678",
        client_email="cuentas@talleresruiz.es",
        lines=[{"description": "Horas de ingeniería", "unit": "h",
                "quantity": 10, "unit_price": 65.0, "amount": 650.0,
                "discount_pct": 0}],
        subtotal=650.0, tax_rate=21.0, tax_amount=136.5, total=786.5,
        currency="EUR", company_name="Acme Ingeniería",
    )
    argumentos.update(kw)
    if paleta is not None:
        argumentos["paleta"] = paleta
    return generate_invoice_pdf(**argumentos)


# ── 1. El generador usa la paleta que se le pasa ────────────────────────────

def test_EL_CIERRE_DEL_CIRCUITO_la_factura_usa_la_paleta_que_recibe():
    """Si el generador ignorara el parámetro, no pediría ningún campo."""
    espia = _PaletaEspia(PALETA_DE_FACTURA)
    _factura(paleta=espia)
    assert espia.pedidos, (
        "el generador no ha leído ni un color de la paleta que se le pasó: "
        "la está ignorando"
    )


@pytest.mark.parametrize("campo", [
    "fondo_de_cabecera",       # la banda que lleva el color de marca
    "acento",                  # líneas y énfasis
    "texto_sobre_cabecera",    # el que faltaba: iba fijo en colors.white
])
def test_EL_HALLAZGO_la_factura_pide_los_tres_campos_de_marca(campo):
    """Los tres que sustituye la marca del tenant.

    `texto_sobre_cabecera` es el que no se pedía antes de cablear —la cabecera
    iba fija en `colors.white`—, y sin él la guarda de contraste no sirve de
    nada: se calcularía un color legible que nadie usa.
    """
    espia = _PaletaEspia(PALETA_DE_FACTURA)
    _factura(paleta=espia)
    assert campo in espia.pedidos, (
        "la factura no lee '%s' de la paleta; pide: %s"
        % (campo, sorted(set(espia.pedidos)))
    )


@pytest.mark.parametrize("campo", ["fondo_de_cabecera", "acento",
                                   "texto_sobre_cabecera"])
def test_el_informe_pide_los_mismos_tres_campos(campo):
    espia = _PaletaEspia(PALETA_POR_DEFECTO)
    generate_report_pdf(
        title="Horas por proyecto", metric_label="Horas",
        data=[{"Proyecto": "Acme", "Horas": 120}], paleta=espia,
    )
    assert campo in espia.pedidos, (
        "el informe no lee '%s'; pide: %s" % (campo, sorted(set(espia.pedidos)))
    )


def test_el_texto_del_cuerpo_sigue_saliendo_de_la_paleta_base():
    """Control de que el cableado no ha movido lo que no debía: el texto del
    cuerpo se sigue leyendo, y de los campos neutros."""
    espia = _PaletaEspia(PALETA_DE_FACTURA)
    _factura(paleta=espia)
    for campo in ("texto_principal", "texto_secundario", "fila_alterna"):
        assert campo in espia.pedidos


def test_sin_paleta_se_usa_la_de_producto():
    """Compatibilidad: los llamadores que no pasan paleta siguen funcionando y
    el documento sale igual que antes."""
    pdf = _factura()
    assert pdf.startswith(b"%PDF")


def test_una_factura_con_marca_sigue_generandose_completa():
    """La marca no puede romper el documento."""
    import io

    from pypdf import PdfReader

    pdf = _factura(paleta=replace(PALETA_DE_FACTURA,
                                  fondo_de_cabecera="#c0392b",
                                  texto_sobre_cabecera="#ffffff",
                                  acento="#16a085"))
    assert pdf.startswith(b"%PDF")
    lector = PdfReader(io.BytesIO(pdf))
    texto = "".join(p.extract_text() or "" for p in lector.pages)
    assert "F-2026-0184" in texto
    assert "Acme Ingeniería" in texto


def test_una_marca_con_cabecera_clara_no_rompe_la_factura():
    """El caso de la guarda de contraste, de extremo a extremo: amarillo de
    cabecera con texto negro calculado."""
    import io

    from pypdf import PdfReader

    pdf = _factura(paleta=replace(PALETA_DE_FACTURA,
                                  fondo_de_cabecera="#ffe066",
                                  texto_sobre_cabecera="#000000"))
    lector = PdfReader(io.BytesIO(pdf))
    assert "F-2026-0184" in "".join(p.extract_text() or "" for p in lector.pages)


# ── 2. El endpoint resuelve la marca y se la pasa ───────────────────────────

class TestElEndpointPasaLaMarca:
    """La otra mitad del circuito.

    Que el generador acepte una paleta no sirve de nada si el endpoint no se la
    pasa — y eso es exactamente la forma del hallazgo original.

    La factura la **crea el test**. La primera versión hacía `skip` cuando la
    base no traía ninguna, y con eso los dos tests que de verdad cierran el
    circuito no verificaban nada: se saltaban en silencio. Un test que se salta
    y un test que pasa se leen igual en la salida de pytest.
    """

    def _org_del_admin(self, db):
        from app.models.user import User
        org_id = db.query(User.organization_id).filter(
            User.username == "admin").scalar()
        assert org_id, "el administrador de los tests no tiene organización"
        return org_id

    def _factura_en_la_base(self, db, org_id):
        from datetime import date

        from app.models.billing_reports import Invoice, InvoiceLine

        inv = Invoice(
            organization_id=org_id, number="F-MARCA-001",
            client_name="Talleres Ruiz", issue_date=date(2026, 1, 15),
            subtotal=650.0, tax_rate=21.0, tax_amount=136.5, total=786.5,
            currency="EUR",
        )
        db.add(inv)
        db.flush()
        db.add(InvoiceLine(
            invoice_id=inv.id, description="Horas de ingeniería", unit="h",
            quantity=10, unit_price=65.0, amount=650.0, order=1,
        ))
        db.commit()
        return inv

    def _espiar_el_generador(self, monkeypatch) -> dict:
        capturado = {}

        def espia(**kw):
            capturado.update(kw)
            return b"%PDF-fake"

        monkeypatch.setattr("app.services.invoice_pdf.generate_invoice_pdf", espia)
        return capturado

    def test_EL_HALLAZGO_la_factura_del_endpoint_lleva_la_marca_del_tenant(
            self, client, admin_token, db, monkeypatch):
        from app.models.white_label import OrgBranding

        org_id = self._org_del_admin(db)
        db.add(OrgBranding(organization_id=org_id, app_name="Acme Ingeniería",
                           primary_color="#c0392b", accent_color="#16a085"))
        factura = self._factura_en_la_base(db, org_id)
        capturado = self._espiar_el_generador(monkeypatch)

        res = client.get(f"/api/v1/billing-reports/invoices/{factura.id}/pdf",
                         headers=auth(admin_token))
        assert res.status_code == 200, res.text
        assert capturado, "el endpoint no ha llamado al generador"

        paleta = capturado.get("paleta")
        assert paleta is not None, (
            "el endpoint no pasa paleta: la marca del tenant no llega al PDF"
        )
        assert paleta.fondo_de_cabecera == "#c0392b"
        assert paleta.acento == "#16a085"
        assert capturado.get("company_name") == "Acme Ingeniería", (
            "el nombre de la factura sigue siendo el de la plataforma"
        )

    def test_sin_marca_configurada_el_endpoint_usa_la_paleta_de_producto(
            self, client, admin_token, db, monkeypatch):
        """Una organización que nunca configuró su marca no puede recibir un
        documento roto ni un 500."""
        factura = self._factura_en_la_base(db, self._org_del_admin(db))
        capturado = self._espiar_el_generador(monkeypatch)

        res = client.get(f"/api/v1/billing-reports/invoices/{factura.id}/pdf",
                         headers=auth(admin_token))
        assert res.status_code == 200, res.text
        assert capturado["paleta"].fondo_de_cabecera ==             PALETA_DE_FACTURA.fondo_de_cabecera
        assert capturado["company_name"], "el documento no puede ir sin nombre"

    def test_una_marca_con_colores_ilegibles_no_tumba_la_descarga(
            self, client, admin_token, db, monkeypatch):
        """El color lo escribe una persona en una pantalla. Que ponga «azul» no
        puede impedir que su cliente reciba la factura."""
        from app.models.white_label import OrgBranding

        org_id = self._org_del_admin(db)
        db.add(OrgBranding(organization_id=org_id, primary_color="azul",
                           accent_color="", text_color="rgb(1,2,3)"))
        factura = self._factura_en_la_base(db, org_id)
        capturado = self._espiar_el_generador(monkeypatch)

        res = client.get(f"/api/v1/billing-reports/invoices/{factura.id}/pdf",
                         headers=auth(admin_token))
        assert res.status_code == 200, res.text
        assert capturado["paleta"].fondo_de_cabecera ==             PALETA_DE_FACTURA.fondo_de_cabecera


class TestLaRutaQueUsaLaInterfaz:
    """`GET /invoices/{id}/pdf` — y esto es lo peor que salió del hallazgo 32.

    Había **dos** generadores de PDF de factura, independientes: el bueno
    (`invoice_pdf.py`, con trazado, paginación, marca y datos fiscales) detrás de
    `/billing-reports/invoices/{id}/pdf`, ruta que **no llamaba nadie**; y uno
    dibujado a mano con `rl_canvas`, que es **el que llama la interfaz** —en
    `_core.ts`, `api.get` sobre `/invoices/<id>/pdf`.

    La factura que descargaba el usuario **no llevaba el NIF del cliente**, ni
    su dirección, ni el nombre del emisor, ni la referencia de pedido, ni el
    periodo, ni las notas — y truncaba la descripción de cada línea a 50
    caracteres con un `[:50]` silencioso. Una factura sin identificación fiscal
    de las dos partes no es una factura válida.

    Y de paso: todo el trabajo de trazado del otro generador —incluido el
    arreglo del `NOSPLIT` que impedía emitir facturas de 29 líneas o más— vivía
    en una ruta que nadie pedía.
    """

    def _org_del_admin(self, db):
        from app.models.user import User
        org_id = db.query(User.organization_id).filter(
            User.username == "admin").scalar()
        assert org_id
        return org_id

    def _factura_completa(self, db, org_id, *, descripcion=None, n_lineas=1):
        from datetime import date

        from app.models.billing_reports import Invoice, InvoiceLine

        inv = Invoice(
            organization_id=org_id, number="F-UI-001",
            client_name="Talleres Ruiz",
            client_address="Calle Mayor 1, 08001 Barcelona",
            client_vat="B12345678",
            client_email="cuentas@talleresruiz.es",
            issue_date=date(2026, 1, 15), due_date=date(2026, 2, 15),
            subtotal=650.0, tax_rate=21.0, tax_amount=136.5, total=786.5,
            currency="EUR", po_reference="PO-2026-77",
            period_from=date(2026, 1, 1), period_to=date(2026, 1, 31),
            notes="Condiciones acordadas en el contrato marco.",
        )
        db.add(inv)
        db.flush()
        for i in range(n_lineas):
            db.add(InvoiceLine(
                invoice_id=inv.id,
                description=descripcion or f"Horas de ingeniería {i + 1}",
                unit="h", quantity=10, unit_price=65.0, amount=650.0, order=i,
            ))
        db.commit()
        return inv

    def _texto(self, pdf: bytes) -> str:
        import io

        from pypdf import PdfReader

        return "".join(p.extract_text() or ""
                       for p in PdfReader(io.BytesIO(pdf)).pages)

    def test_EL_HALLAZGO_la_factura_de_la_interfaz_lleva_el_NIF_del_cliente(
            self, client, admin_token, db):
        """El dato que la hacía inválida. Sin el NIF de las dos partes no es una
        factura, y el generador de lienzo no lo dibujaba."""
        factura = self._factura_completa(db, self._org_del_admin(db))
        res = client.get(f"/api/v1/invoices/{factura.id}/pdf",
                         headers=auth(admin_token))
        assert res.status_code == 200, res.text
        texto = self._texto(res.content)
        assert "B12345678" in texto, (
            "la factura que descarga la interfaz sigue sin el NIF del cliente"
        )

    @pytest.mark.parametrize("dato,valor", [
        ("dirección del cliente", "Calle Mayor 1"),
        ("referencia de pedido", "PO-2026-77"),
        ("notas", "contrato marco"),
    ])
    def test_los_datos_que_el_generador_de_lienzo_omitia(
            self, client, admin_token, db, dato, valor):
        factura = self._factura_completa(db, self._org_del_admin(db))
        res = client.get(f"/api/v1/invoices/{factura.id}/pdf",
                         headers=auth(admin_token))
        assert res.status_code == 200, res.text
        assert valor in self._texto(res.content), (
            "falta %s en la factura de la interfaz" % dato
        )

    def test_EL_HALLAZGO_la_descripcion_ya_no_se_trunca_a_50_caracteres(
            self, client, admin_token, db):
        """El `[:50]` era silencioso: el concepto salía cortado en el documento
        por el que se cobra, sin ningún aviso."""
        larga = ("Servicios de ingeniería de detalle para la línea de montaje "
                 "número tres, fase de puesta en marcha")
        assert len(larga) > 50
        factura = self._factura_completa(db, self._org_del_admin(db),
                                         descripcion=larga)
        res = client.get(f"/api/v1/invoices/{factura.id}/pdf",
                         headers=auth(admin_token))
        assert res.status_code == 200, res.text
        texto = self._texto(res.content).replace("\n", " ")
        cola = larga[-25:]
        assert cola in texto, (
            "la descripción sigue truncada: no aparece su final %r" % cola
        )

    def test_la_marca_del_tenant_llega_a_la_factura_de_la_interfaz(
            self, client, admin_token, db, monkeypatch):
        from app.models.white_label import OrgBranding

        org_id = self._org_del_admin(db)
        db.add(OrgBranding(organization_id=org_id, app_name="Acme Ingeniería",
                           primary_color="#c0392b"))
        factura = self._factura_completa(db, org_id)

        capturado = {}

        def espia(**kw):
            capturado.update(kw)
            return b"%PDF-fake"

        monkeypatch.setattr("app.services.invoice_pdf.generate_invoice_pdf", espia)
        res = client.get(f"/api/v1/invoices/{factura.id}/pdf",
                         headers=auth(admin_token))
        assert res.status_code == 200, res.text
        assert capturado["paleta"].fondo_de_cabecera == "#c0392b"
        assert capturado["company_name"] == "Acme Ingeniería"

    def test_una_factura_larga_se_emite_por_esta_ruta(self, client, admin_token, db):
        """El arreglo del `NOSPLIT` llega ya a donde importa: 60 líneas por la
        ruta que usa la interfaz, que antes iba por el otro generador."""
        import io

        from pypdf import PdfReader

        factura = self._factura_completa(db, self._org_del_admin(db), n_lineas=60)
        res = client.get(f"/api/v1/invoices/{factura.id}/pdf",
                         headers=auth(admin_token))
        assert res.status_code == 200, res.text
        assert len(PdfReader(io.BytesIO(res.content)).pages) > 1

    def test_se_conserva_la_descarga_como_adjunto_con_el_nombre_saneado(
            self, client, admin_token, db):
        """Contrato de esta ruta que no debe cambiar al delegar."""
        factura = self._factura_completa(db, self._org_del_admin(db))
        res = client.get(f"/api/v1/invoices/{factura.id}/pdf",
                         headers=auth(admin_token))
        assert res.headers["content-type"] == "application/pdf"
        assert "attachment" in res.headers["content-disposition"]
        assert "factura_F-UI-001.pdf" in res.headers["content-disposition"]

    def test_se_conserva_el_403_de_los_roles_sin_permiso(
            self, client, dev_token, db):
        factura = self._factura_completa(db, self._org_del_admin(db))
        res = client.get(f"/api/v1/invoices/{factura.id}/pdf",
                         headers=auth(dev_token))
        assert res.status_code == 403

    def test_se_conserva_el_404_de_una_factura_inexistente(
            self, client, admin_token, db):
        res = client.get("/api/v1/invoices/no-existe/pdf",
                         headers=auth(admin_token))
        assert res.status_code == 404
