# Decisiones Arquitectónicas IA/ML (Wave G, items #76-83)

> Estas son **decisiones documentadas**, no bugs. Sirven como referencia para
> futuras evoluciones y para que cualquier nuevo desarrollador entienda el
> "porqué" detrás de elecciones que pueden parecer subóptimas a primera vista.

## #76 — TF-IDF como backend embeddings por defecto (no sentence-transformers)

**Decisión.** El motor semántico arranca con TF-IDF (`local_model_name="tfidf"`)
y solo conmuta a transformers (`all-MiniLM-L6-v2`) si el admin lo activa
explícitamente vía `/semantic-engine/config` → `embeddings_backend=transformer`.

**Por qué.**
- TF-IDF no requiere descarga de modelos (~90 MB) ni dependencia pesada
  (`sentence-transformers` + `torch`).
- Para corpus pequeños (<10k items) TF-IDF da resultados aceptables y es
  determinista.
- El deploy de Contecflow se distribuye también on-prem en clientes sin GPU
  ni acceso a HuggingFace.

**Cuándo migrar.** Si una organización supera 5k tickets/perfiles activos y se
observa que el ranking expert-cache es ruidoso, el admin puede conmutar a
transformer (la migración no requiere downtime: el `rebuild_profiles` re-genera
embeddings con el nuevo backend).

## #77 — `is_superadmin` como bypass multi-tenant, sin RLS de Postgres

**Decisión.** Los filtros `organization_id == cu.organization_id` se aplican en
SQLAlchemy a nivel de servicio, **no** con Row-Level Security de Postgres.
`is_superadmin=True` salta el filtro.

**Por qué.**
- Compatibilidad con SQLite (pruebas locales / single-tenant).
- Auditabilidad: las consultas son explícitas en el código, no implícitas en
  políticas RLS que son difíciles de debugar.
- El producto admite users superadmin globales (consultoría externa) que deben
  ver todos los tenants — RLS con `SET LOCAL` añadiría complejidad de sesión.

**Riesgo conocido.** Cada query que toca datos sensibles debe pasar por la
abstracción `_scope_by_org()` (helper en `ai_modules_service.py`). Si un
desarrollador olvida aplicarlo → leak. **Mitigación:** los tests de regresión
en `tests/integration/test_cross_tenant_*.py` verifican que un user de org A
no puede leer datos de org B vía endpoints AI.

## #78 — Dispatcher `call_ai()` como chokepoint único de LLMs

**Decisión.** Todo acceso a proveedores LLM (Anthropic, OpenAI, Azure, Bedrock,
Groq…) pasa por `app.services.ai_provider_service.call_ai()`. No hay clientes
SDK directos en endpoints/servicios.

