"""Un valor único en una tabla con organización es único POR organización.

Revisión multitenant 2026-11. Diecinueve índices únicos eran globales en
tablas con `organization_id`: la segunda empresa no podía tener su
«PRJ-0001», su factura «INV-2026-001» ni sus tipos de tarea (la pantalla daba
500 al sembrarlos). Medido con una segunda organización en una copia de la base.

Este guardián recorre los modelos y falla si aparece un único sin
`organization_id` que no esté en la lista de abajo con su motivo. Una entrada
nueva en la lista es una decisión escrita, no una excepción por inercia.
"""
from __future__ import annotations

from datetime import date

from app.db.base import Base
import app.models  # noqa: F401  (registra todos los modelos)

_IDENTIDAD = "identidad o credencial: tiene que ser única en toda la plataforma"
_DEL_PADRE = "única dentro de su entidad padre, que ya es de una sola organización"

GLOBALES_A_PROPOSITO = {
    # `origen_id` es el UUID de la cadena de versiones de un presupuesto, que ya
    # pertenece a una sola organizacion: (origen_id, mes) no puede chocar entre empresas.
    ("budget_closes", ("origen_id", "mes")): "origen_id es un UUID de presupuesto, ya es de una sola organizacion",
    ("budget_variance_notes", ("origen_id", "mes", "tipo")): "origen_id es un UUID de presupuesto, ya es de una sola organizacion",
    ("users", ("email",)): "el correo identifica al usuario en el login, sea de la empresa que sea",
    ("users", ("username",)): _IDENTIDAD,
    ("client_users", ("email",)): "el correo identifica al cliente en el login del portal",
    ("api_keys", ("key_digest",)): _IDENTIDAD,
    ("api_keys", ("key_hash",)): _IDENTIDAD,
    ("cmdb_agent_registrations", ("token_hash",)): _IDENTIDAD,
    ("mfa_challenges", ("token_jti",)): _IDENTIDAD,
    ("oauth_apps", ("client_id",)): _IDENTIDAD,
    ("oauth_states", ("state",)): _IDENTIDAD,
    ("public_forms", ("token",)): "el token es la URL pública del formulario",
    ("user_sessions", ("refresh_token_jti",)): _IDENTIDAD,
    ("webauthn_credentials", ("credential_id",)): _IDENTIDAD,
    ("webhook_triggers", ("slug",)): "el slug es la URL pública del webhook entrante y se resuelve sin sesión",
    ("esign_envelopes", ("provider_envelope_id",)): "id que asigna el proveedor de firma, único en su sistema",
    ("collaboration_push_subscriptions", ("endpoint",)): "endpoint del navegador, único por dispositivo",
    ("integration_connectors", ("name",)): "catálogo global de la plataforma (NULL = global)",
    ("integration_connectors", ("slug",)): "catálogo global de la plataforma (NULL = global)",
    ("mfa_configs", ("user_id",)): _DEL_PADRE,
    ("onboarding_states", ("user_id",)): _DEL_PADRE,
    ("sem_profiles", ("user_id",)): _DEL_PADRE,
    ("user_preferences", ("user_id",)): _DEL_PADRE,
    ("collaboration_presence_states", ("user_id",)): _DEL_PADRE,
    ("collaboration_presence_states", ("client_user_id",)): _DEL_PADRE,
    ("client_portal_configs", ("client_id",)): _DEL_PADRE,
    ("kanban_configs", ("project_id",)): _DEL_PADRE,
    ("sprint_retro_notes", ("sprint_id",)): _DEL_PADRE,
    ("rev_entries", ("rev_contract_id", "period_year", "period_month")): _DEL_PADRE,
    ("sd_incident_to_problem", ("problem_id", "ticket_id")): _DEL_PADRE,
    ("sd_known_error_tickets", ("known_error_id", "ticket_id")): _DEL_PADRE,
    ("collaboration_attachment_versions", ("attachment_id", "version")): _DEL_PADRE,
    ("collaboration_bot_apps", ("workspace_id", "handle")): _DEL_PADRE,
    ("collaboration_channel_members", ("channel_id", "user_id")): _DEL_PADRE,
    ("collaboration_channels", ("conversation_id",)): _DEL_PADRE,
    ("collaboration_channels", ("team_id", "slug")): _DEL_PADRE,
    ("collaboration_direct_conversations", ("conversation_id",)): _DEL_PADRE,
    ("collaboration_drafts", ("user_id", "conversation_id", "parent_message_id")): _DEL_PADRE,
    ("collaboration_group_conversations", ("conversation_id",)): _DEL_PADRE,
    ("collaboration_pinned_messages", ("conversation_id", "message_id")): _DEL_PADRE,
    ("collaboration_reactions", ("message_id", "client_user_id", "emoji")): _DEL_PADRE,
    ("collaboration_reactions", ("message_id", "user_id", "emoji")): _DEL_PADRE,
    ("collaboration_reads", ("conversation_id", "client_user_id")): _DEL_PADRE,
    ("collaboration_reads", ("conversation_id", "user_id")): _DEL_PADRE,
    ("collaboration_saved_messages", ("user_id", "message_id")): _DEL_PADRE,
    ("collaboration_team_members", ("team_id", "user_id")): _DEL_PADRE,
    ("collaboration_teams", ("workspace_id", "slug")): _DEL_PADRE,
    ("collaboration_threads", ("root_message_id",)): _DEL_PADRE,
    ("collaboration_transcripts", ("call_id",)): _DEL_PADRE,
}


def _unicos_sin_organizacion() -> set:
    vistos = set()
    for tabla in Base.metadata.sorted_tables:
        if "organization_id" not in tabla.c:
            continue
        grupos = [(c.name,) for c in tabla.c if c.unique and not c.primary_key]
        grupos += [tuple(c.name for c in i.columns) for i in tabla.indexes if i.unique]
        grupos += [tuple(c.name for c in k.columns) for k in tabla.constraints
                   if k.__class__.__name__ == "UniqueConstraint"]
        vistos |= {(tabla.name, g) for g in grupos if "organization_id" not in g}
    return vistos


def test_EL_ESTRUCTURAL_ningun_unico_global_sin_motivo_en_una_tabla_con_organizacion():
    vistos = _unicos_sin_organizacion()
    assert len(vistos) >= 40, f"el guardián solo encontró {len(vistos)} únicos: no está mirando"
    nuevos = vistos - set(GLOBALES_A_PROPOSITO)
    assert not nuevos, (
        "Únicos globales en tablas con organización, sin motivo escrito. Hazlos únicos por "
        f"(organization_id, …) o añádelos a GLOBALES_A_PROPOSITO con su razón: {sorted(nuevos)}")
    sobran = set(GLOBALES_A_PROPOSITO) - vistos
    assert not sobran, f"Entradas que ya no existen, quítalas de la lista: {sorted(sobran)}"


def test_EL_HALLAZGO_dos_empresas_repiten_codigo_de_proyecto_y_numero_de_factura(db):
    from app.models.billing_reports import Invoice
    from app.models.mfa import Organization
    from app.models.project import Project, ProjectStatus, ProjectType
    db.add(Organization(id="org-b", name="B", slug="org-b"))
    db.flush()
    for org in ("1", "org-b"):
        db.add(Project(code="PRJ-0001", name=f"P {org}", status=ProjectStatus.active,
                       project_type=ProjectType.development, organization_id=org))
        db.add(Invoice(number="INV-2026-001", organization_id=org, client_name="C",
                       issue_date=date(2026, 11, 1), status="draft", total=1))
    db.commit()
