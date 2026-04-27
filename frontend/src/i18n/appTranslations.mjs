
/**
 * Devuelve todas las claves planas con su módulo: [{module, key, base_es}]
 */
export function getAllKeys(obj = es) {
	const result = [];
	for (const [module, keys] of Object.entries(obj)) {
		for (const [key, value] of Object.entries(keys)) {
			result.push({ module, key, full_key: `${module}.${key}`, base_es: value });
		}
	}
	return result;
}
/**
 * Archivo migrado a .mjs para evitar problemas de análisis con Vite.
 * No editar appTranslations.js, solo este archivo.
 */

// Copiado automáticamente desde appTranslations.js


// partial: true → translation is incomplete; UI shows a β badge and
// loadLanguage will fill missing keys with English as fallback.
export const APP_LANGUAGES = [
	{ code: 'es', label: 'Español',    flag: '🇪🇸' },
	{ code: 'en', label: 'English',    flag: '🇬🇧' },
	{ code: 'fr', label: 'Français',   flag: '🇫🇷', partial: true },
	{ code: 'de', label: 'Deutsch',    flag: '🇩🇪', partial: true },
	{ code: 'pt', label: 'Português',  flag: '🇵🇹', partial: true },
	{ code: 'it', label: 'Italiano',   flag: '🇮🇹', partial: true },
	{ code: 'pl', label: 'Polski',     flag: '🇵🇱', partial: true },
	{ code: 'zh', label: '中文',       flag: '🇨🇳', partial: true },
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
import { deepMergeTranslations } from './translationRuntime.mjs';

export { es, en, fr, de, pt, it, pl, zh };

export const APP_TRANSLATIONS = { es, en, fr, de, pt, it, pl, zh };

/**
 * Deep merge by namespace and nested keys.
 * Keys present in base but absent in override keep their fallback value.
 */
function mergeWithFallback(base, override) {
	return deepMergeTranslations(base || {}, override || {});
}

/**
 * Carga automática del idioma detectado o forzado.
 * For partial languages (everything except 'en') English is used as the base
 * so missing keys always show English text rather than raw key names.
 * @param {string} lang Código de idioma (es, en, ...)
 * @returns {Promise<Object>} Objeto de traducciones
 */
export async function loadLanguage(lang) {
	if (!langFiles[lang]) lang = 'es';
	try {
		const [targetMod, enMod] = await Promise.all([
			langFiles[lang](),
			lang !== 'en' ? langFiles['en']() : Promise.resolve(null),
		]);
		const target = targetMod.default;
		if (!enMod) return target; // 'en' needs no fallback
		return mergeWithFallback(enMod.default, target);
	} catch {
		// Fallback a inglés si el fichero del idioma falla
		const mod = await langFiles['en']();
		return mod.default;
	}
}

/**
 * Carga automática según el idioma del navegador, con fallback a español.
 * @returns {Promise<Object>} Objeto de traducciones
 */
export async function loadAutoLanguage() {
	const navLang = (globalThis.navigator?.language || 'es').slice(0,2);
	return await loadLanguage(navLang);
}
