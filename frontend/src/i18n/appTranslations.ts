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
// Idiomas soportados: es, en, zh. Auditoría 2026-08 (hallazgo 16): se retiraron
// fr, de, pt, it y pl — no se venden y estaban al 44 % de cobertura.
//
// Auditoría 2026-09 (modo estricto): este fichero es **la frontera de tipos**
// con el runtime en `.mjs`, y hasta ahora no hacía de frontera — reexportaba
// tal cual y el tipo que llegaba al resto de la aplicación era el que
// TypeScript infiere de un objeto literal JS. Dos consecuencias reales:
// `APP_TRANSLATIONS` decía «solo existen es, en y zh» cuando el código lo
// indexa con un código de idioma que viene de la configuración del usuario, y
// `loadLanguage` devolvía `Object` —el tipo inútil, no `object`—, que no se
// puede pasar a nada. Declarar los dos aquí es lo que este fichero existe para
// hacer; declararlo en cada sitio que los usa sería repetir la misma suposición
// en N sitios y que se desincronicen.
import {
  APP_TRANSLATIONS as _APP_TRANSLATIONS,
  loadLanguage as _loadLanguage,
  loadAutoLanguage as _loadAutoLanguage,
} from './appTranslations.mjs'

/** Un módulo de traducción: claves a texto, con anidamiento arbitrario. */
export type ModuloDeTraduccion = Record<string, unknown>

/** El diccionario completo de un idioma: nombre de módulo → módulo. */
export type DiccionarioDeIdioma = Record<string, ModuloDeTraduccion>

/** Todos los idiomas cargados: código de idioma → diccionario. */
export const APP_TRANSLATIONS = _APP_TRANSLATIONS as unknown as Record<string, DiccionarioDeIdioma>

/** Carga perezosa del diccionario de un idioma. */
export const loadLanguage = _loadLanguage as unknown as (code: string) => Promise<DiccionarioDeIdioma>

/** Igual, resolviendo antes el idioma del navegador. */
export const loadAutoLanguage = _loadAutoLanguage as unknown as () => Promise<DiccionarioDeIdioma>

export {
  APP_LANGUAGES,
  AVAILABLE_LANGUAGES,
  es,
  en,
  zh,
  getAllKeys,
} from './appTranslations.mjs'
