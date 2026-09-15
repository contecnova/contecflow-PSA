"""La complejidad de `app/` no puede empeorar.

Auditoría 2026-08 (hallazgo 18). El hallazgo decía «complejidad excesiva» y
llevaba abierto toda la auditoría por una razón que no era la falta de ganas:
**no había ninguna medida**. `ruff.toml` selecciona `E, F, W, S, B`, y `C901` no
está entre ellas, así que una función podía pasar de 10 a 20 sin que nada dijera
nada. Sin medida no hay «mejor» ni «peor», sólo opiniones.

Este fichero es el trinquete. La medida la hace `scripts/audit_complejidad.py`,
que **llama a ruff** en vez de reimplementar McCabe: la definición de
complejidad ya existe y tener dos sería peor que tener una.

## Qué se registró, y por qué no es cero

`CONOCIDAS` es la foto de hoy: 74 funciones por encima de 10, con 173 de
exceso acumulado y 16 de máximo. Se llegó ahí desde 94 / 253 / 17,
quitando diecinueve funciones de la lista — y **ninguna se quitó
por partirla en trozos para bajar un número**. Las catorce escondían un defecto:

* cuatro eran copias literales del mismo dominio de tareas en dos módulos, y a
  una le faltaba la comprobación ABAC que la otra sí tenía;
* una era `TaskService`, 387 líneas de dominio duplicado sin un solo sitio de
  llamada y con las búsquedas por id sin acotar por organización;
* tres eran el mismo preámbulo de autenticación copiado en tres WebSocket;
* dos eran la tabla de comandos del bot escrita una vez para Slack y otra para
  Teams — y las dos copias no aceptaban los mismos verbos;
* y cuatro eran cascadas de `elif` que son, literalmente, una tabla: los
  operadores de búsqueda, las frecuencias de las tareas recurrentes, el
  reconocimiento del `User-Agent` y los contadores de la instantánea de
  seguridad. Un barrido por AST buscando esa firma sobre las que quedan
  devuelve **cero**: no queda ninguna escondida.

Las 81 que quedan son, en su mayoría, funciones largas pero lineales: reglas de
negocio encadenadas donde partir por partir mueve el problema de sitio y añade
indirección. Bajarlas es trabajo legítimo y hay que hacerlo; lo que **no** se va
a hacer es maquillar el número. Por eso el trinquete registra cada función con
su valor en vez de guardar sólo un total: un total baja partiendo cualquier cosa.

## Las tres reglas

1. Una función que **no está en la lista** no puede superar 10. Es la regla que
   importa: el código nuevo nace por debajo del umbral.
2. Una función que **sí está** no puede subir de su valor registrado.
3. Si una **mejora** —baja o desaparece—, el test también falla, y pide que
   actualices la lista. Es a propósito: mantiene la foto honesta y convierte
   cada mejora en un cambio deliberado y visible en el diff.

Para regenerar la lista después de una mejora:

    python scripts/audit_complejidad.py --lista
"""
import pytest

from scripts.audit_complejidad import UMBRAL, medir


