"""ALM: busqueda de contratos y licencias en el servidor (segunda auditoria 2026-11).

Antes la pantalla pedia la lista entera y filtraba en el navegador cuando habia
texto o «renovacion urgente»; ahora `GET /alm/contracts` acepta `q` y
`renewal_urgent`, y `GET /alm/licenses` acepta `q` y `type`, y paginan a la vez.
"""
from __future__ import annotations

import datetime as dt
import uuid

from tests.conftest import auth
from tests.test_listados_paginados_y_sin_n_mas_1_2026_11 import _nuevo


def _titulos(r):
    assert r.status_code == 200, r.text
    return sorted(c["title"] for c in r.json()["items"])


def test_contratos_q_y_renovacion_urgente_se_filtran_y_paginan_en_el_servidor(client, db, admin_token):
    from app.core import timeutil
    from app.core.serializers import DIAS_RENOVACION_URGENTE
    from app.models.alm import ALMContract, ALMVendor

    sufijo = uuid.uuid4().hex[:6]
    proveedor = _nuevo(db, ALMVendor, name=f"Zeta_100%_{sufijo}")
    otro = _nuevo(db, ALMVendor, name=f"Otro-{sufijo}")
    hoy = timeutil.today()
    _nuevo(db, ALMContract, title=f"Soporte-{sufijo}", reference=f"REF-{sufijo}", vendor_id=otro.id,
           renewal_date=hoy + dt.timedelta(days=DIAS_RENOVACION_URGENTE))      # urgente (limite)
    _nuevo(db, ALMContract, title=f"Hosting-{sufijo}", vendor_id=proveedor.id,
           renewal_date=hoy + dt.timedelta(days=DIAS_RENOVACION_URGENTE + 1))  # no urgente
    _nuevo(db, ALMContract, title=f"Pasado-{sufijo}", vendor_id=otro.id,
           renewal_date=hoy - dt.timedelta(days=1))                             # ya vencido: no urgente
    h = auth(admin_token)
    get = lambda **p: client.get("/api/v1/alm/contracts", params=p, headers=h)

    # titulo, referencia (sin distinguir mayusculas) y proveedor; % y _ son texto
    assert _titulos(get(q=f"soporte-{sufijo}")) == [f"Soporte-{sufijo}"]
    assert _titulos(get(q=f"ref-{sufijo}")) == [f"Soporte-{sufijo}"]
    assert _titulos(get(q=f"zeta_100%_{sufijo}")) == [f"Hosting-{sufijo}"]
    assert _titulos(get(q=f"zeta_1%0_{sufijo}")) == []
    # urgente: de hoy a +60 dias, ambos incluidos, igual que `renewal_urgent` del serializador
    urgentes = get(renewal_urgent="true", q=sufijo)
    assert _titulos(urgentes) == [f"Soporte-{sufijo}"]
    assert all(c["renewal_urgent"] for c in urgentes.json()["items"])
    # el total y la pagina salen del filtro del servidor
    pagina = get(q=sufijo, page=1, page_size=2).json()
    assert pagina["meta"]["total"] == 3 and len(pagina["items"]) == 2


def test_licencias_q_y_tipo_se_filtran_en_el_servidor(client, db, admin_token):
    from app.models.alm import ALMLicense, ALMVendor

    sufijo = uuid.uuid4().hex[:6]
    proveedor = _nuevo(db, ALMVendor, name=f"Acme-{sufijo}")
    uno = _nuevo(db, ALMLicense, name=f"Editor-{sufijo}", vendor_id=proveedor.id)
    _nuevo(db, ALMLicense, name=f"Otra-{sufijo}", type=uno.type)
    h = auth(admin_token)
    r = client.get("/api/v1/alm/licenses", params={"q": f"ACME-{sufijo}"}, headers=h)
    assert [x["name"] for x in r.json()["items"]] == [f"Editor-{sufijo}"]
    r = client.get("/api/v1/alm/licenses", params={"q": sufijo, "type": uno.type.value}, headers=h)
    assert r.json()["meta"]["total"] == 2
