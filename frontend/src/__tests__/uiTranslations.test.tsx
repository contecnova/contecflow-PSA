/**
 * uiTranslations.test.jsx
 * Tests that AppLangProvider correctly loads translations and responds to language changes.
 * Renders a minimal test UI instead of the full App to avoid authentication/routing dependencies.
 */
import { vi, describe, it, expect, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { AppLangProvider, useAppLang } from '../i18n/AppLangContext';
import React from 'react';

// AppLangProvider hace `useContext(AuthContext)` (no solo useAuth): el mock debe
// exportar un Context real para que useContext no falle.
vi.mock('../context/AuthContext', async () => {
  const { createContext } = await vi.importActual<typeof import('react')>('react');
  return {
    useAuth: () => ({ user: null }),
    AuthContext: createContext<{ user: null } | null>({ user: null }),
  };
});

vi.mock('../services/api', () => ({
  default: {
    patch: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

// Mock loadLanguage so tests don't depend on actual translation files
vi.mock('../i18n/appTranslations', () => ({
  APP_LANGUAGES: [
    { code: 'es', label: 'Español',    flag: '🇪🇸' },
    { code: 'en', label: 'English',    flag: '🇬🇧' },
    { code: 'fr', label: 'Français',   flag: '🇫🇷', partial: true },
    { code: 'de', label: 'Deutsch',    flag: '🇩🇪', partial: true },
    { code: 'pt', label: 'Português',  flag: '🇵🇹', partial: true },
    { code: 'it', label: 'Italiano',   flag: '🇮🇹', partial: true },
    { code: 'pl', label: 'Polski',     flag: '🇵🇱', partial: true },
    { code: 'zh', label: '中文',       flag: '🇨🇳', partial: true },
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
}));

const LANGUAGES = [
  { code: 'es', label: 'Español' },
  { code: 'en', label: 'English' },
  { code: 'fr', label: 'Français' },
  { code: 'de', label: 'Deutsch' },
  { code: 'pt', label: 'Português' },
  { code: 'it', label: 'Italiano' },
  { code: 'pl', label: 'Polski' },
  { code: 'zh', label: '中文' },
];

function LangTestUI() {
  const { lang, setLang } = useAppLang();
  return (
    <select
      data-testid="lang-select"
      value={lang}
      onChange={(e) => setLang(e.target.value)}
    >
      {LANGUAGES.map((l) => (
        <option key={l.code} value={l.code}>{l.label}</option>
      ))}
    </select>
  );
}

afterEach(cleanup);

describe('UI Translations — AppLangProvider', () => {
  LANGUAGES.forEach(({ code, label }) => {
    it(`cambia la interfaz a ${label} (${code})`, async () => {
      render(
        <AppLangProvider>
          <LangTestUI />
        </AppLangProvider>
      );
      // Wait for initial language load (AppLangProvider returns null while loading)
      const select = await waitFor(() => screen.getByTestId('lang-select'));

      // Switch to target language
      fireEvent.change(select, { target: { value: code } });

      // After language reload, select reappears with new value
      await waitFor(() =>
        expect(screen.getByTestId('lang-select')).toHaveValue(code)
      );
    });
  });
});