CONOCIDAS = {
    ("app/api/v1/endpoints/ai_chat.py", "generate"): 12,
    ("app/api/v1/endpoints/ai_chat.py", "run_agent_stream"): 16,
    ("app/api/v1/endpoints/ai_modules.py", "transcribe_voice_audio"): 12,
    ("app/api/v1/endpoints/ai_providers.py", "test_provider"): 12,
    ("app/api/v1/endpoints/analytics.py", "run_query"): 13,
    ("app/api/v1/endpoints/bi_intelligence.py", "phase2_realtime_stream"): 15,
    ("app/api/v1/endpoints/capacity.py", "get_resource_leveling"): 11,
    ("app/api/v1/endpoints/m365.py", "sync_to_planner"): 12,
    ("app/api/v1/endpoints/service_desk/ai_auto_resolution.py", "run_auto_resolution_job"): 11,
    ("app/core/abac_enforce.py", "enforce_abac"): 11,
    ("app/core/csrf.py", "dispatch"): 11,
    ("app/core/settings_pubsub.py", "_subscriber_loop"): 12,
    ("app/core/uploads.py", "detect_mime_from_magic"): 14,
    ("app/core/uploads.py", "validate_upload"): 11,
    ("app/services/adhoc_analytics_service.py", "run_adhoc_query"): 14,
    ("app/services/adhoc_analytics_service.py", "run_analytics_drilldown"): 11,
    ("app/services/ai_chat/tool_execution/resources.py", "_get_imputations"): 13,
    ("app/services/ai_copilot_service.py", "get_ai_timesheet_anomalies"): 13,
    ("app/services/ai_modules/meetings.py", "process_meeting"): 11,
    ("app/services/ai_planning_service.py", "estimate_task_hours"): 12,
    ("app/services/ai_planning_service.py", "triage_ticket"): 14,
    ("app/services/alm_service.py", "clean_input"): 11,
    ("app/services/analytics_service.py", "get_advanced_utilization"): 13,
    ("app/services/approval_engine/_base.py", "_is_authorized"): 12,
    ("app/services/ask_the_data.py", "validate_sql"): 11,
    ("app/services/automations_service.py", "_accion_call_webhook"): 13,
    ("app/services/bi_collaboration_service.py", "resolve_comment"): 14,
    ("app/services/bi_export_service.py", "export_dashboard_excel"): 11,
    ("app/services/bi_intelligence_service.py", "ml_predict_project_overrun_lgbm"): 11,
    ("app/services/billing_reports_service.py", "run_system_report"): 11,
    ("app/services/billing_reports_service.py", "smartmatch"): 11,
    ("app/services/bpmn_process_service.py", "build_bpmn_xml"): 12,
    ("app/services/campaign_pdf.py", "generate_campaign_pdf"): 13,
    ("app/services/capacity_planning_service.py", "get_gantt_leveling"): 12,
    ("app/services/client_portal_service.py", "respond_to_fr"): 12,
    ("app/services/client_service.py", "get_client_360"): 11,
    ("app/services/cmdb/discovery.py", "discover_kubernetes"): 11,
    ("app/services/documents_service.py", "extract_document_text"): 13,
    ("app/services/enterprise_service.py", "_validate_webhook_url"): 11,
    ("app/services/enterprise_service.py", "update_worker"): 14,
    ("app/services/epics_service.py", "execute_nql_search"): 13,
    ("app/services/esign_service.py", "create_provider_envelope"): 13,
    ("app/services/key_management.py", "get_integration_rotation_status"): 11,
    ("app/services/key_management.py", "rotate_due_materials"): 11,
    ("app/services/m365_bi_embed_service.py", "export_dashboard_excel"): 14,
    ("app/services/m365_bi_embed_service.py", "export_dashboard_word"): 15,
    ("app/services/metrics/advanced.py", "metric_forecast_revenue"): 12,
    ("app/services/predictive_retraining_service.py", "evaluate_itsm_model_health"): 12,
    ("app/services/raci_service.py", "compute_retro_insights"): 14,
    ("app/services/raci_service.py", "compute_user_burnout_risk"): 12,
    ("app/services/rate_card_service.py", "get_effective_rate"): 11,
    ("app/services/scheduled_reports.py", "_execute_report"): 11,
    ("app/services/scheduled_reports_compat.py", "summarize_scheduled_reports"): 11,
    ("app/services/service_desk/ai_auto_resolution_service.py", "_search_kb"): 13,
    ("app/services/service_desk/change_impact_service.py", "generate_comms_plan"): 12,
    ("app/services/service_desk/change_impact_service.py", "generate_testing_plan"): 14,
    ("app/services/service_desk/change_impact_service.py", "simulate_change_whatif"): 15,
    ("app/services/service_desk/change_management_service.py", "advance_rollout_phase"): 11,
    ("app/services/service_desk/dynamic_forms_service.py", "_context_options_payload"): 11,
    ("app/services/service_desk/dynamic_forms_service.py", "_normalize_mapping_rule"): 13,
    ("app/services/service_desk/governance_compliance_service.py", "audit_incident_management"): 13,
    ("app/services/service_desk/governance_compliance_service.py", "generate_compliance_report"): 14,
    ("app/services/service_desk/predictive_analytics_service.py", "predict_sla_breach"): 11,
    ("app/services/service_desk/ticket_query_service.py", "build_ticket_list_query"): 13,
    ("app/services/service_desk/workflow_engine.py", "advance"): 11,
    ("app/services/service_desk/workflow_engine.py", "evaluate_expression"): 13,
    ("app/services/session_security.py", "_compute_risk"): 12,
    ("app/services/sla_service.py", "add_working_hours"): 13,
    ("app/services/task_service.py", "bulk_update_dates_record"): 13,
    ("app/services/task_service.py", "update_task_record"): 14,
    ("app/services/tasks/queries.py", "build_task_list_query"): 13,
    ("app/services/tasks/scheduling.py", "cascade_reschedule"): 12,
    ("app/services/user_service.py", "create_user_record"): 13,
    ("app/worker.py", "deliver_webhook_task"): 11,
}


