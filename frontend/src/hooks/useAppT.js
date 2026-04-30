import { useContext, useMemo } from 'react';
import { AppLangContext } from '../i18n/AppLangContext';
import { resolveTranslation } from '../i18n/translationRuntime.mjs';

const NOOP = () => {};
const EMPTY_OBJ = {};

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
  const setLang = ctx?.setLang || NOOP;
  const loading = ctx?.loading || false;
  const translations = ctx?.translations || EMPTY_OBJ;
  const setCustomTranslations = ctx?.setCustomTranslations || NOOP;

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
      let module, keyPath = [], params;
      // Soporta t('mod.key', { ... }) o t('mod', 'key', { ... })
      if (typeof keyOrParams === 'object' && keyOrParams !== null && !Array.isArray(keyOrParams)) {
        // t('mod.key', { ... })
        params = keyOrParams;
        if (moduleOrFullKey.includes('.')) {
          const parts = moduleOrFullKey.split('.');
          module = parts[0];
          keyPath = parts.slice(1);
        } else {
          return moduleOrFullKey;
        }
      } else if (typeof maybeParams === 'object' && maybeParams !== null && !Array.isArray(maybeParams)) {
        // t('mod', 'key', { ... })
        module = moduleOrFullKey;
        keyPath = String(keyOrParams).split('.');
        params = maybeParams;
      } else {
        // t('mod.key') o t('mod', 'key')
        if (keyOrParams) {
          module = moduleOrFullKey;
          keyPath = String(keyOrParams).split('.');
        } else if (moduleOrFullKey.includes('.')) {
          const parts = moduleOrFullKey.split('.');
          module = parts[0];
          keyPath = parts.slice(1);
        } else {
          return moduleOrFullKey;
        }
        params = {};
      }

      // Permite forzar idioma por llamada
      const dict = ctx?.translations || {};
      let trans = resolveTranslation({
        lang,
        moduleName: module,
        keyPath,
        runtimeTranslations: dict,
        baseTranslations: ctx?.baseTranslations || {},
        englishTranslations: ctx?.allTranslations?.en || {},
        spanishTranslations: ctx?.allTranslations?.es || {},
      });

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
