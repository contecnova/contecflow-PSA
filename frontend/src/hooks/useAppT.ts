import { useContext, useMemo } from 'react';
import { AppLangContext } from '../i18n/AppLangContext';
// @ts-expect-error — translationRuntime es un .mjs sin tipos (migración gradual #115)
import { resolveTranslation } from '../i18n/translationRuntime.mjs';

const NOOP = () => {};
const EMPTY_OBJ: Record<string, unknown> = {};

export type TranslationParams = Record<string, string | number | boolean | null | undefined>;

export type TFunction = (
  moduleOrFullKey: string,
  keyOrParams?: string | TranslationParams,
  maybeParams?: TranslationParams,
) => string;

export interface AppT {
  t: TFunction;
  lang: string;
  setLang: (lang: string) => void;
  loading: boolean;
  translations: Record<string, unknown>;
  setCustomTranslations: (translations: Record<string, unknown>) => void;
}

interface AppLangContextValue {
  lang?: string;
  setLang?: (lang: string) => void;
  loading?: boolean;
  translations?: Record<string, unknown>;
  setCustomTranslations?: (translations: Record<string, unknown>) => void;
  baseTranslations?: Record<string, unknown>;
  allTranslations?: { en?: Record<string, unknown>; es?: Record<string, unknown>; [k: string]: unknown };
}

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
export function useAppT(): AppT {
  const ctx = useContext(AppLangContext) as AppLangContextValue | null;
  // Fallbacks seguros
  const lang = ctx?.lang || 'es';
  const setLang = ctx?.setLang || NOOP;
  const loading = ctx?.loading || false;
  const translations = ctx?.translations || EMPTY_OBJ;
  const setCustomTranslations = ctx?.setCustomTranslations || NOOP;

  // Traducción robusta con interpolación y fallback
  const t = useMemo<TFunction>(() => {
    /**
     * Traduce una clave con soporte para:
     * - t('mod.key')
     * - t('mod', 'key')
     * - t('mod.key', { var1, lang })
     * - t('mod', 'key', { var1, lang })
     */
    return function translate(moduleOrFullKey, keyOrParams, maybeParams) {
      let moduleName: string;
      let keyPath: string[] = [];
      let params: TranslationParams;
      // Soporta t('mod.key', { ... }) o t('mod', 'key', { ... })
      if (typeof keyOrParams === 'object' && keyOrParams !== null && !Array.isArray(keyOrParams)) {
        // t('mod.key', { ... })
        params = keyOrParams as TranslationParams;
        if (moduleOrFullKey.includes('.')) {
          const parts = moduleOrFullKey.split('.');
          moduleName = parts[0];
          keyPath = parts.slice(1);
        } else {
          return moduleOrFullKey;
        }
      } else if (typeof maybeParams === 'object' && maybeParams !== null && !Array.isArray(maybeParams)) {
        // t('mod', 'key', { ... })
        moduleName = moduleOrFullKey;
        keyPath = String(keyOrParams).split('.');
        params = maybeParams;
      } else {
        // t('mod.key') o t('mod', 'key')
        if (keyOrParams) {
          moduleName = moduleOrFullKey;
          keyPath = String(keyOrParams).split('.');
        } else if (moduleOrFullKey.includes('.')) {
          const parts = moduleOrFullKey.split('.');
          moduleName = parts[0];
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
        moduleName,
        keyPath,
        runtimeTranslations: dict,
        baseTranslations: ctx?.baseTranslations || {},
        englishTranslations: ctx?.allTranslations?.en || {},
        spanishTranslations: ctx?.allTranslations?.es || {},
      });

      // Interpolación de variables: {var}
      if (params && typeof trans === 'string') {
        trans = trans.replace(/\{(\w+)\}/g, (_: string, name: string) =>
          params[name] !== undefined ? String(params[name]) : `{${name}}`,
        );
      }
      return trans as string;
    };
  }, [ctx, lang]);

  return useMemo<AppT>(() => ({
    t,
    lang,
    setLang: setLang as (lang: string) => void,
    loading,
    translations: translations as Record<string, unknown>,
    setCustomTranslations: setCustomTranslations as (translations: Record<string, unknown>) => void,
  }), [t, lang, setLang, loading, translations, setCustomTranslations]);
}
