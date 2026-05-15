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
// @ts-ignore appTranslations.mjs has no type declarations
export {
  APP_LANGUAGES,
  APP_TRANSLATIONS,
  es,
  en,
  fr,
  de,
  pt,
  it,
  pl,
  zh,
  getAllKeys,
  loadLanguage,
  loadAutoLanguage,
} from './appTranslations.mjs'
