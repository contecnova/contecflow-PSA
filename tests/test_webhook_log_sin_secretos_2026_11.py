"""El log de un webhook entrante no guarda credenciales (revisión 2026-11).

Medido antes: `POST /webhooks/fire/{slug}` guardaba todas las cabeceras de la
petición en `webhook_trigger_logs.headers`: Authorization, Cookie y la firma.
"""
from __future__ import annotations

import hashlib
import hmac
import json

from app.models.cab import WebhookTrigger, WebhookTriggerLog


def test_EL_HALLAZGO_las_cabeceras_sensibles_se_tapan(client, db):
    db.add(WebhookTrigger(id="wt-1", name="Entrada", slug="entrada-secreta", secret="s3cr3t", is_active=True,
                          organization_id="1"))
    db.commit()
    cuerpo = b'{"a": 1}'
    firma = "sha256=" + hmac.new(b"s3cr3t", cuerpo, hashlib.sha256).hexdigest()
    r = client.post("/api/v1/webhooks/fire/entrada-secreta", content=cuerpo,
                    headers={"X-Contecflow-Signature": firma, "Authorization": "Bearer muy-secreto",
                             "X-Api-Key": "clave", "Content-Type": "application/json", "X-Origen": "erp"})
    assert r.status_code == 200, r.text
    cabeceras = json.loads(db.query(WebhookTriggerLog).filter(WebhookTriggerLog.trigger_id == "wt-1").one().headers)
    assert cabeceras["authorization"] == cabeceras["x-api-key"] == cabeceras["x-contecflow-signature"] == "[oculto]"
    assert cabeceras["x-origen"] == "erp"
    assert "muy-secreto" not in json.dumps(cabeceras)
