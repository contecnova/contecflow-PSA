# Pipeline comercial: regla de cálculo de totales

Auditoría 04b M9 (23-11-2026). Estándar de mercado (Salesforce/HubSpot), aplicado
igual en la API, el OLAP/BI, las métricas, los informes, el asistente y la pantalla.

| Concepto | Etapas que cuentan |
|---|---|
| Valor del pipeline abierto | `lead`, `qualification`, `proposal`, `negotiation` |
| Previsión ponderada (importe × probabilidad) | solo las abiertas |
| Tasa de éxito (win rate) | ganadas / (ganadas + perdidas) |
| Sin decisión (canceladas) | fuera del pipeline y de la tasa; se dan aparte (recuento e importe) |

- Una perdida o cancelada **no suma** aunque conserve una probabilidad puesta a mano.
- Las ganadas no son pipeline: son contratación (`won_ytd` / `won_revenue`).

## Dónde vive

- Estados: `app/models/pipeline.py` (`ETAPAS_ABIERTAS`, `ETAPAS_CERRADAS`,
  `ETAPAS_DECIDIDAS`, `ETAPA_GANADA/PERDIDA/CANCELADA`, `etapa_de`).
- Cálculo único en Python: `pipeline_service.resumir_pipeline(opps)`.
- Frontend: `frontend/src/constants/pipelineStages.ts` (`resumirPipeline`,
  `cumpleFiltroEstado`), espejo del anterior.

## Campos añadidos (los existentes se conservan)

- `GET /api/v1/pipeline/pipeline` → `summary`: `open_pipeline_value`, `won_count`,
  `lost_count`, `lost_value`, `cancelled_count`, `cancelled_value`.
- KPIs OLAP (`get_kpi_summary`, DuckDB y respaldo): `won_count`, `lost_count`,
  `cancelled_count`, `cancelled_value`, `win_rate`.
- Informe de pipeline (`run_pipeline_report`) → `totals`: `open_amount`, `open_count`,
  `won_count`, `lost_count`, `cancelled_count`, `cancelled_amount`, `win_rate`.
  `weighted_amount` pasa a ser solo de abiertas.
- Métrica `win_rate_evolution`: `lost` y `cancelled` por mes.

## Pantalla

Pipeline: KPIs de valor abierto, ponderado, abiertas, tasa de éxito (con ayuda) y
«Sin decisión (canceladas)»; filtro de estado Todas / Abiertas / Ganadas /
Perdidas / Canceladas (filtra tablero y lista; los KPIs no dependen de él).

Pruebas: `tests/test_pipeline_canceladas_2026_11_23.py`,
`frontend/src/constants/__tests__/pipelineStages.test.ts`.
