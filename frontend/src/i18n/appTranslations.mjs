
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


// ── Idiomas soportados: los tres que se venden ────────────────────────────────
// Auditoría 2026-08 (hallazgo 16). Antes había SIETE en el selector y ninguno
// estaba completo: el usuario veía interfaz mezclada castellano-inglés en
// cualquiera que eligiese. Medido entonces:
//
//   es  3756 claves (base)          en  62,2 %
//   fr / de / pt / it  44,2 %       pl / zh  62,2 % (ocultos con enabled:false)
//
// Mantener siete idiomas al 44-62 % era peor que ofrecer tres bien: un cliente
// internacional lo detecta en la demo. Se retiran fr, de, pt e it —que no se
// venden— y se conservan los tres que sí: castellano, inglés y chino.
//
// El chino estaba oculto con `enabled: false` pese a tener MÁS cobertura que los
// cuatro que sí se mostraban. Ahora está soportado de primera clase.
export const APP_LANGUAGES = [
	{ code: 'es', label: 'Español',    flag: '🇪🇸' },
	{ code: 'en', label: 'English',    flag: '🇬🇧' },
	{ code: 'zh', label: '中文',       flag: '🇨🇳' },
];

// Se conserva como export separado porque lo consumen los selectores de idioma y
// el editor de traducciones. Ya no filtra nada —los tres idiomas están
// soportados— pero se mantiene la indirección para no romper a sus llamadores.
export const AVAILABLE_LANGUAGES = APP_LANGUAGES.filter(l => l.enabled !== false);

// Carga dinámica de traducciones por idioma
const langFiles = {
	es: () => import('./langs/es.mjs'),
	en: () => import('./langs/en.mjs'),
	zh: () => import('./langs/zh.mjs'),
};

// ─── DEFINICIONES DE CONSTANTES DE IDIOMA ─────────────────────────────
// Copiado automáticamente desde appTranslations.js
import es from './langs/es.mjs';
import en from './langs/en.mjs';
import zh from './langs/zh.mjs';
import { deepMergeTranslations } from './translationRuntime.mjs';

export { es, en, zh };

export const APP_TRANSLATIONS = { es, en, zh };

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
