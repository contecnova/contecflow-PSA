import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { AppLangContext } from '../../i18n/AppLangContext';
import { useAppT } from '../useAppT';

const mockTranslations = {
  dashboard: {
    title: 'Tablero',
    welcome: 'Bienvenido, {name}!'
  },
  common: {
    save: 'Guardar',
    cancel: 'Cancelar'
  }
};

describe('useAppT (enterprise)', () => {
  function wrapper({ children }: { children?: React.ReactNode }) {
    return (
      <AppLangContext.Provider value={{
        // El contexto tiene nueve campos; el doble los da todos aunque
        // `useAppT` hoy solo lea algunos. Un doble incompleto es una
        // suposicion sobre la implementacion escondida en el test.
        lang: 'es',
        setLang: vi.fn(),
        t: (clave: string) => clave,
        loading: false,
        translations: mockTranslations,
        baseTranslations: mockTranslations,
        allTranslations: { es: mockTranslations },
        customTrans: {},
        setCustomTranslations: vi.fn()
      }}>
        {children}
      </AppLangContext.Provider>
    );
  }

  it('traduce claves simples', () => {
    const { result } = renderHook(() => useAppT(), { wrapper });
    expect(result.current.t('dashboard.title')).toBe('Tablero');
    expect(result.current.t('common.save')).toBe('Guardar');
  });

  it('interpolates variables', () => {
    const { result } = renderHook(() => useAppT(), { wrapper });
    expect(result.current.t('dashboard.welcome', { name: 'Juan' })).toBe('Bienvenido, Juan!');
  });

  it('humaniza fallback cuando falta traducción', () => {
    const { result } = renderHook(() => useAppT(), { wrapper });
    expect(result.current.t('dashboard.unknown')).toBe('Unknown');
  });

  it('permite forzar idioma (simulado)', () => {
    const { result } = renderHook(() => useAppT(), { wrapper });
    // No cambia traducción porque mockTranslations solo tiene 'es', pero testea la API
    expect(result.current.t('dashboard.title', { lang: 'en' })).toBe('Tablero');
  });

  it('usa fallback en/es antes de humanizar', () => {
    function wrapperWithFallback({ children }: { children?: React.ReactNode }) {
      return (
        <AppLangContext.Provider value={{
          lang: 'fr',
          setLang: vi.fn(),
          t: (clave: string) => clave,
          customTrans: {},
          loading: false,
          translations: { dashboard: {} },
          baseTranslations: { dashboard: { title: 'Dashboard' } },
          allTranslations: {
            en: { dashboard: { title: 'Dashboard' } },
            es: { dashboard: { title: 'Tablero' } },
          },
          setCustomTranslations: vi.fn()
        }}>
          {children}
        </AppLangContext.Provider>
      );
    }

    const { result } = renderHook(() => useAppT(), { wrapper: wrapperWithFallback });
    expect(result.current.t('dashboard.title')).toBe('Dashboard');
  });

  it('expone helpers', () => {
    const { result } = renderHook(() => useAppT(), { wrapper });
    expect(result.current.lang).toBe('es');
    expect(typeof result.current.setLang).toBe('function');
    expect(result.current.loading).toBe(false);
    expect(result.current.translations).toBe(mockTranslations);
    expect(typeof result.current.setCustomTranslations).toBe('function');
  });
});
