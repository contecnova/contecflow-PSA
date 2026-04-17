
// Stub for getAllKeys to avoid import error
export function getAllKeys() {
	return [];
}
/**
 * Archivo migrado a .mjs para evitar problemas de análisis con Vite.
 * No editar appTranslations.js, solo este archivo.
 */

// Copiado automáticamente desde appTranslations.js


export const APP_LANGUAGES = [
	{ code: 'es', label: 'Español',    flag: '🇪🇸' },
	{ code: 'en', label: 'English',    flag: '🇬🇧' },
	{ code: 'fr', label: 'Français',   flag: '🇫🇷' },
	{ code: 'de', label: 'Deutsch',    flag: '🇩🇪' },
	{ code: 'pt', label: 'Português',  flag: '🇵🇹' },
	{ code: 'it', label: 'Italiano',   flag: '🇮🇹' },
	{ code: 'pl', label: 'Polski',     flag: '🇵🇱' },
	{ code: 'zh', label: '中文',       flag: '🇨🇳' },
];

// Carga dinámica de traducciones por idioma
const langFiles = {
	es: () => import('./langs/es.mjs'),
	en: () => import('./langs/en.mjs'),
	fr: () => import('./langs/fr.mjs'),
	de: () => import('./langs/de.mjs'),
	pt: () => import('./langs/pt.mjs'),
	it: () => import('./langs/it.mjs'),
	pl: () => import('./langs/pl.mjs'),
	zh: () => import('./langs/zh.mjs'),
};

// ─── DEFINICIONES DE CONSTANTES DE IDIOMA ─────────────────────────────
// Copiado automáticamente desde appTranslations.js
import es from './langs/es.mjs';
import en from './langs/en.mjs';
import fr from './langs/fr.mjs';
import de from './langs/de.mjs';
import pt from './langs/pt.mjs';
import it from './langs/it.mjs';
import pl from './langs/pl.mjs';
import zh from './langs/zh.mjs';

export { es, en, fr, de, pt, it, pl, zh };

export const APP_TRANSLATIONS = { es, en, fr, de, pt, it, pl, zh };

/**
 * Carga automática del idioma detectado o forzado.
 * @param {string} lang Código de idioma (es, en, ...)
 * @returns {Promise<Object>} Objeto de traducciones
 */
export async function loadLanguage(lang) {
	if (!langFiles[lang]) lang = 'es';
	try {
		const mod = await langFiles[lang]();
		return mod.default;
	} catch (e) {
		// Fallback a español si falla
		const mod = await langFiles['es']();
		return mod.default;
	}
}

/**
 * Carga automática según el idioma del navegador, con fallback a español.
 * @returns {Promise<Object>} Objeto de traducciones
 */
export async function loadAutoLanguage() {
	const navLang = (navigator.language || 'es').slice(0,2);
	return await loadLanguage(navLang);
}
