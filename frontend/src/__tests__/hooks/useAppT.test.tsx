// Pilot test for the useAppT translation hook — audit #47.
// Verifies the basic translation contract exposed to ~all UI components:
//   • returns a callable t()
//   • t() falls back gracefully on missing keys
//   • t() honors a per-call lang override (does not crash)
//   • t() interpolates {var} placeholders
//
// We wrap with AppLangContext.Provider directly (instead of the real
// AppLangProvider) to keep this test hermetic — no async dictionary loads,
// no localStorage / navigator dependencies.
import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { AppLangContext } from '../../i18n/AppLangContext';
import { useAppT } from '../../hooks/useAppT';

const mockTranslations = {
  greetings: {
    hello: 'Hola',
    welcome: 'Bienvenido, {name}!',
  },
};

function makeWrapper(value: React.ContextType<typeof AppLangContext>) {
  return function Wrapper({ children }: { children?: React.ReactNode }) {
    return (
      <AppLangContext.Provider value={value}>{children}</AppLangContext.Provider>
    );
  };
}

// El contexto tiene nueve campos; el doble los da todos aunque `useAppT` hoy
// solo lea algunos. Un doble incompleto es una suposicion sobre la
// implementacion escondida dentro del test.
const baseCtx: React.ContextType<typeof AppLangContext> = {
  lang: 'es',
  setLang: vi.fn(),
  t: (clave: string) => clave,
  loading: false,
  translations: mockTranslations,
  baseTranslations: mockTranslations,
  allTranslations: { es: mockTranslations, en: mockTranslations },
  customTrans: {},
  setCustomTranslations: vi.fn(),
};

describe('useAppT', () => {
  it('returns a t function', () => {
    const { result } = renderHook(() => useAppT(), { wrapper: makeWrapper(baseCtx) });
    expect(typeof result.current.t).toBe('function');
  });

  it('t("nonexistent.key") returns a graceful fallback (never undefined)', () => {
    const { result } = renderHook(() => useAppT(), { wrapper: makeWrapper(baseCtx) });
    const out = result.current.t('nonexistent.key');
    // Implementation humanizes the last path segment when no dict entry
    // exists. The contract guarantee we lock in: it is a non-empty string,
    // never undefined, and never throws.
    expect(typeof out).toBe('string');
    expect(out.length).toBeGreaterThan(0);
  });

  it('t("key", { lang: "es" }) does not crash and returns a string', () => {
    // The hook accepts a per-call lang override in the params object;
    // we just verify it is honored (i.e. accepted without throwing) and
    // still produces a string for an existing key.
    const { result } = renderHook(() => useAppT(), { wrapper: makeWrapper(baseCtx) });
    const out = result.current.t('greetings.hello', { lang: 'es' });
    expect(typeof out).toBe('string');
    expect(out.length).toBeGreaterThan(0);
  });

  it('t("key", { var: "X" }) interpolates {var} placeholders', () => {
    const { result } = renderHook(() => useAppT(), { wrapper: makeWrapper(baseCtx) });
    expect(result.current.t('greetings.welcome', { name: 'Oriol' }))
      .toBe('Bienvenido, Oriol!');
  });
});
