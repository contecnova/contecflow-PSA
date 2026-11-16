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
