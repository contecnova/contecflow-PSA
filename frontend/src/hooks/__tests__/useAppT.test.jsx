import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { AppLangContext } from '../../i18n/AppLangContext';
import { useAppT } from '../useAppT';
import React from 'react';

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
  function wrapper({ children }) {
    return (
      <AppLangContext.Provider value={{
        lang: 'es',
        setLang: vi.fn(),
        loading: false,
        translations: mockTranslations,
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

  it('permite fallback a clave si falta traducción', () => {
    const { result } = renderHook(() => useAppT(), { wrapper });
    expect(result.current.t('dashboard.unknown')).toBe('unknown');
  });

  it('permite forzar idioma (simulado)', () => {
    const { result } = renderHook(() => useAppT(), { wrapper });
    // No cambia traducción porque mockTranslations solo tiene 'es', pero testea la API
    expect(result.current.t('dashboard.title', { lang: 'en' })).toBe('Tablero');
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
