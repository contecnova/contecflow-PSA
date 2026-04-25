// portalTranslations.js — thin aggregator. Source of truth lives in ./portal/*.js
import es from './portal/es.js'
import en from './portal/en.js'
import fr from './portal/fr.js'
import de from './portal/de.js'
import pt from './portal/pt.js'
import it from './portal/it.js'
import pl from './portal/pl.js'
import zh from './portal/zh.js'

export const PORTAL_LANGUAGES = [
  { code: 'es', label: 'Español',   flag: '🇪🇸' },
  { code: 'en', label: 'English',   flag: '🇬🇧' },
  { code: 'fr', label: 'Français',  flag: '🇫🇷' },
  { code: 'de', label: 'Deutsch',   flag: '🇩🇪' },
  { code: 'pt', label: 'Português', flag: '🇵🇹' },
  { code: 'it', label: 'Italiano',  flag: '🇮🇹' },
  { code: 'pl', label: 'Polski',    flag: '🇵🇱' },
  { code: 'zh', label: '中文',      flag: '🇨🇳' },
]

// Compatibilidad con código antiguo
export const LANGUAGES = PORTAL_LANGUAGES

export const PORTAL_TRANSLATIONS = { es, en, fr, de, pt, it, pl, zh }

// Compatibilidad con código antiguo
export const T = PORTAL_TRANSLATIONS

/** Obtener todas las claves con su valor ES base */
export function getPortalKeys() {
  return Object.entries(es).map(([key, base_es]) => ({ key, base_es }))
}

export default PORTAL_TRANSLATIONS
