import { vi, describe, it, expect, afterEach } from 'vitest';
import { createContext } from 'react';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import LangSelector from '../components/LangSelector';
import { AppLangProvider } from '../i18n/AppLangContext';
import { AVAILABLE_LANGUAGES } from '../i18n/appTranslations';

// AppLangProvider needs useAuth, AuthContext (read via useContext) and api
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: null }),
  AuthContext: createContext({ user: null }),
}));

vi.mock('../services/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    patch: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

// Mock loadLanguage to avoid async i18n file loading in tests
// Vite resuelve '../i18n/appTranslations' al .mjs (registro) y el proveedor
// importa el .ts (cargador): se simulan los dos con el mismo módulo.
vi.mock('../i18n/appTranslations.ts', () => import('../i18n/appTranslations'));
vi.mock('../i18n/appTranslations', () => {
  const mod = {
    APP_LANGUAGES: [
      { code: 'es', label: 'Español',    flag: '🇪🇸' },
      { code: 'en', label: 'English',    flag: '🇬🇧' },
      { code: 'fr', label: 'Français',   flag: '🇫🇷', partial: true },
      { code: 'de', label: 'Deutsch',    flag: '🇩🇪', partial: true },
      { code: 'pt', label: 'Português',  flag: '🇵🇹', partial: true },
      { code: 'it', label: 'Italiano',   flag: '🇮🇹', partial: true },
      { code: 'pl', label: 'Polski',     flag: '🇵🇱', partial: true, enabled: false },
      { code: 'zh', label: '中文',       flag: '🇨🇳', partial: true, enabled: false },
    ],
    // Switcher shows only enabled locales (pl/zh excluded).
    AVAILABLE_LANGUAGES: [
      { code: 'es', label: 'Español',    flag: '🇪🇸' },
      { code: 'en', label: 'English',    flag: '🇬🇧' },
      { code: 'fr', label: 'Français',   flag: '🇫🇷', partial: true },
      { code: 'de', label: 'Deutsch',    flag: '🇩🇪', partial: true },
      { code: 'pt', label: 'Português',  flag: '🇵🇹', partial: true },
      { code: 'it', label: 'Italiano',   flag: '🇮🇹', partial: true },
    ],
    APP_TRANSLATIONS: {
      es: { nav: { projects: 'Proyectos' } },
      en: { nav: { projects: 'Projects' } },
      fr: { nav: { projects: 'Projects' } },
      de: { nav: { projects: 'Projects' } },
      pt: { nav: { projects: 'Projects' } },
      it: { nav: { projects: 'Projects' } },
      pl: { nav: { projects: 'Projects' } },
      zh: { nav: { projects: 'Projects' } },
    },
    loadLanguage: vi.fn().mockImplementation((code) =>
      Promise.resolve({ nav: { projects: code === 'es' ? 'Proyectos' : 'Projects' } })
    ),
  };
  // Lo que el proveedor lee ya cargado (#24a: los idiomas se cargan bajo demanda).
  const tr = mod.APP_TRANSLATIONS as Record<string, Record<string, Record<string, unknown>>>;
  return {
    ...mod,
    diccionarioCargado: (code: string) => tr[code] ?? tr.es,
    respaldoIngles: () => tr.en,
  };
});

describe('LangSelector', () => {
  afterEach(() => { cleanup(); });

  AVAILABLE_LANGUAGES.forEach(({ code, label }) => {
    it(`permite cambiar a ${label} (${code})`, async () => {
      render(
        <AppLangProvider>
          <LangSelector />
        </AppLangProvider>
      );
      // Use regex match (exact: false equivalent) because partial-language buttons
      // have a suffix in their aria-label (e.g. "Français — traducción parcial")
      const btn = await waitFor(() =>
        screen.getByRole('button', { name: new RegExp(label, 'i') })
      );
      fireEvent.click(btn);
      expect(btn).toBeTruthy();
    });
  });
});
