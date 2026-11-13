// Solo para scripts de Node (check_i18n*, i18n_gap...): los tres diccionarios
// cargados a la vez. La aplicación NO debe importar este fichero: metería en el
// chunk inicial los idiomas que appTranslations.mjs carga bajo demanda.
import es from './langs/es.mjs';
import en from './langs/en.mjs';
import zh from './langs/zh.mjs';

export { APP_LANGUAGES, AVAILABLE_LANGUAGES, getAllKeys } from './appTranslations.mjs';
export { es, en, zh };
export const APP_TRANSLATIONS = { es, en, zh };