@pytest.fixture(scope="module")
def medicion():
    return medir()


def test_ninguna_funcion_nueva_por_encima_del_umbral(medicion):
    """La regla que de verdad importa: lo nuevo nace por debajo de 10."""
    nuevas = {k: v for k, v in medicion.items() if k not in CONOCIDAS}
    assert not nuevas, (
        "funciones por encima de "
        f"{UMBRAL} que no estaban registradas:\n"
        + "\n".join(f"  {v:3}  {f}  {n}" for (f, n), v in sorted(nuevas.items()))
        + "\n\nNo la añadas a CONOCIDAS para que pase: pártela, o saca lo que "
          "esconde. La lista es la deuda que ya había, no un buzón."
    )


def test_ninguna_conocida_ha_empeorado(medicion):
    peores = {
        k: (CONOCIDAS[k], medicion[k])
        for k in CONOCIDAS
        if k in medicion and medicion[k] > CONOCIDAS[k]
    }
    assert not peores, (
        "funciones registradas que han crecido:\n"
        + "\n".join(f"  {f}  {n}: {antes} -> {ahora}"
                     for (f, n), (antes, ahora) in sorted(peores.items()))
    )


def test_la_foto_sigue_siendo_la_de_la_lista(medicion):
    """Si algo ha mejorado, hay que bajar el registro. A mano y a la vista.

    Falla ante una mejora **a propósito**. Un trinquete que sólo mira hacia
    arriba deja la foto envejecer: al cabo de unos meses la lista dice 16 donde
    el código dice 11, y entonces alguien puede subir de 11 a 16 sin que salte
    nada. Mantenerla exacta cuesta un comando y evita eso.
    """
    mejoradas = {
        k: (CONOCIDAS[k], medicion.get(k))
        for k in CONOCIDAS
        if k not in medicion or medicion[k] < CONOCIDAS[k]
    }
    assert not mejoradas, (
        "la complejidad ha bajado — enhorabuena, y actualiza la lista con "
        "`python scripts/audit_complejidad.py --lista`:\n"
        + "\n".join(f"  {f}  {n}: {antes} -> {ahora or 'por debajo del umbral'}"
                     for (f, n), (antes, ahora) in sorted(mejoradas.items()))
    )


def test_los_totales_registrados_cuadran(medicion):
    """Que los números de la cabecera no se queden viejos."""
    assert len(medicion) == len(CONOCIDAS)
    assert sum(v - UMBRAL for v in medicion.values()) == EXCESO_REGISTRADO
    assert max(medicion.values()) == MAXIMO_REGISTRADO


EXCESO_REGISTRADO = 173
MAXIMO_REGISTRADO = 16
