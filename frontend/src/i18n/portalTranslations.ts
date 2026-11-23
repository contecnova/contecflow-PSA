// portalTranslations.ts — thin aggregator. Source of truth lives in ./portal/*.ts
import es from './portal/es'
import en from './portal/en'
import fr from './portal/fr'
import de from './portal/de'
import pt from './portal/pt'
import it from './portal/it'
import pl from './portal/pl'
import zh from './portal/zh'

export type PortalLangCode = 'es' | 'en' | 'fr' | 'de' | 'pt' | 'it' | 'pl' | 'zh'

export interface PortalLanguage {
  code: PortalLangCode
  /** Nombre del idioma en ese idioma. Sin banderas: un idioma no es un país (16-11-2026). */
  label: string
}

export type PortalDictionary = Record<string, string>
export type PortalTranslationsMap = Record<PortalLangCode, PortalDictionary>

/**
 * Idioma que se MUESTRA cuando no hay preferencia del usuario, ni de la
 * empresa, ni un idioma del navegador que se ofrezca: inglés (incidencia 5 de
 * usuarios, 23-11-2026). El castellano sigue siendo el idioma FUENTE de los
 * textos (`IDIOMA_FUENTE`: último respaldo de una clave sin traducir).
 */
export const IDIOMA_POR_DEFECTO: PortalLangCode = 'en'
/** Idioma en el que se escriben los textos y último respaldo de una clave. */
export const IDIOMA_FUENTE: PortalLangCode = 'es'

export const PORTAL_LANGUAGES: PortalLanguage[] = [
  { code: 'es', label: 'Español' },
  { code: 'en', label: 'English' },
  { code: 'fr', label: 'Français' },
  { code: 'de', label: 'Deutsch' },
  { code: 'pt', label: 'Português' },
  { code: 'it', label: 'Italiano' },
  { code: 'pl', label: 'Polski' },
  { code: 'zh', label: '中文' },
]

// Compatibilidad con código antiguo
export const LANGUAGES: PortalLanguage[] = PORTAL_LANGUAGES

/** `true` si el código es uno de los 8 idiomas del portal. */
export function esIdiomaDelPortal(code: string | null | undefined): code is PortalLangCode {
  return !!code && PORTAL_LANGUAGES.some(l => l.code === code)
}

/**
 * Idioma inicial del portal (incidencia 5): el de la URL (`?lang=`, enlaces de
 * correo), el último resuelto en este navegador (preferencia del usuario o de
 * su empresa, que llega al entrar), el del navegador si es uno de los 8 y, si
 * no, inglés.
 */
export function idiomaInicialDelPortal(): PortalLangCode {
  try {
    const deLaUrl = new URLSearchParams(globalThis.location?.search ?? '').get('lang')
    if (esIdiomaDelPortal(deLaUrl)) return deLaUrl
  } catch { /* sin URL (tests) */ }
  try {
    const ficha = JSON.parse(globalThis.localStorage?.getItem('client_user') || 'null') as { language?: string } | null
    if (esIdiomaDelPortal(ficha?.language)) return ficha.language
    const guardado = globalThis.localStorage?.getItem('portal_lang')
    if (esIdiomaDelPortal(guardado)) return guardado
  } catch { /* accesorio: almacenamiento bloqueado o dato corrupto */ }
  const navegador = globalThis.navigator
  for (const l of [...(navegador?.languages ?? []), navegador?.language]) {
    const code = (l || '').slice(0, 2).toLowerCase()
    if (esIdiomaDelPortal(code)) return code
  }
  return IDIOMA_POR_DEFECTO
}

export const PORTAL_TRANSLATIONS: PortalTranslationsMap = { es, en, fr, de, pt, it, pl, zh }

// Compatibilidad con código antiguo
export const T: PortalTranslationsMap = PORTAL_TRANSLATIONS

export interface PortalKeyEntry {
  key: string
  base_es: string
}

/** Obtener todas las claves con su valor ES base */
export function getPortalKeys(): PortalKeyEntry[] {
  return Object.entries(es).map(([key, base_es]) => ({ key, base_es }))
}

export default PORTAL_TRANSLATIONS
