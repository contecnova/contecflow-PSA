
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

// ── Carga de idiomas (auditoría 2026-11, #24a) ────────────────────────────────
// Antes se importaban los tres diccionarios de forma estática (~1 MB de fuente)
// y acababan los tres en el chunk inicial aunque el usuario solo usa uno. Ahora
// solo el castellano —idioma por defecto y último respaldo— va en el chunk
// inicial; inglés y chino se piden con import() cuando hacen falta. El registro
// de lo ya cargado, la mezcla con el respaldo y la carga viven en
// appTranslations.ts (solo navegador). Los scripts de Node que necesitan los
// tres idiomas a la vez importan ./todosLosIdiomas.mjs.
import es from './langs/es.mjs';

export { es };

/** Cargadores de los idiomas que no van en el chunk inicial. */
export const CARGADORES_DE_IDIOMA = {
	en: () => import('./langs/en.mjs'),
	zh: () => import('./langs/zh.mjs'),
};
