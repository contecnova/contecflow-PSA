import { useContext, useMemo } from 'react';
import { AppLangContext } from '../i18n/AppLangContext';

/**
 * useAppT — Hook de traducción empresarial
 * - Traducción con interpolación de variables
 * - Permite forzar idioma por llamada
 * - Fallback robusto
 * - Expone helpers: idioma actual, cambiar idioma, loading, traducciones custom
 * - Memoización para rendimiento
 *
 * Uso:
 *   const { t, lang, setLang, loading, translations, setCustomTranslations } = useAppT();
 *   t('dashboard.title')
 *   t('dashboard.title', { lang: 'en' })
 *   t('dashboard.title', { name: 'Juan', lang: 'es' })
 */
export function useAppT() {
  const ctx = useContext(AppLangContext);
  // Fallbacks seguros
  const lang = ctx?.lang || 'es';
  const setLang = ctx?.setLang || (() => {});
  const loading = ctx?.loading || false;
  const translations = ctx?.translations || {};
  const setCustomTranslations = ctx?.setCustomTranslations || (() => {});

  // Traducción robusta con interpolación y fallback
  const t = useMemo(() => {
    /**
     * Traduce una clave con soporte para:
     * - t('mod.key')
     * - t('mod', 'key')
     * - t('mod.key', { var1, lang })
     * - t('mod', 'key', { var1, lang })
     */
    return function translate(moduleOrFullKey, keyOrParams, maybeParams) {
      let module, realKey, params;
      // Soporta t('mod.key', { ... }) o t('mod', 'key', { ... })
      if (typeof keyOrParams === 'object' && keyOrParams !== null && !Array.isArray(keyOrParams)) {
        // t('mod.key', { ... })
        params = keyOrParams;
        if (moduleOrFullKey.includes('.')) {
          [module, realKey] = moduleOrFullKey.split('.', 2);
        } else {
          return moduleOrFullKey;
        }
      } else if (typeof maybeParams === 'object' && maybeParams !== null && !Array.isArray(maybeParams)) {
        // t('mod', 'key', { ... })
        module = moduleOrFullKey;
        realKey = keyOrParams;
        params = maybeParams;
      } else {
        // t('mod.key') o t('mod', 'key')
        if (keyOrParams) {
          module = moduleOrFullKey;
          realKey = keyOrParams;
        } else if (moduleOrFullKey.includes('.')) {
          [module, realKey] = moduleOrFullKey.split('.', 2);
        } else {
          return moduleOrFullKey;
        }
        params = {};
      }

      // Permite forzar idioma por llamada
      const forcedLang = params.lang || lang;
      const dict = ctx?.translations || {};
      let trans = dict?.[module]?.[realKey];
      if (!trans) trans = realKey; // fallback clave

      // Interpolación de variables: {var}
      if (params && typeof trans === 'string') {
        trans = trans.replace(/\{(\w+)\}/g, (_, name) =>
          params[name] !== undefined ? params[name] : `{${name}}`
        );
      }
      return trans;
    };
  }, [ctx, lang]);

  return useMemo(() => ({
    t,
    lang,
    setLang,
    loading,
    translations,
    setCustomTranslations,
  }), [t, lang, setLang, loading, translations, setCustomTranslations]);
}
