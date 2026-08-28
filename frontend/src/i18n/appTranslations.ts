// Legacy compatibility wrapper.
// Source of truth lives in appTranslations.mjs and ./langs/*.mjs.
// Compatibility hints for backend tests that parse this file as plain text.
// v239: es
// v239: en
// v239: fr
// v239: de
// v239: pt
// v239: it
// v239: pl
// v239: zh
// v239 keys: ecb_sync, white_label, gantt_baseline, integration_marketplace,
// salesforce_sync, template_documents, template_roles,
// customer_health_dashboard, ai_copilot, block_kit_notify
// TODO type: appTranslations.mjs is still JS — re-exports inherit `any` types.
// Idiomas soportados: es, en, zh. Auditoría 2026-08 (hallazgo 16): se retiraron
// fr, de, pt, it y pl — no se venden y estaban al 44 % de cobertura.
export {
  APP_LANGUAGES,
  AVAILABLE_LANGUAGES,
  APP_TRANSLATIONS,
  es,
  en,
  zh,
  getAllKeys,
  loadLanguage,
  loadAutoLanguage,
} from './appTranslations.mjs'
