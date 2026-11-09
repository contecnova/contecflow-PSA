"""RGPD: consentimientos por propósito, borrado completo y máscaras aplicadas (revisión 2026-11).

Medido antes: un consentimiento para otro propósito pisaba el anterior; al
resolver un borrado se volvía a escribir el identificador del interesado y el
historial quedaba; y las máscaras de campo se guardaban sin aplicarse.
"""
from __future__ import annotations

from app.models.project import Project, ProjectStatus, ProjectType
from app.services import bi_gdpr_service as g
from tests.conftest import auth


def test_un_proposito_no_pisa_a_otro(db):
    g.record_consent(db, user_id="u-1", consented=True, org_id="1", purpose="analytics")
    g.record_consent(db, user_id="u-1", consented=False, org_id="1", purpose="marketing")
    assert g.get_consent(db, user_id="u-1", org_id="1")["consented"] is True
    assert g.get_consent(db, user_id="u-1", org_id="1", purpose="marketing")["consented"] is False
    assert len(g.list_consents(db, org_id="1")) == 2


def test_EL_HALLAZGO_el_borrado_no_deja_rastro_del_interesado(db):
    g.record_consent(db, user_id="sujeto-9", consented=True, org_id="1")
    dsr = g.create_dsr(db, subject_id="sujeto-9", request_type="erasure", org_id="1", requester_user_id="admin")
    g.resolve_dsr(db, dsr_id=dsr["id"], org_id="1", execute_erasure_pipeline=True)
    assert g.get_consent(db, user_id="sujeto-9", org_id="1") is None
    assert g.get_consent_history(db, user_id="sujeto-9", org_id="1") == []
    resuelta = g.get_dsr(db, dsr_id=dsr["id"], org_id="1")
    assert resuelta["subject_id"] != "sujeto-9" and "sujeto-9" not in str(resuelta)


def test_EL_HALLAZGO_la_mascara_se_aplica_al_exportar(client, db, admin_token):
    db.add(Project(id="p-masc", code="SECRETO-1", name="Cliente confidencial", status=ProjectStatus.active,
                   project_type=ProjectType.consulting, organization_id="1"))
    db.commit()
    g.set_field_mask(db, dataset="projects", field="name", mask_type="redact", org_id="1")
    r = client.post("/api/v1/reports/export", headers=auth(admin_token),
                    json={"entity": "projects", "columns": ["code", "name"], "filters": []})
    assert "SECRETO-1" in r.text and "Cliente confidencial" not in r.text and "***" in r.text
