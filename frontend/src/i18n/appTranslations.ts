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
//
// Auditoría 2026-11 (#24a): además es el **cargador**. Solo el castellano va en
// el chunk inicial; inglés y chino se piden con import() la primera vez que se
// usan y quedan registrados en `APP_TRANSLATIONS`. Para que el castellano siga
// resolviendo sus claves sin traducir con el inglés —como antes— sin descargar
// el inglés entero, se usa `virtual:i18n-respaldo-en` (ver vite.config.js).
// Ojo: Vite resuelve `./appTranslations` sin extensión al .mjs; quien quiera
// este cargador importa `./appTranslations.ts` con la extensión.
import {
  APP_LANGUAGES,
  AVAILABLE_LANGUAGES,
  CARGADORES_DE_IDIOMA,
  es as _es,
  getAllKeys as _getAllKeys,
} from './appTranslations.mjs'
import RESPALDO_EN from 'virtual:i18n-respaldo-en'
import { deepMergeTranslations } from './translationRuntime.mjs'

/** Un módulo de traducción: claves a texto, con anidamiento arbitrario. */
export type ModuloDeTraduccion = Record<string, unknown>

/** El diccionario completo de un idioma: nombre de módulo → módulo. */
export type DiccionarioDeIdioma = Record<string, ModuloDeTraduccion>

export const es = _es as DiccionarioDeIdioma

/**
 * Diccionarios crudos ya cargados: código de idioma → diccionario. Empieza
 * solo con el castellano y crece con cada idioma que se carga.
 */
export const APP_TRANSLATIONS: Record<string, DiccionarioDeIdioma> = { es }

const CODIGOS: readonly string[] = APP_LANGUAGES.map((l) => l.code)
const cargadores = CARGADORES_DE_IDIOMA as Record<string, () => Promise<{ default: unknown }>>
const mezclados = new Map<string, DiccionarioDeIdioma>()

/** El código si se ofrece; si no, castellano. */
export function idiomaSoportado(code: string | null | undefined): string {
  return code && CODIGOS.includes(code) ? code : 'es'
}

/**
 * Respaldo inglés para resolver claves: el diccionario inglés si ya se cargó;
 * si no, solo las entradas que le faltan al castellano.
 */
export function respaldoIngles(): DiccionarioDeIdioma {
  return APP_TRANSLATIONS.en ?? RESPALDO_EN
}

/**
 * Diccionario de un idioma ya mezclado con el respaldo inglés, sin esperar:
 * `undefined` si aún no se ha cargado. El castellano está siempre.
 */
export function diccionarioCargado(code: string): DiccionarioDeIdioma | undefined {
  const lang = idiomaSoportado(code)
  const hecho = mezclados.get(lang)
  if (hecho) return hecho
  const propio = APP_TRANSLATIONS[lang]
  if (!propio) return undefined
  let resultado: DiccionarioDeIdioma
  if (lang === 'en') resultado = propio
  else if (lang === 'es') resultado = deepMergeTranslations(respaldoIngles(), propio) as DiccionarioDeIdioma
  else if (APP_TRANSLATIONS.en) resultado = deepMergeTranslations(APP_TRANSLATIONS.en, propio) as DiccionarioDeIdioma
  else return undefined
  mezclados.set(lang, resultado)
  return resultado
}

async function registrar(lang: string): Promise<void> {
  if (APP_TRANSLATIONS[lang]) return
  const mod = await cargadores[lang]()
  APP_TRANSLATIONS[lang] = mod.default as DiccionarioDeIdioma
  // El castellano se mezcló con el respaldo parcial; con el inglés entero se rehace.
  if (lang === 'en') mezclados.delete('es')
}

/**
 * Carga (si hace falta) el idioma y su respaldo inglés y devuelve el
 * diccionario mezclado. Si la descarga falla, castellano.
 */
export async function loadLanguage(code: string): Promise<DiccionarioDeIdioma> {
  const lang = idiomaSoportado(code)
  try {
    await Promise.all(lang === 'es' ? [] : [registrar(lang), registrar('en')])
    return diccionarioCargado(lang) ?? (diccionarioCargado('es') as DiccionarioDeIdioma)
  } catch {
    return diccionarioCargado('es') as DiccionarioDeIdioma
  }
}

/** Igual, resolviendo antes el idioma del navegador. */
export function loadAutoLanguage(): Promise<DiccionarioDeIdioma> {
  return loadLanguage((globalThis.navigator?.language || 'es').slice(0, 2))
}

/** Claves planas de un diccionario (por defecto, el castellano). */
export const getAllKeys = _getAllKeys as (obj?: DiccionarioDeIdioma) => Array<{ module: string; key: string; full_key: string; base_es: string }>

export { APP_LANGUAGES, AVAILABLE_LANGUAGES }