**Por qué.**
- **Guardrails:** `check_prompt` / `check_output` aplicados en un único punto
  (Wave A, item #3) → 100% de cobertura PII/keyword en todo el sistema.
- **Cost tracking:** `_record_usage` mide tokens y mapea coste vía
  `PROVIDER_CATALOG` para reporting (`/ai-providers/usage/by-module`).
- **Fallback automático:** si el provider primario falla, el dispatcher rota
  a otro con `_try_fallback_providers` sin que el caller lo sepa.
- **Multi-tenant routing:** `get_default_provider(organization_id=...)`
  permite que cada tenant tenga su clave/proveedor sin que el código de negocio
  lo sepa.

**Coste.** Una sola línea de cambio en el dispatcher afecta a TODO el sistema.
Los tests en `tests/integration/test_ai_provider_chokepoint.py` deben pasar
antes de cualquier merge que toque este fichero.

## #79 — Map-Reduce LLM para documentos largos (no streaming)

**Decisión.** Documentos >8k tokens (meetings, contratos) usan
`map_reduce_analysis()` en `ai_chunk_service.py`: chunk → analyze each → reduce
to JSON. No usamos streaming ni context caching de Anthropic.

**Por qué.**
- Streaming complica el parsing JSON (necesitaríamos buffer + parser parcial).
- Context caching de Anthropic solo aplica si el system prompt es estable, no
  útil aquí porque el contenido cambia siempre.
- Map-Reduce es trivialmente paralelizable; cada chunk va a un thread.

**Cuándo reconsiderar.** Si la latencia user-perceived supera 30s en docs de
50+ páginas. Hoy es ~12s p95.

## #80 — Whisper STT solo OpenAI (no local) por defecto

**Decisión.** El endpoint `/ai-modules/voice/transcribe` usa Whisper de OpenAI
vía HTTP. El módulo de colaboración (`_transcription.py`) admite `WHISPER_LOCAL=1`
para whisper.cpp pero NO está activado por defecto.

**Por qué.**
- whisper.cpp local requiere ~2 GB RAM, no viable en plan SaaS.
- El precio de Whisper API (~$0.006/min) es marginal vs gpt-4o.
- gpt-4o-mini-transcribe (item #50) reduce coste y mejora calidad en
  audios cortos.

**Privacidad.** Para clientes con requisitos de no-cloud audio: activar
`WHISPER_LOCAL=1` + binario whisper.cpp pre-instalado.

## #81 — Modelo ML local (`GradientBoostingClassifier`) firmado con HMAC

**Decisión.** El modelo entrenado por `ml_trainer.py` se serializa con joblib,
se envuelve en un sobre con HMAC-SHA256 (clave: `ML_MODEL_HMAC_SECRET`), y se
persiste en `ai_ml_models` (BLOB en DB).

**Por qué.**
- Evita carga de pickle no firmado → mitigación de RCE si un atacante consigue
  insertar en la tabla.
- La firma se verifica antes de `joblib.load()`. Fallo → modelo rechazado.

**Limitación.** No protege contra adversarial inputs en runtime (poisoning de
features de entrenamiento). Eso requiere ML monitoring (no implementado).

## #82 — `EmbeddingsCache` en DB, no Redis

**Decisión.** `SemEmbeddingCache` (tabla SQL) guarda embedding + text_snippet
de cada ticket/task analizado, indexado por `assigned_user_id, item_type`.
No usamos Redis ni vector DB (pgvector, Pinecone, etc.).

**Por qué.**
- Mantiene el stack simple: solo Postgres + Python.
- Cardinality esperada: <100k embeddings/tenant × 384 dimensiones × 4 bytes
  ≈ 150 MB. Aceptable en Postgres.
- Búsqueda k-NN se hace en Python (numpy) sobre subset top-50 ordenado por
  `created_at DESC`. Suficiente con datasets <100k.

**Cuándo migrar.** Si un tenant supera 500k embeddings o p95 latencia
`/semantic-engine/suggest/ticket` >800 ms, considerar pgvector con índice
ivfflat.

## #83 — Cost profiles por usuario, no por proyecto

**Decisión.** `UserCostProfile` (item del último commit `metrics: add user cost
profiles`) modela el coste-hora REAL de un user (salario + impuestos +
overhead) por país via `CountryEmployerCost`. El coste de un proyecto se
calcula sumando `imputaciones × user_cost_profile.cost_per_hour`, no
`imputaciones × project.billing_rate`.

**Por qué.**
- `billing_rate` es la tarifa que se cobra al cliente (revenue).
- `cost_per_hour` es lo que cuesta INTERNAMENTE → margen real = revenue - cost.
- El margen por proyecto se vuelve calculable sin estimaciones grosso.

**Migración pendiente.** El AI Oracle (`run_oracle_analysis`) y `ml_features.py`
todavía usan el fallback `AI_REVENUE_HOURLY_RATE_FALLBACK` (85€/h) cuando no
hay `billing_rate`. Sería más exacto usar `user_cost_profile.cost_per_hour`
del owner del proyecto, pero el cambio toca 4 funciones y requiere tests de
regresión específicos. Tracked para Wave H.

---

**Última actualización:** 2026-05-12 — post Wave A→G (83 items).
